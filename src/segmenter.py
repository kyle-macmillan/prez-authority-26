"""
Segment presidential documents into classifiable units.

Each document is split on double-spaces (the scraper's paragraph delimiter),
chunks are classified by role, then grouped into segments based on structure.

Segment types returned:
  'metadata'    - header, subject, doc number, signature, dateline (not for classification)
  'section'     - classifiable unit: formal section, subsection, or long standalone directive
  'paragraph'   - classifiable unit: freestanding body paragraph
  'boilerplate' - standard closing legal language (not for classification)
"""

import re
from dataclasses import dataclass, field
from typing import Literal

SegmentType = Literal["metadata", "section", "paragraph", "boilerplate"]

# Items below this threshold are list items → group with surrounding content.
# Items at or above are substantive standalone directives → own segment.
_STRUCT_ITEM_MIN_CHARS = 400


@dataclass
class Segment:
    text: str
    seg_type: SegmentType
    chunk_indices: list[int] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Chunk classification
# ---------------------------------------------------------------------------

# Period after the number distinguishes document section headers ("Section 1. Policy.")
# from references to external law sections ("Section 1016 of the Intelligence Reform Act").
# Allow optional whitespace before the period to handle "Sec. 2 . Title" formatting variants.
_SECTION_RE = re.compile(r"^(Section|Sec\.)\s+\d+\s*\.", re.IGNORECASE)
# Some documents (e.g. NSC-organization memos) use uppercase-letter section headers: "A. Title".
# Must be case-sensitive — lowercase (a), (b) are list sub-items, not section headers.
# Require the word after the period to begin with a letter (not a digit) to avoid matching
# land parcel descriptors like "T. 16 N., R. 13 E.,"
_SECTION_ALPHA_RE = re.compile(r"^[A-Z]\.\s+[A-Za-z]")
_STRUCT_ITEM_RE = re.compile(
    r"^(\(\d+\)|\([a-z]\)|\([ivxlcdm]+\)|\d+\.)\s", re.IGNORECASE
)
_DOT_FILL_RE = re.compile(r"\.{3,}")

_METADATA_PATTERNS = [
    re.compile(r"^Memorandum for\b", re.IGNORECASE),
    re.compile(r"^Dear\s"),
    re.compile(r"^Subject:\s", re.IGNORECASE),
    re.compile(r"^Presidential (Determination|Finding)\s*(No\.?|#)", re.IGNORECASE),
    # Directive numbering schemes (short title lines like "NSPM-10", "NSM-8", "NSD-1")
    re.compile(r"^(NSD|PPD|SPD|NSDD|NSPD|HSPD|PDD|PSD|NSM|NSPM|NSPD)-?\s*\d+\b"),
    re.compile(
        r"^(National Security|Presidential Policy|Presidential Study|Space Policy|"
        r"Homeland Security Presidential|National Security Presidential)\s+"
        r"(Memorandum|Directive|Decision Directive|Presidential Directive|Presidential Memorandum)"
        r"[-/\s]*[\w-]*\s*$",  # allows suffix like "-3", "/NSPM-10", "/NSM-8"
        re.IGNORECASE,
    ),
    re.compile(r"^(THE WHITE HOUSE|The White House)[,\s]*$", re.IGNORECASE),
    re.compile(r"^Washington,\s"),
    re.compile(r"^\[Filed with the Office of the Federal Register", re.IGNORECASE),
    re.compile(r"^(Sincerely|Respectfully|Yours truly)[,.]?\s*$", re.IGNORECASE),
    re.compile(r"^(FROM|TO):\s", re.IGNORECASE),
    # Proclamation attestation line: "By the President:"
    re.compile(r"^By the President:?\s*$", re.IGNORECASE),
    # Bracket-enclosed annotations: "[Released Jan 15, 1966]", "[The Honorable, ...]"
    re.compile(r"^\[.*\]\s*$"),
    # Standalone date lines: "November 5, 1988." or "May 31, 1984"
    re.compile(
        r"^(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+\d{1,2},\s+\d{4}\.?\s*$"
    ),
]

_BOILERPLATE_SIGNALS = [
    "nothing in this",
    "does not create any right or benefit",
    "shall be implemented consistent with applicable law",
    "this memorandum shall be implemented consistent",
    "this order shall be implemented consistent",
    "this directive shall be implemented consistent",
    "does not alter existing authorities",
    "is not intended to, and does not, create any right",
    # publish / transmit / report / submit / inform / notify closing paragraphs
    "authorized and directed to publish this",
    "authorized and directed to report this",
    "authorized and directed to report these",
    "authorized and directed to report",
    "authorized and directed to transmit",
    "authorized and directed to submit this",
    "authorized and directed to inform",
    "authorized and directed to notify",
    "directed to report this determination to the congress",
    "directed to report these determinations",
    "directed to report this finding to the congress",
    "directed to bring this determination",
    "directed to inform the appropriate committees",
    "directed to inform the congress",
    "directed to submit this determination",
    "directed to submit this designation",
    "directed to notify the congress",
    "directed to notify the appropriate",
    "directed to transmit this determination",
    "directed to implement this determination",
    "directed to publish this determination",
    "directed to publish this memorandum",
    "requested to report this determination",
    "further directed to publish",
    "please transmit this determination",
    "shall be published in the federal register",
    "to be published in the federal register",
    "notify the congress of this determination",
    "certification shall be published in the federal register",
    "ensure the publication of this memorandum in the federal register",
    "arrange for its publication in the federal register",
    "in witness whereof",
    # Proclamation formal closing: "DONE at the City of Washington this..."
    "done at the city of",
    # Conditional implementation note tied to the transmission act itself
    "take effect after transmission of this determination",
]

# Signature: short chunk near end that looks like a presidential name.
# Handles all-caps (RONALD REAGAN), title-case (George W. Bush),
# comma suffix (JOSEPH R. BIDEN, JR.) and no-comma suffix (JOSEPH R. BIDEN JR.)
_SIGNATURE_RE = re.compile(
    r"^[A-Z][A-Za-z]+(\s+[A-Z]\.?)*(\s+[A-Z][A-Za-z]+)*"
    r"(\s*,\s*(Jr\.|Sr\.|JR\.|SR\.|II|III|IV))?\.?\s*$"
)


def _classify_chunk(chunk: str, position: int, total: int, is_last_n: bool) -> SegmentType:
    s = chunk.strip()
    if not s:
        return "metadata"

    for pat in _METADATA_PATTERNS:
        if pat.match(s):
            return "metadata"

    # Known presidential signature anywhere in document (handles mid-doc signatures
    # in multi-memo documents)
    if len(s) < 55 and _PRESIDENT_NAME_RE.match(s):
        return "metadata"

    # Fallback signature: short name-like string in last few chunks
    if is_last_n and len(s) < 55 and _SIGNATURE_RE.match(s):
        return "metadata"

    if _SECTION_RE.match(s):
        return "section"

    lower = s.lower()
    # Only classify as boilerplate if the chunk is a leaf (doesn't end with ':' introducing sub-items)
    if any(signal in lower for signal in _BOILERPLATE_SIGNALS) and not s.rstrip().endswith(":"):
        return "boilerplate"

    # Standalone structural directive: long enough to stand alone, no table fill
    if _STRUCT_ITEM_RE.match(s) and len(s) >= _STRUCT_ITEM_MIN_CHARS and not _DOT_FILL_RE.search(s):
        return "section"

    return "paragraph"


_BULLET_RE = re.compile(r"^[•\-\*]\s")

# Known presidential signatures — detected anywhere in the document (not just at the end)
# to handle multi-memo documents where a signature appears mid-way through.
_PRESIDENT_NAME_RE = re.compile(
    r"^("
    r"JOSEPH R\. BIDEN[,.]?\s*(JR\.|Jr\.)?|Joseph R\. Biden[,.]?\s*(Jr\.)?|"
    r"DONALD J\. TRUMP|Donald J\. Trump|"
    r"BARACK OBAMA|Barack Obama|"
    r"GEORGE W\. BUSH|George W\. Bush|"
    r"WILLIAM J\. CLINTON|William J\. Clinton|"
    r"GEORGE BUSH|George Bush|"
    r"RONALD REAGAN|Ronald Reagan|"
    r"JIMMY CARTER|Jimmy Carter|"
    r"GERALD R\. FORD|Gerald R\. Ford|"
    r"RICHARD NIXON|Richard Nixon|"
    r"LYNDON B\. JOHNSON|Lyndon B\. Johnson|"
    r"JOHN F\. KENNEDY|John F\. Kennedy|"
    r"DWIGHT D\. EISENHOWER|Dwight D\. Eisenhower|"
    r"HARRY S\.? TRUMAN|Harry S\.? Truman"
    r")\s*$",
    re.IGNORECASE,
)

# Embedded section header: a new "Sec. N." or "Section N." that follows a sentence-end
# within a chunk (single-space separated, not caught by the initial double-space split).
_EMBEDDED_SECTION_RE = re.compile(
    r"(?<=[.!?])\s+(?=(Section|Sec\.)\s+\d+\s*\.)", re.IGNORECASE
)


def _is_list_item(s: str) -> bool:
    """True for chunks that should attach to a surrounding paragraph rather than stand alone.
    Includes bullet points (always) and short structural items (below the standalone threshold).
    """
    if _BULLET_RE.match(s):
        return True
    return (
        bool(_STRUCT_ITEM_RE.match(s))
        and len(s) < _STRUCT_ITEM_MIN_CHARS
        and not _DOT_FILL_RE.search(s)
    )


# ---------------------------------------------------------------------------
# Document-level structure detection
# ---------------------------------------------------------------------------

def _is_section_header(s: str) -> bool:
    """True if the chunk is a formal section header (Section N., Sec. N., or A. B. C. style)."""
    return bool(_SECTION_RE.match(s) or _SECTION_ALPHA_RE.match(s))


def _has_formal_sections(chunks: list[str]) -> bool:
    return any(_is_section_header(c.strip()) for c in chunks)


def _ends_incomplete(text: str) -> bool:
    """True if text ends with ':' or no sentence-ending punctuation.

    A colon explicitly introduces what follows; alphanumeric endings indicate a
    sentence fragment or title — both signal that the next chunk belongs with this one.
    """
    s = text.rstrip()
    if not s:
        return False
    c = s[-1]
    return c == ":" or c.isalnum()


def _has_structural_items(chunks: list[str]) -> bool:
    """True if doc has at least one long struct item and no table-like tiny-item runs."""
    tiny_run = 0  # consecutive items that are table-like (<100 chars or dot-fill)
    found_long = False
    for c in chunks:
        s = c.strip()
        if _STRUCT_ITEM_RE.match(s):
            if len(s) < 100 or _DOT_FILL_RE.search(s):
                tiny_run += 1
                if tiny_run >= 4:
                    return False
            else:
                tiny_run = 0
                if len(s) >= _STRUCT_ITEM_MIN_CHARS:
                    found_long = True
        else:
            tiny_run = 0
    return found_long


# ---------------------------------------------------------------------------
# Grouping strategies
# ---------------------------------------------------------------------------

# Top-level numbered items within a section: "1. text", "2. text" — used as sub-section breaks.
# Lettered items (a), (b), (c) are sub-items of a section and stay merged with it.
_SECTION_NUMBERED_RE = re.compile(r"^\d+\.\s+\S")


def _group_by_sections(
    tagged: list[tuple[SegmentType, str, int]],
    split_subsections: bool = True,
) -> list[Segment]:
    """One segment per formal section; metadata stripped; preamble paragraphs merged.

    When split_subsections=True (default), top-level numbered items (1. 2. 3.) within a
    section start new sub-segments.  When False, everything within a formal section stays
    merged into one segment — useful for display/review where you want complete sections.
    Boilerplate detection still applies to standalone chunks outside formal sections.
    """
    segments: list[Segment] = []
    current_chunks: list[str] = []
    current_indices: list[int] = []
    current_type: SegmentType = "paragraph"

    def flush():
        if current_chunks:
            segments.append(Segment(" ".join(current_chunks), current_type, current_indices[:]))
            current_chunks.clear()
            current_indices.clear()

    for seg_type, text, idx in tagged:
        s = text.strip()

        if seg_type == "metadata":
            flush()
            segments.append(Segment(text, "metadata", [idx]))
            current_type = "paragraph"
            continue

        # Only a formal section header (Section N., Sec. N., or A./B./C. style) starts a new
        # section. Long structural items classified as "section" by _classify_chunk are treated
        # as regular content and appended to the current section below.
        if _is_section_header(s):
            flush()
            current_chunks.append(text)
            current_indices.append(idx)
            current_type = "section"
            continue

        # Outside a section, boilerplate chunks remain boilerplate
        if seg_type == "boilerplate" and current_type != "section":
            if current_chunks:
                flush()
            segments.append(Segment(text, "boilerplate", [idx]))
            continue

        # Within a section: numbered items (1. 2. 3.) start new sub-segments when enabled —
        # UNLESS the preceding content ends with ':' or no punctuation, meaning the items
        # are part of a list introduced by that content, not independent sub-sections.
        # Lettered items (a), (b), (c) always stay merged.
        if (split_subsections
                and current_type == "section"
                and current_chunks
                and _SECTION_NUMBERED_RE.match(s)
                and not _ends_incomplete(current_chunks[-1])):
            flush()
            current_chunks.append(text)
            current_indices.append(idx)
            # current_type stays "section"
            continue

        if not current_chunks:
            current_type = seg_type
        current_chunks.append(text)
        current_indices.append(idx)

    flush()
    return segments


def _group_by_struct_items(tagged: list[tuple[SegmentType, str, int]]) -> list[Segment]:
    """
    Long struct_items get their own segments.
    Short list items and short orphans attach to the nearest preceding content.
    """
    segments: list[Segment] = []
    current: list[tuple[str, int]] = []
    current_type: SegmentType = "paragraph"

    def flush():
        if current:
            segments.append(Segment(
                " ".join(t for t, _ in current),
                current_type,
                [i for _, i in current],
            ))
            current.clear()

    for seg_type, text, idx in tagged:
        s = text.strip()

        if seg_type == "metadata":
            flush()
            segments.append(Segment(text, "metadata", [idx]))
            current_type = "paragraph"
            continue

        if seg_type == "boilerplate":
            flush()
            segments.append(Segment(text, "boilerplate", [idx]))
            current_type = "paragraph"
            continue

        if seg_type == "section":
            # Long standalone directive — but if the preceding content ends with ':' or
            # no punctuation, this is a list item (not an independent sub-section).
            if current and _ends_incomplete(" ".join(t for t, _ in current)):
                current.append((text, idx))
            else:
                flush()
                current.append((text, idx))
                current_type = "section"
            continue

        # Short list item or short orphan: attach to current open segment
        if _is_list_item(s) or len(s) < 80:
            if current:
                current.append((text, idx))
            else:
                # Nothing open yet — start accumulating
                current.append((text, idx))
                current_type = "paragraph"
            continue

        # Substantive paragraph (not a list item, not short)
        if current_type == "section":
            # A new substantial paragraph after a struct_item → flush, start fresh paragraph
            flush()
            current.append((text, idx))
            current_type = "paragraph"
        else:
            # Continue current paragraph segment
            flush()
            current.append((text, idx))
            current_type = seg_type if seg_type != "paragraph" else "paragraph"

    flush()
    return segments


def _group_as_paragraphs(tagged: list[tuple[SegmentType, str, int]]) -> list[Segment]:
    """
    No structural markers: each substantive paragraph is its own segment.
    Short list items (<700 chars, structural pattern) attach to the current open segment.
    Short orphans (<80 chars) attach forward to the next substantive chunk.
    """
    segments: list[Segment] = []
    current: list[tuple[str, int]] = []
    current_type: SegmentType = "paragraph"
    pending_orphans: list[tuple[str, int]] = []  # short non-structural chunks waiting to attach

    def flush():
        if current:
            segments.append(Segment(
                " ".join(t for t, _ in current),
                current_type,
                [i for _, i in current],
            ))
            current.clear()

    for seg_type, text, idx in tagged:
        s = text.strip()

        if seg_type == "metadata":
            flush()
            if pending_orphans:
                # orphans before metadata — emit as own paragraph
                segments.append(Segment(
                    " ".join(t for t, _ in pending_orphans),
                    "paragraph",
                    [i for _, i in pending_orphans],
                ))
                pending_orphans.clear()
            segments.append(Segment(text, "metadata", [idx]))
            current_type = "paragraph"
            continue

        if seg_type == "boilerplate":
            flush()
            if pending_orphans:
                segments.append(Segment(
                    " ".join(t for t, _ in pending_orphans),
                    "paragraph",
                    [i for _, i in pending_orphans],
                ))
                pending_orphans.clear()
            segments.append(Segment(text, "boilerplate", [idx]))
            current_type = "paragraph"
            continue

        # Short list item: attach to current open segment
        if _is_list_item(s):
            if pending_orphans:
                current.extend(pending_orphans)
                pending_orphans.clear()
            current.append((text, idx))
            continue

        # Short orphan: buffer it to attach to the next substantive chunk
        if len(s) < 80:
            pending_orphans.append((text, idx))
            continue

        # Substantive chunk: flush any open segment, absorb pending orphans, start fresh
        flush()
        current.extend(pending_orphans)
        pending_orphans.clear()
        current.append((text, idx))
        current_type = seg_type

    flush()
    if pending_orphans:
        segments.append(Segment(
            " ".join(t for t, _ in pending_orphans),
            "paragraph",
            [i for _, i in pending_orphans],
        ))
    return segments


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _resplit_embedded_sections(chunks: list[str]) -> list[str]:
    """Further split chunks that contain an embedded section header after a sentence end.

    The scraper sometimes collapses a section break to a single space instead of
    double-space, e.g. '...allies and partners. Sec. 2. Policy. With respect...'
    This detects and splits at those points so the section header starts a new chunk.
    """
    result = []
    for chunk in chunks:
        parts = _EMBEDDED_SECTION_RE.split(chunk)
        result.extend(p.strip() for p in parts if p.strip())
    return result


def segment(
    doc_text: str,
    doc_type: str = "",
    split_subsections: bool = True,
    split_paragraphs: bool = True,
) -> list[Segment]:
    """Segment a document's text into classifiable units.

    Args:
        doc_text: Raw document text from the CSV.
        doc_type: Optional document type hint (unused currently).
        split_subsections: When True (default), numbered items (1. 2. 3.) within a
            formal section each become their own segment.  Set to False to keep entire
            sections merged — useful for display/review.
        split_paragraphs: When True (default), documents without formal sections are
            split into individual paragraph/section segments.  When False, all content
            in a non-sectioned document is merged into a single paragraph segment —
            useful for classification where the whole document is one unit.
            Has no effect on documents that have formal sections.
    """
    raw_chunks = re.split(r"  +", doc_text)
    chunks = _resplit_embedded_sections(
        [c.strip() for c in raw_chunks if c.strip()]
    )
    total = len(chunks)

    tagged: list[tuple[SegmentType, str, int]] = []
    for i, chunk in enumerate(chunks):
        is_last_n = i >= total - 5
        ct = _classify_chunk(chunk, i, total, is_last_n)
        tagged.append((ct, chunk, i))

    has_sections = _has_formal_sections(chunks)

    if has_sections:
        segs = _group_by_sections(tagged, split_subsections=split_subsections)
    elif _has_structural_items(chunks):
        segs = _group_by_struct_items(tagged)
    else:
        segs = _group_as_paragraphs(tagged)

    segs = _merge_incomplete_paragraphs(segs)
    segs = _enforce_closing_cutoff(segs)
    segs = _enforce_signoff_cutoff(segs)

    if not split_paragraphs and not has_sections:
        segs = _merge_content_segments(segs)

    return segs


def _merge_incomplete_paragraphs(segs: list[Segment]) -> list[Segment]:
    """Merge a paragraph into the next if it ends with ':' or no terminal punctuation.

    A colon introduces what follows; alphanumeric endings indicate a fragment or title.
    Both mean the next paragraph is semantically part of the same unit.
    Only merges paragraph→paragraph; does not cross metadata or boilerplate boundaries.
    """
    result = list(segs)
    i = 0
    while i < len(result) - 1:
        seg = result[i]
        nxt = result[i + 1]
        if (seg.seg_type == "paragraph"
                and nxt.seg_type == "paragraph"
                and _ends_incomplete(seg.text)):
            merged = Segment(
                seg.text + " " + nxt.text,
                "paragraph",
                seg.chunk_indices + nxt.chunk_indices,
            )
            result[i : i + 2] = [merged]
            # Don't increment — merged segment may itself end incomplete
        else:
            i += 1
    return result


def _enforce_closing_cutoff(segs: list[Segment]) -> list[Segment]:
    """After 'In Witness Whereof', reclassify any remaining paragraph segments as boilerplate.

    Everything following that formula is closing ceremony (datelines, attestations, etc.)
    and should never be classified as content.
    """
    past_cutoff = False
    result = []
    for seg in segs:
        if not past_cutoff and seg.seg_type == "boilerplate" and "in witness whereof" in seg.text.lower():
            past_cutoff = True
        if past_cutoff and seg.seg_type == "paragraph":
            result.append(Segment(seg.text, "boilerplate", seg.chunk_indices))
        else:
            result.append(seg)
    return result


def _enforce_signoff_cutoff(segs: list[Segment]) -> list[Segment]:
    """After the last presidential signature, reclassify trailing content as metadata.

    Boilerplate and short paragraphs (< 100 chars) that follow the signature are
    attestation lines, titles, and datelines — all metadata.  Longer paragraphs are
    left alone to protect multi-memo documents where substantive content follows a
    mid-document signature.
    """
    last_sig_idx = -1
    for i, seg in enumerate(segs):
        if seg.seg_type == "metadata" and len(seg.text.strip()) < 55 and (
            _PRESIDENT_NAME_RE.match(seg.text.strip())
            or _SIGNATURE_RE.match(seg.text.strip())
        ):
            last_sig_idx = i

    if last_sig_idx == -1:
        return segs

    result = list(segs)
    for i in range(last_sig_idx + 1, len(segs)):
        seg = segs[i]
        if seg.seg_type == "boilerplate":
            result[i] = Segment(seg.text, "metadata", seg.chunk_indices)
    return result


def _merge_content_segments(segs: list[Segment]) -> list[Segment]:
    """Merge consecutive non-metadata/non-boilerplate segments into one paragraph each.

    Preserves ordering: metadata and boilerplate are emitted in place; runs of content
    segments between them are collapsed to a single paragraph.
    """
    result: list[Segment] = []
    content_texts: list[str] = []
    content_indices: list[int] = []

    def flush_content() -> None:
        if content_texts:
            result.append(Segment(" ".join(content_texts), "paragraph", content_indices[:]))
            content_texts.clear()
            content_indices.clear()

    for seg in segs:
        if seg.seg_type in ("metadata", "boilerplate"):
            flush_content()
            result.append(seg)
        else:
            content_texts.append(seg.text)
            content_indices.extend(seg.chunk_indices)

    flush_content()
    return result
