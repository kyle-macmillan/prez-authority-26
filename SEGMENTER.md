# Document Segmenter

`src/segmenter.py` splits presidential documents from `data/4_28_2026_build.csv` into
classifiable units. Each document's `doc_text` field has all whitespace collapsed by the
scraper: paragraphs are separated by **double spaces** and there are no newlines.

## Output: Segment types

| Type | Description |
|------|-------------|
| `section` | Classifiable unit: a formal section, subsection, or long standalone directive |
| `paragraph` | Classifiable unit: a freestanding body paragraph |
| `vesting_clause` | Opening directive sentence citing legal authority ("vested in me") — excluded from classification |
| `boilerplate` | Standard closing legal language — excluded from classification |
| `metadata` | Header, subject, doc number, signature, dateline — excluded from classification |

## API

```python
from segmenter import segment

segments = segment(
    doc_text,
    doc_type="",           # unused, reserved
    split_subsections=True, # split numbered sub-items within sections into own segments
    split_paragraphs=True,  # split unstructured documents into paragraphs vs. one unit
)
```

Set `split_subsections=False` for display/review (keeps each formal section as one block).  
Set `split_paragraphs=False` for classification of short unstructured documents (the whole
body becomes one segment rather than many small paragraphs).

---

## Pipeline

### Step 1 — Primary split

The raw text is split on two-or-more spaces: `re.split(r"  +", doc_text)`. This yields the
base **chunks** — the scraper's paragraph-level units.

### Step 2 — Resplit embedded section headers

Some section headers are separated from the preceding paragraph by only a single space
(scraper artifact), e.g. `"...allies and partners. Sec. 2. Policy. With respect..."`.
`_resplit_embedded_sections` detects the pattern `[.!?]\s+(Section|Sec\.)\s+\d+\s*\.` and
splits at those points so the section header begins a new chunk.

### Step 3 — Chunk classification

Each chunk is classified by `_classify_chunk` into one of the four types:

**Metadata** — matched by explicit patterns:
- Recipient/salutation headers: `Memorandum for`, `Dear `, `FROM:`, `TO:`, `By the President:`
- Subject and document-number lines: `Subject:`, `Presidential Determination No.`, and
  directive codes (`NSD-N`, `NSM-N`, `NSPM-N`, `PPD-N`, `SPD-N`, `HSPD-N`, …) as well as
  title lines like `"National Security Presidential Memorandum/NSPM-10"`
- Datelines: `Washington,`, `THE WHITE HOUSE`, standalone `Month DD, YYYY` dates,
  `[Filed with the Office of the Federal Register…]`, bracket-enclosed annotations `[…]`
- Signatures: all fourteen presidents by name (all-caps and title-case variants including
  suffixes like `JR.`); fallback short-name pattern in the last five chunks
- Closings: `Sincerely,`, `Respectfully,`

**Section headers** — matched by `_SECTION_RE` or `_SECTION_ALPHA_RE`:
- `Section N.` / `Sec. N.` (optional space before the period; catches `Sec. 2 . Title`)
- `A.`, `B.`, `C.` … uppercase-letter headers (must be followed by a letter, not a digit,
  to avoid land-parcel descriptors like `T. 16 N., R. 13 E.,`)
- References to external law sections (`Section 1016 of the Act`) are **not** matched because
  they lack the period after the number

**Boilerplate** — substring match against `_BOILERPLATE_SIGNALS` (case-insensitive), provided
the chunk does **not** end with `:` (which would make it a list header, not a leaf):
- General Provisions language: `"nothing in this"`, `"does not create any right or benefit"`,
  `"shall be implemented consistent with applicable law"`, …
- Publication / transmission closings: `"shall be published in the federal register"`,
  `"authorized and directed to publish/transmit/submit/report/inform/notify"`,
  `"directed to submit this determination"`, `"directed to notify the congress"`, …
- Formal closing formulas: `"in witness whereof"`, `"done at the city of"`,
  `"take effect after transmission of this determination"`

**Section (structural directive)** — a chunk that matches a structural item pattern
(`(a)`, `(1)`, `1.`, etc.), is **≥ 400 characters**, and contains no dot-fill (table rows
are excluded). Shorter items are `paragraph`.

**Paragraph** — everything else.

---

### Step 4 — Structure detection

The document is routed to one of three groupers:

| Condition | Grouper |
|-----------|---------|
| Any chunk matches a formal section header | `_group_by_sections` |
| At least one structural item ≥ 400 chars | `_group_by_struct_items` |
| Neither | `_group_as_paragraphs` |

---

### Step 5 — Grouping rules

#### `_group_by_sections`

Used for documents with `Section N.` / `Sec. N.` / `A. B. C.` headers.

- Each formal section header flushes the current accumulation and starts a new `section`
  segment. Everything between two section headers stays merged.
- **Numbered sub-items** (`1.`, `2.`, `3.`) start their own sub-segments when
  `split_subsections=True` — *unless* the preceding content ends with `:` or no terminal
  punctuation, in which case they are list items introduced by that content and stay merged.
- Boilerplate chunks that appear *outside* a formal section are emitted as `boilerplate`.
  Boilerplate inside a section stays merged into the section.
- Sections are always type `section` regardless of content — General Provisions sections
  stay `section`, not `boilerplate`.

#### `_group_by_struct_items`

Used for documents without formal sections but with at least one long directive item.

- Items ≥ 400 chars starting with a structural pattern → `section` segment, *unless* the
  preceding content ends with `:` or no terminal punctuation (treated as a list item, merged
  into the preceding segment instead).
- Items < 400 chars with a structural pattern → **list items**: attach to the current open
  segment rather than starting a new one.
- Bullet points (`•`, `-`, `*`) → always attach to the preceding segment.
- Short orphans (< 80 chars) → attach to the current open segment.

#### `_group_as_paragraphs`

Used for documents with no formal sections and no long structural items (most memos,
proclamations, letters).

- Each substantive chunk (≥ 80 chars, not a list item) → its own `paragraph` segment.
- List items (< 400 chars, structural pattern — `(1)`, `(a)`, `(i)`, `1.`, bullets) →
  each becomes its own `paragraph` segment so list elements can be coded individually.
- Short orphans (< 80 chars) → buffered and attached to the *next* substantive chunk,
  or backward to the previous paragraph if no forward target exists.

---

### Step 6 — Post-processing passes (applied in order)

1. **`_merge_incomplete_paragraphs`** — If a `paragraph` ends with `:` or alphanumeric
   (no sentence-ending punctuation), it is merged forward into the next `paragraph`.
   Repeats until neither paragraph ends incompletely. Does not cross `metadata` or
   `boilerplate` boundaries.

2. **`_enforce_closing_cutoff`** — After the first `boilerplate` segment containing
   `"in witness whereof"`, any remaining `paragraph` segments are reclassified as
   `boilerplate`. This captures datelines, attestation lines, and other closing ceremony
   that follows the formula.

3. **`_enforce_signoff_cutoff`** — After the last presidential signature (`metadata`),
   any remaining `boilerplate` segments are reclassified as `metadata`. This handles
   trailing attestation lines (e.g. `"By the President:"`, `"Secretary of State"`) that
   appear after the signature in proclamations.

4. **`_merge_content_segments`** *(only when `split_paragraphs=False`)* — All non-metadata,
   non-boilerplate segments between `metadata`/`boilerplate` boundaries are merged into a
   single `paragraph`. Useful for classifying short unstructured documents as a whole unit.

---

## Holdout set

`data/holdout_ids.json` contains 2,021 document IDs (10 % of each doc type, stratified,
seeded at 42) that were set aside before any rule development. These should not be used for
further rule tuning.

`data/test_sample_ids.json`, `data/test_sample_ids_2.json`, and `data/test_sample_ids_3.json`
contain three successive 20-document review batches (5 per doc type each, seeds 99 / 17 / 31)
used during development. Corresponding HTML viewers are in `data/sample_segmentation/`.

## Viewer

```bash
python3 src/view_segments.py [--n N] [--id ROW_ID]
```

Writes `data/sample_segmentation/segments_viewer.html`.  The page has one tab per document
type (Executive Orders, Memos, Letters, Proclamations).  Each document has an alphanumeric
ID that restarts per tab — EO1, EO2, … / M1, M2, … / L1, L2, … / P1, P2, … — and shows
the original text (left) and labelled segments (right) with a link to the source UCSB page.

`--n` controls how many documents are sampled per type (default 5).  `--id` loads a single
document by CSV row index, bypassing the sampling.
