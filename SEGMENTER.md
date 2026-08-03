# Document Segmenter

`src/segmenter.py` splits presidential documents from `data/4_28_2026_build_dev.csv` into
classifiable units. Each document's `doc_text` field has all whitespace collapsed by the
scraper: paragraphs are separated by **double spaces** and there are no newlines.

Two segmentation strategies are available via the same API.

---

## Segment types

### Section/Paragraph strategy (`segment()`)

| Type | Classifiable | Description |
|------|:---:|-------------|
| `section` | ✓ | Formal section, subsection, or long standalone directive |
| `paragraph` | ✓ | Freestanding body paragraph |
| `vesting_clause` | — | Opening authority citation ("vested in me") |
| `boilerplate` | — | Standard closing/limitation language |
| `metadata` | — | Header, subject, doc number, signature, dateline |

### Woolley & Peters strategy (`segment_ordering()`)

| Type | Classifiable | Description |
|------|:---:|-------------|
| `order_action` | ✓ | Directive starting at (or triggered by) an ordering phrase |
| `preamble` | — | Text before the first ordering phrase, or sections lacking one |
| `ordering_phrase` | — | Short introductory connector at the document opening (e.g. "it is hereby ordered as follows:") |
| `vesting_clause` | — | Sentence(s) citing the legal authority for the directive |
| `boilerplate` | — | Standard closing/limitation language |
| `metadata` | — | Same as above |

---

## API

```python
from segmenter import segment, segment_ordering

# Section/Paragraph strategy
segments = segment(
    doc_text,
    doc_type="",            # unused, reserved
    split_subsections=True, # split numbered sub-items within sections into own segments
    strict_wp=False,        # True → disable extensions, use pure W&P phrase list only
)

# Woolley & Peters strategy (also called automatically by segment() for unstructured docs)
segments = segment_ordering(
    doc_text,
    doc_type="",            # unused, reserved
    strict_wp=False,        # True → disable extensions, use pure W&P phrase list only
)
```

`strict_wp=True` disables both the generic `shall + verb` extension and the sentence-opening
authority-citation vesting detection, falling back to the original W&P phrase list and
standard vesting logic.

---

## Ordering phrases

The W&P ordering-phrase list (`src/ordering_phrases.py`) drives both strategies. It contains
~305 phrases drawn from the appendix of Woolley & Peters (PSQ), e.g. `"i hereby order"`,
`"do hereby proclaim"`, `"shall coordinate"`, `"you are directed"`.

`CURATED_OUT` is a small exclusion set for phrases that fire too heavily in non-directive
contexts (currently `"this directive"`, `"designated"`, `"designation"`).

### `shall + verb` extension

In addition to the phrase list, the extended regex (`extended=True`) adds a pattern for
directives of the form:

> *shall [also / promptly / immediately] [allowlisted directive verb]*

Examples matched:
- `"The Board shall perform"`
- `"Federal agencies shall promptly develop"`
- `"The Secretary shall also make"`

The allowlisted verbs are `take`, `develop`, `designate`, `establish`, `perform`, `make`,
`issue`, `identify`, `prepare`, `implement`, `determine`, `recommend`, `prescribe`, `seek`,
and `assist`. This pattern applies to both formal sections and unstructured documents
when `strict_wp=False`. In unstructured documents, a match starts a new `order_action`
using the same sentence-boundary rules as the original W&P phrases. Generic `shall + verb`
matches inside straight or curly double-quoted text are ignored so that quoted statutes,
regulations, and prior directives do not create new actions.

---

## Vesting clause detection

A sentence is carved out as `vesting_clause` when it contains one of the following signals.
Detection happens sentence-by-sentence after the primary chunk split.

### Strong signals (unconditional)

The sentence is tagged `vesting_clause` regardless of whether an ordering phrase follows:

| Signal | Typical form |
|--------|-------------|
| `"vested in me"` | "By the authority vested in me as President…" |
| `"by virtue of the authority"` | "By virtue of the authority vested in me…" |
| `"joint resolution"` | Proclamations citing a Congressional joint resolution |
| `"public law"` | Proclamations citing a Public Law (e.g. "Public Law 87-20") |
| Sentence **opens with** `"Pursuant to / Under section [law citation]"` | "Pursuant to section 121(a) of title 40…", "Pursuant to the International Emergency Economic Powers Act…" |

The sentence-opening authority pattern (`_OPENING_AUTHORITY_RE`) requires a matching law
citation (`_LAW_CITATION_RE`) somewhere in the same sentence and anchors to the **start** of
the sentence — it does not fire for mid-sentence "pursuant to" qualifiers like "The Secretary
shall, pursuant to section 5, submit reports."

### Conditional signals (require an ordering phrase in the same sentence)

| Signal | Typical form |
|--------|-------------|
| `"now, therefore, i"` | Standard proclamation invocation formula |
| `"pursuant to"` + law citation + `"I"` | "Pursuant to section X…, I hereby order…" |

A mid-sentence `"pursuant to"` statutory citation is also carved out when it follows both
a first-person presidential actor and an ordering phrase. This captures forms such as
`"I hereby designate … pursuant to section 251…"` without treating cabinet instructions
such as `"The Secretary shall, pursuant to section 5…"` as presidential vesting clauses.
Internal citation commas are retained when followed by another citation component, including
a year, `"as amended"`, a U.S.C./Stat./Public Law reference, or an additional provision.

### Vesting carve mechanics

When a sentence contains both a vesting signal **and** an ordering phrase, the text is split:

- Everything before the ordering phrase (up to the last punctuation before it, or right before
  the phrase if the intervening text is a continuation clause starting with `"including "`) →
  `vesting_clause`
- The ordering phrase and everything after → `order_action`

---

## Pipeline

### Step 1 — Primary split

Raw text is split on two-or-more spaces: `re.split(r"  +", doc_text)` → base **chunks**.

### Step 2 — Resplit embedded section headers

Scraper artifacts where a section header is separated by only a single space are detected and
re-split so the header starts its own chunk.

### Step 3 — Chunk classification

Each chunk is classified by `_classify_chunk`:

**Metadata** — explicit patterns: salutations (`Memorandum for`, `Dear `, `FROM:`, `TO:`),
subject/directive-number lines, datelines (`Washington,`, `THE WHITE HOUSE`, `Month DD, YYYY`),
all fourteen presidential signatures (all-caps and title-case), bracket annotations `[…]`.

**Boilerplate** — substring match against `_BOILERPLATE_SIGNALS`: General Provisions language
(`"nothing in this"`, `"does not create any right or benefit"`…), publication/transmission
closings (`"shall be published in the federal register"`…), formal closing formulas
(`"in witness whereof"`, `"done at the city of"`…).

**Section header** — `Section N.` / `Sec. N.`, uppercase-letter headers (`A. Title`),
multi-character Roman numeral headers (`II. Title`).

**Section (structural directive)** — structural list marker (`(a)`, `(1)`, `1.`, etc.),
≥ 400 characters, no dot-fill.

**Paragraph** — everything else.

### Step 4 — Vesting carve-out

Before grouping, chunks that contain a vesting signal are passed through `_carve_vesting`,
which splits them sentence-by-sentence and emits `vesting_clause` pieces separately.

### Step 5 — Route to grouper

| Condition | Path |
|-----------|------|
| Any chunk is a formal section header | Section/Paragraph grouper → W&P relabeling |
| No formal sections | Ordering-phrase segmentation |

### Step 6 — Section/Paragraph grouper (`_group_by_sections`)

- Each formal section header starts a new segment; everything between two headers merges.
- Numbered sub-items (`1.`, `2.`, `3.`) start sub-segments when `split_subsections=True`,
  unless the preceding content ends with `:` (list context).
- After grouping, sections lacking any ordering phrase are reclassified `preamble`.

### Step 7 — W&P relabeling (`_relabel_for_wp`, sections path only)

Applied after `_group_by_sections` when called from `segment_ordering()`:

| Condition | Label |
|-----------|-------|
| Section title is "Purpose" or "Definitions" | `preamble` |
| Section contains boilerplate signal | `boilerplate` |
| Section contains an ordering phrase | `order_action` |
| Section contains no ordering phrase | `preamble` |
| Paragraph with ordering phrase, **before** first `order_action` section | `ordering_phrase` |
| Paragraph with ordering phrase, **after** first `order_action` section | `order_action` |
| Paragraph without ordering phrase | `preamble` |

The extended regex (with generic `shall + verb` matching) is used here when
`strict_wp=False`, as it is in the no-sections path.

### Step 8 — Ordering-phrase segmentation (no-sections path)

Each ordering phrase starts a new `order_action`. Text before the first ordering phrase
is `preamble`. List items following an open directive are grouped into it unless they
contain their own ordering phrase.

Post-processing: `_split_colon_lists` splits colon-introduced lists into a header +
individual items; `_merge_sublists` reassembles sub-items into their parent directive.

### Step 9 — Post-processing (both paths)

1. **`_merge_incomplete_paragraphs`** — Paragraphs ending with `:` or no terminal
   punctuation are merged forward into the next paragraph.
2. **`_enforce_closing_cutoff`** — After `"in witness whereof"`, remaining paragraphs
   become `boilerplate`.
3. **`_enforce_signoff_cutoff`** — After the last presidential signature, remaining
   `boilerplate` segments become `metadata`.
4. **`_reclassify_titles_before_metadata`** — Short incomplete paragraphs immediately
   before a metadata segment become `metadata`.

---

## Holdout and review sets

`data/holdout_ids.json` — 2,021 document IDs (10% of each doc type, stratified, seed 42)
set aside before any rule development. Do not use for further rule tuning.

`data/sample_segmentation/` — HTML viewers for successive review batches used during
development, including `pilot_20.html` (20-document pilot with multi-annotator labels)
and `pilot_20_new_strategy.html` (same documents, W&P strategy, current rules).

---

## Viewer

```bash
# Rebuild a saved document set by ID map (e.g. the pilot)
python3 src/view_segments.py --from-map data/sample_segmentation/doc_id_map_pilot_20.json \
    --out pilot_20_new_strategy.html

# Fresh random sample (5 docs per type)
python3 src/view_segments.py [--n N] [--seed SEED] [--out filename.html]

# Single document by CSV row index
python3 src/view_segments.py --id ROW_INDEX
```

The viewer shows the original text on the left (annotation canvas) and colour-coded segments
on the right. A toggle in the top bar switches between Section/Paragraph and W&P views.
Ordering phrases are highlighted in bold within each segment.
