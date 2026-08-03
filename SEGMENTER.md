# Document Segmenter

`src/segmenter.py` splits presidential documents into classifiable units. The vesting-authority
analysis runs it over the union of `data/4_28_2026_build_dev.csv` and
`data/4_28_2026_build_holdout.csv` (20,232 unique directives). Each document's `doc_text` field
has all whitespace collapsed by the scraper: paragraphs are separated by **double spaces** and
there are no newlines.

Two segmentation strategies remain available via the same API for historical comparison.
Starting with annotation Round 2, annotation viewers no longer use sections or expose the
Section/Paragraph strategy: they show only the extended Woolley & Peters strategy
(`segment_ordering(..., strict_wp=False)`).

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

`strict_wp=True` disables both the section-only `shall + verb` extension and the sentence-opening
authority-citation vesting detection, falling back to the original W&P phrase list and
standard vesting logic.

---

## Ordering phrases

The W&P ordering-phrase list (`src/ordering_phrases.py`) drives both strategies. It contains
~305 phrases drawn from the appendix of Woolley & Peters (PSQ), e.g. `"i hereby order"`,
`"do hereby proclaim"`, `"shall coordinate"`, `"you are directed"`.

`CURATED_OUT` is a small exclusion set for phrases that fire too heavily in non-directive
contexts (currently `"this directive"`, `"designated"`, `"designation"`).

### `shall + verb` extension (sections path only)

In addition to the phrase list, the extended regex (`extended=True`) adds a pattern for
directives of the form:

> *shall [also / promptly / immediately] [allowlisted directive verb]*

Examples matched:
- `"The Board shall perform"`
- `"Federal agencies shall promptly develop"`
- `"The Secretary shall also make"`
- `"The Secretary shall, within 90 days, prepare"`
- `"The agency shall, in consultation with other agencies, issue"`

The comma-delimited form permits up to 160 intervening characters, may contain internal
commas, and cannot cross a period or semicolon. The action verb after the closing comma
must still be on the allowlist.

The allowlisted verbs are `take`, `develop`, `designate`, `establish`, `perform`, `make`,
`issue`, `identify`, `prepare`, `implement`, `determine`, `recommend`, `prescribe`, `seek`,
and `assist`. The extension applies across structured and unstructured documents and is
disabled when `strict_wp=True`.

---

## Vesting clause detection

Vesting detection is rule-based and case-insensitive. Before matching, the authority-analysis
extractor collapses whitespace and splits sentences only at terminal punctuation outside
parentheses. This prevents periods in parenthetical citations such as `U.S.C.` or OCR variants
such as `13. S. C.` from truncating an authority clause.

### Strong authority signals

`_STRONG_VESTING_RE` recognizes the following reviewed formulations without requiring a
separate ordering phrase:

| Regex family | Examples and scope |
|--------------|--------------------|
| `vested\s+in\s+(?:me|my(?=\s+by))` | Standard `vested in me` language and the observed OCR error `vested in my by` |
| `by\s+virtue\s+of\s+the\s+authority` | Standard `By virtue of the authority vested in me…` clauses |
| `by\s+virtue\s+of\s+and\s+pursuant\s+to…vested\s+in\s+the\s+President` | Historical third-person presidential formula |
| `by\s+virtue\s+of\s+my\s+authority\s+as\s+President` | `By virtue of my authority as President of the United States…` |
| `pursuant\s+to\s+my\s+authority\s+to\s+regulate\s+federal\s+employment` | Reviewed federal-employment determination |
| `pursuant\s+to\s+my\s+authority\s+under\s+subsection\s+\d` | Reviewed trade-agreement reconfirmations |

Proclamations additionally treat a Congressional `joint resolution` or `public law` citation
as a strong signal. The formal `I, [name], President of the United States…` invocation is also
retained as generic presidential authority.

The reviewed Unified Command Plan formulation is narrower: `_REVIEWED_COMMANDER_AUTHORITY_RE`
matches `pursuant to my authority as Commander in Chief` only when it is followed by
`I hereby approve` or `I hereby rescind`. This avoids absorbing congressional-report letters
that describe military actions under the same constitutional role.

### Statutory and constitutional citation anchors

`_LAW_CITATION_RE` recognizes `section` or `subsection` numbers, numbered U.S.C. citations,
numbered titles and chapters, Public Laws, the Constitution, the laws or statutes of the United
States, and named Acts. `_AUTHORITY_CITATION_RE` adds `my constitutional authority`.

A sentence opening with `pursuant to`, `under section`, `under title`, or `under the authority`
is treated as an authority invocation only when one of those anchors appears in the sentence.
This prevents vague references such as `pursuant to applicable policy` from qualifying.

### Conditional and mid-sentence signals

The following constructions require an ordering phrase or a specifically reviewed
first-person action in the same sentence:

| Construction | Rule |
|--------------|------|
| `Now, therefore, I…` | Standard proclamation invocation followed by an ordering phrase |
| `pursuant to` + citation + presidential `I` | Authority prefix followed by a first-person ordering phrase |
| `It is hereby ordered, pursuant to [citation]…` | Passive presidential order followed by an inline authority citation |
| `I hereby order, by [the] authority vested in me…` | Post-ordering first-person vesting clause |
| `pursuant to [citation], I determine…` | Mid-sentence determination authority, including text following metadata or introductory context |
| `pursuant to [citation], I hereby exempt…` | Reviewed statutory exemption determinations |

For the last two constructions, `_pursuant_authority_action_start` selects the nearest
qualifying `pursuant to` before the action. It does not bridge intervening `consistent with`,
`in accordance with`, or `in response to` language. This guard prevents a `Pursuant to…`
document title from converting a later compliance statement into a vesting clause.

An inline `pursuant to` citation that follows an ordering phrase is retained only when the
preceding actor is first-person presidential or the passive formula is `it is hereby ordered`.
Thus `The Secretary shall, pursuant to section 5…` is not treated as presidential vesting.

### Vesting carve mechanics

When a sentence contains both a vesting signal and an ordering phrase, the authority text is
separated from the operative action. The extracted clause begins at the reviewed authority
connector (`by`, `by virtue of`, `pursuant to`, or `under`) and ordinarily ends at the comma
before the action. Citation-continuation commas are retained when followed by a year,
`as amended`, a U.S.C./Stat./Public Law reference, an additional section/title/chapter, or a
parenthetical citation. Parenthetical citations remain intact.

The extractor also applies narrow boundary corrections for reviewed historical Executive
Order and Proclamation citations and removes an `and in order to…` purpose tail from the
reviewed `By virtue of my authority as President…` formula.

Compliance or context language is not by itself a vesting signal. In particular, the matcher
does not infer presidential authority solely from `consistent with`, `in accordance with`,
`in order to`, `in furtherance of`, `in light of`, or `as contemplated by`. Reviewed letters
that merely report an action taken in another directive, and reviewed memoranda that only carry
out a statutory duty without invoking presidential authority, remain outside the matched forms.

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

The extended regex (with section-only `shall + verb` matching) is used here when
`strict_wp=False`.

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
originally set aside before rule development. The current descriptive vesting-authority
analysis covers the entire 20,232-document corpus by combining this set with the 18,211
development documents; it does not use child-parent-analysis exclusions.

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
