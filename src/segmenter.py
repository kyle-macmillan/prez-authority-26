"""
Segment presidential documents into classifiable units.

Two segmentation strategies are available:

  segment()          - "Section/Paragraph" strategy: structural segmentation using formal
                       section headers, paragraph breaks, and list detection.
  segment_ordering() - "Woolley & Peters" strategy: segment on ordering phrases
                       (e.g. "I hereby order", "do proclaim") per the appendix in
                       Woolley & Peters (PSQ).  Covers the entire document text with no
                       metadata/boilerplate exclusions.

Section/Paragraph segment types:
  'metadata'       - header, subject, doc number, signature, dateline (not for classification)
  'section'        - classifiable unit: formal section, subsection, or long standalone directive
  'paragraph'      - classifiable unit: freestanding body paragraph
  'boilerplate'    - standard closing legal language (not for classification)
  'vesting_clause' - opening authority citation ("vested in me") (not for classification)

Woolley & Peters segment types:
  'preamble'       - text before the first ordering phrase
  'order_action'   - text starting at (or just after) an ordering phrase
  'metadata'       - header, subject, doc number, signature, dateline (same as S/P strategy)
  'boilerplate'    - standard closing legal language (same as S/P strategy)
  'vesting_clause' - opening authority citation ("vested in me"), carved out from the sentence
                     that contains the first ordering phrase
"""

import re
from dataclasses import dataclass, field
from typing import Literal

SegmentType = Literal[
    "metadata", "section", "paragraph", "boilerplate", "vesting_clause",
    "preamble", "order_action", "ordering_phrase",
]

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
_SECTION_RE = re.compile(r"^(Section|Sec\.)\s+\d+\s*\.(?!\d)", re.IGNORECASE)
# Some executive orders use title-part numbering: "1-1. Title" for top-level
# sections and "1-101. Text" for subsections under that section.
_SECTION_HYPHEN_PRIMARY_RE = re.compile(r"^\d+-\d{1,2}\.\s+\S")
_SECTION_HYPHEN_SUB_RE = re.compile(r"^\d+-\d{3,}\.\s+\S")
_SECTION_HYPHEN_RE = re.compile(r"^\d+-\d+\.\s+\S")
# Some documents (e.g. NSC-organization memos) use uppercase-letter section headers: "A. Title".
# Must be case-sensitive — lowercase (a), (b) are list sub-items, not section headers.
# Require the word after the period to begin with a letter (not a digit) to avoid matching
# land parcel descriptors like "T. 16 N., R. 13 E.,"
_SECTION_ALPHA_RE = re.compile(r"^[A-Z]\.\s+[A-Za-z]")
# Multi-character Roman numeral section headers: "II. Title", "III. Title", "IV. Title", etc.
# Single-character Roman numerals (I., V., X.) are already covered by _SECTION_ALPHA_RE.
_SECTION_ROMAN_RE = re.compile(r"^[IVX]{2,}\.\s+[A-Za-z]")
# All Roman numeral section headers including single-character ones (I., V., X., XI., XII., …).
# Restricted to I/V/X so that C./D./L./M. (common alpha subsection labels) are not misread as
# Roman numeral primaries — presidential documents never reach Roman numerals that high.
_SECTION_ROMAN_ALL_RE = re.compile(r"^[IVX]+\.\s+[A-Za-z]")
# Sections whose title is "Purpose", "Purposes", or "Definitions" are always preamble.
_PURPOSE_TITLE_RE = re.compile(
    r"^(?:(?:Section|Sec\.)\s+\S+|[A-Z](?:\.[A-Z])*\.)\s+(?:Purposes?|Definitions)\b",
    re.IGNORECASE,
)
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

# A subject/header chunk can contain the beginning of the operative text when the
# source omits a paragraph boundary (for example, "Subject: Delegation ..., I hereby
# delegate ..."). Split only at clear present-tense commands. Requests, transmissions,
# endorsements, and descriptions of completed actions intentionally remain metadata or
# preamble.
_EMBEDDED_METADATA_COMMAND_RE = re.compile(
    r"\b(?:"
    r"I\s+(?:(?:do|am)\s+)?(?:hereby\s+)?"
    r"(?:authorize|appoint|delegate|designate|direct|establish|instruct|order|"
    r"prescribe|prohibit|revoke|terminate|transfer|withdraw)"
    r"|this\s+(?:memorandum|directive)\s+"
    r"(?:assigns|directs|establishes|instructs)"
    r"|you\s+are\s+(?:hereby\s+)?"
    r"(?:appointed|authorized|delegated|directed|instructed)"
    r")\b",
    re.IGNORECASE,
)

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
    r"^([A-Z][A-Za-z]+|[A-Z]\.)(\s+([A-Z]\.?|[A-Z][A-Za-z]+))*"
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

    # Fallback signature: short name-like string in last few chunks.
    # Exclude chunks that look like section headers (e.g. "F. National Cyber Incident Response Plan")
    # — real presidential signatures use full first names and never start with an initial + period.
    if is_last_n and len(s) < 55 and _SIGNATURE_RE.match(s) and not _SECTION_ALPHA_RE.match(s):
        return "metadata"

    if _SECTION_RE.match(s) or _SECTION_HYPHEN_RE.match(s):
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
    r"(?<=[.!?:])\s+(?=(?:(?:Section|Sec\.)\s+\d+\s*\.(?!\d)|\d+-\d+\.\s+\S))",
    re.IGNORECASE,
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
    """True if the chunk is a formal section header (Section N., Sec. N., A./B./C., or Roman numeral style)."""
    return bool(
        _SECTION_RE.match(s)
        or _SECTION_HYPHEN_RE.match(s)
        or _SECTION_ALPHA_RE.match(s)
        or _SECTION_ROMAN_RE.match(s)
    )


def _is_primary_section_header(s: str) -> bool:
    return bool(
        _SECTION_RE.match(s)
        or _SECTION_HYPHEN_PRIMARY_RE.match(s)
        or _SECTION_ALPHA_RE.match(s)
        or _SECTION_ROMAN_RE.match(s)
    )


def _has_formal_sections(tagged: list[tuple[SegmentType, str, int]]) -> bool:
    return any(
        _is_section_header(text.strip())
        for seg_type, text, _ in tagged
        if seg_type != "metadata"
    )


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
    alpha_as_subsection: bool = False,
) -> list[Segment]:
    """One segment per formal section; metadata stripped; preamble paragraphs merged.

    When split_subsections=True (default), top-level numbered items (1. 2. 3.) within a
    section start new sub-segments.  When False, everything within a formal section stays
    merged into one segment — useful for display/review where you want complete sections.
    Boilerplate detection still applies to standalone chunks outside formal sections.

    When alpha_as_subsection=True (set automatically for docs that use Roman numerals as
    primary section headers), A./B./C. alpha headers are treated as sub-headers within the
    current Roman numeral section rather than starting new top-level segments.  With
    split_subsections=True they each become their own sub-segment; with split_subsections=False
    they stay merged into the parent section.
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

        if seg_type == "vesting_clause":
            flush()
            segments.append(Segment(text, "vesting_clause", [idx]))
            current_type = "paragraph"
            continue

        # Determine what constitutes a "primary" section header for this document.
        # When alpha_as_subsection=True (Roman numeral docs), only Sec.N and Roman numeral
        # headers (including single I./V./X.) are primary.  A./B./C. are sub-headers.
        # When alpha_as_subsection=False, all formal section headers are primary.
        is_primary = (
            bool(_SECTION_RE.match(s) or _SECTION_HYPHEN_PRIMARY_RE.match(s) or _SECTION_ROMAN_ALL_RE.match(s))
            if alpha_as_subsection
            else _is_primary_section_header(s)
        )

        if is_primary:
            flush()
            current_chunks.append(text)
            current_indices.append(idx)
            current_type = "section"
            continue

        # A./B./C. sub-headers within a Roman numeral section.
        # split_subsections=True: each becomes its own sub-segment (for classification).
        # split_subsections=False: merged into the parent section (for display).
        if (alpha_as_subsection
                and _SECTION_ALPHA_RE.match(s)
                and not _SECTION_ROMAN_ALL_RE.match(s)
                and current_type == "section"):
            if (split_subsections
                    and current_chunks
                    and not _ends_incomplete(current_chunks[-1])):
                flush()
                current_chunks.append(text)
                current_indices.append(idx)
                # current_type stays "section"
            else:
                current_chunks.append(text)
                current_indices.append(idx)
            continue

        # Hyphen-coded subsections such as "1-101." belong under a top-level
        # "1-1." section. For classifier output they can split into their own
        # provisions; for display/review they remain merged with the parent.
        if _SECTION_HYPHEN_SUB_RE.match(s) and current_type == "section":
            if (split_subsections
                    and current_chunks
                    and not _ends_incomplete(current_chunks[-1])):
                flush()
                current_chunks.append(text)
                current_indices.append(idx)
            else:
                current_chunks.append(text)
                current_indices.append(idx)
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
    Bare N. items (1., 2., 3.) always start a new section regardless of length —
    they are top-level amendment/paragraph markers in amending orders and memos.
    """
    segments: list[Segment] = []
    current: list[tuple[str, int]] = []
    current_type: SegmentType = "paragraph"
    in_list_context = False    # True while accumulating struct items after a ':' introducer
    in_numbered_section = False  # True when current section started with a bare N. marker

    def flush():
        nonlocal in_list_context, in_numbered_section
        if current:
            segments.append(Segment(
                " ".join(t for t, _ in current),
                current_type,
                [i for _, i in current],
            ))
            current.clear()
        in_list_context = False
        in_numbered_section = False

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

        if seg_type == "vesting_clause":
            flush()
            segments.append(Segment(text, "vesting_clause", [idx]))
            current_type = "paragraph"
            continue

        # Bare N. item (1., 2., 3. …) → always start a new section regardless of length.
        # Checked before the long-struct-item and short-list-item paths so that N. items
        # used as top-level section markers (amending orders, numbered memos) are always
        # treated as section boundaries, not merged into the preceding paragraph.
        if _SECTION_NUMBERED_RE.match(s):
            flush()
            current.append((text, idx))
            current_type = "section"
            in_numbered_section = True
            continue

        if seg_type == "section":
            # Long standalone directive — but if the preceding content ends with ':' or
            # no punctuation, or we're already accumulating a list introduced by ':', keep
            # attaching rather than starting a new section segment.
            if current and (in_list_context or _ends_incomplete(" ".join(t for t, _ in current))):
                current.append((text, idx))
                in_list_context = True
            else:
                flush()
                current.append((text, idx))
                current_type = "section"
            continue

        # Short list item or short orphan: attach to current open segment
        if _is_list_item(s) or len(s) < 80:
            if current:
                if not in_list_context and _ends_incomplete(" ".join(t for t, _ in current)):
                    in_list_context = True
                current.append((text, idx))
            else:
                # Nothing open yet — start accumulating
                current.append((text, idx))
                current_type = "paragraph"
            continue

        # Substantive paragraph (not a list item, not short)
        if current_type == "section":
            if in_numbered_section:
                # Body of a numbered section (quoted regulation text, sub-item bodies, etc.)
                # — keep accumulating until the next N. marker or a metadata boundary.
                current.append((text, idx))
            else:
                # A new substantial paragraph after a long struct_item → flush, start fresh.
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
    Short orphans (<80 chars) attach forward to the next substantive chunk, or backward
    to the previous paragraph if no forward target exists.
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

    def emit_orphans():
        """Attach pending orphans to the previous paragraph, or emit as own paragraph."""
        if not pending_orphans:
            return
        if segments and segments[-1].seg_type == "paragraph":
            last = segments[-1]
            segments[-1] = Segment(
                last.text + " " + " ".join(t for t, _ in pending_orphans),
                "paragraph",
                last.chunk_indices + [i for _, i in pending_orphans],
            )
        else:
            segments.append(Segment(
                " ".join(t for t, _ in pending_orphans),
                "paragraph",
                [i for _, i in pending_orphans],
            ))
        pending_orphans.clear()

    for seg_type, text, idx in tagged:
        s = text.strip()

        if seg_type == "metadata":
            flush()
            emit_orphans()
            segments.append(Segment(text, "metadata", [idx]))
            current_type = "paragraph"
            continue

        if seg_type == "boilerplate":
            flush()
            emit_orphans()
            segments.append(Segment(text, "boilerplate", [idx]))
            current_type = "paragraph"
            continue

        if seg_type == "vesting_clause":
            flush()
            emit_orphans()
            segments.append(Segment(text, "vesting_clause", [idx]))
            current_type = "paragraph"
            continue

        # Short list item: emit as its own paragraph so each list element is codeable individually
        if _is_list_item(s):
            flush()
            emit_orphans()
            segments.append(Segment(text, "paragraph", [idx]))
            current_type = "paragraph"
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
    emit_orphans()
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
    strict_wp: bool = False,
) -> list[Segment]:
    """Segment a document's text into classifiable units.

    Args:
        doc_text: Raw document text from the CSV.
        doc_type: Optional document type hint (unused currently).
        split_subsections: When True (default), numbered items (1. 2. 3.) within a
            formal section each become their own segment.  Set to False to keep entire
            sections merged — useful for display/review.
        split_paragraphs: Deprecated. Documents without formal sections are segmented
            by ordering phrases.
            Has no effect on documents that have formal sections.
        strict_wp: When True, disable all extensions (section-only shall verbs,
            opening-authority vesting) and use only the original W&P phrase list.
    """
    raw_chunks = re.split(r"  +", doc_text)
    chunks = _resplit_embedded_sections(
        [c.strip() for c in raw_chunks if c.strip()]
    )
    total = len(chunks)

    ordering_re = _get_ordering_re(extended=False)  # W&P only for initial scan
    opening_authority = not strict_wp
    is_proclamation = doc_type == "proclamation"
    tagged: list[tuple[SegmentType, str, int]] = []
    for i, chunk in enumerate(chunks):
        is_last_n = i >= total - 5
        ct = _classify_chunk(chunk, i, total, is_last_n)
        # Metadata and boilerplate bypass the vesting carve-out — they are complete chunks
        # whose classification is already settled (mirrors segment_ordering() behavior).
        if ct not in ("metadata", "boilerplate") and _chunk_has_vesting(chunk, ordering_re, opening_authority=opening_authority, is_proclamation=is_proclamation):
            for piece, is_vesting in _carve_vesting(chunk, ordering_re, opening_authority=opening_authority, is_proclamation=is_proclamation):
                if is_vesting:
                    tagged.append(("vesting_clause", piece, i))
                else:
                    tagged.append((_classify_chunk(piece, i, total, is_last_n), piece, i))
        else:
            tagged.append((ct, chunk, i))

    has_sections = _has_formal_sections(tagged)
    # Docs with multi-char Roman numeral headers (II., III., …) use A./B./C. as sub-headers
    alpha_as_sub = any(
        bool(_SECTION_ROMAN_RE.match(text.strip()))
        for seg_type, text, _ in tagged
        if seg_type != "metadata"
    )

    if has_sections:
        segs = _group_by_sections(tagged, split_subsections=split_subsections,
                                  alpha_as_subsection=alpha_as_sub)
    else:
        segs = segment_ordering(doc_text, doc_type, strict_wp=strict_wp)

    segs = _merge_incomplete_paragraphs(segs)
    segs = _enforce_closing_cutoff(segs)
    segs = _enforce_signoff_cutoff(segs)
    segs = _reclassify_titles_before_metadata(segs)

    return segs


def _reclassify_sections_without_ordering_phrase(
    segs: list[Segment], ordering_re: re.Pattern
) -> list[Segment]:
    """Reclassify section segments that lack a W&P ordering phrase as preamble."""
    return [
        seg if seg.seg_type != "section" or ordering_re.search(seg.text)
        else Segment(seg.text, "preamble", seg.chunk_indices)
        for seg in segs
    ]


def _relabel_for_wp(segs: list[Segment], ordering_re: re.Pattern) -> list[Segment]:
    """Translate section-grouper labels into the W&P taxonomy.

    Paragraphs (pre-section introductory text):
      has ordering phrase  → ordering_phrase  (introductory, not a standalone directive)
      no ordering phrase   → preamble

    Sections (priority order):
      has boilerplate signal     → boilerplate
      default                    → order_action
    """
    result = []
    seen_action = False  # True once the first order_action section has been emitted

    for seg in segs:
        if seg.seg_type == "paragraph":
            if ordering_re.search(seg.text):
                # ordering_phrase only at the document opening (before any order_action
                # section); mid-document ordering paragraphs become order_action.
                new_type: SegmentType = "ordering_phrase" if not seen_action else "order_action"
            else:
                new_type = "order_action" if seen_action else "preamble"
            result.append(Segment(seg.text, new_type, seg.chunk_indices))

        elif seg.seg_type == "section":
            lower = seg.text.lower()
            _ends_law = lower.rstrip().rstrip('.').endswith("to the extent permitted by law")
            if ((_ends_law or any(signal in lower for signal in _BOILERPLATE_SIGNALS))
                    and not seg.text.rstrip().endswith(":")):
                new_type = "boilerplate"
            else:
                new_type = "order_action"
                seen_action = True
            result.append(Segment(seg.text, new_type, seg.chunk_indices))

        else:
            result.append(seg)

    return result


def _starts_with_list_marker(text: str) -> bool:
    """True if text begins with a structural list marker or bullet point.

    Used to guard against re-merging independently emitted list items.
    """
    s = text.lstrip()
    return bool(_STRUCT_ITEM_RE.match(s) or _BULLET_RE.match(s))


def _merge_incomplete_paragraphs(segs: list[Segment]) -> list[Segment]:
    """Merge a paragraph into the next if it ends with ':' or no terminal punctuation.

    A colon introduces what follows; alphanumeric endings indicate a fragment or title.
    Both mean the next paragraph is semantically part of the same unit.
    Only merges paragraph→paragraph; does not cross metadata or boilerplate boundaries.
    List-marked paragraphs (e.g. "(1) item text") are never merged — they are intentionally
    standalone even when preceded by an introducer ending with ':'.
    """
    result = list(segs)
    i = 0
    while i < len(result) - 1:
        seg = result[i]
        nxt = result[i + 1]
        if (seg.seg_type == "paragraph"
                and nxt.seg_type == "paragraph"
                and _ends_incomplete(seg.text)
                and not _starts_with_list_marker(seg.text)
                and not _starts_with_list_marker(nxt.text)):
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


def _reclassify_titles_before_metadata(segs: list[Segment]) -> list[Segment]:
    """Reclassify short title-like paragraphs that immediately precede a metadata segment.

    A sub-title or annex header that sits just before a Subject: line, dateline, or other
    metadata marker is itself metadata, not classifiable content.
    """
    result = list(segs)
    for i in range(len(result) - 1):
        seg = result[i]
        nxt = result[i + 1]
        if (seg.seg_type == "paragraph"
                and nxt.seg_type == "metadata"
                and len(seg.text.strip()) < 200
                and _ends_incomplete(seg.text)):
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
        if seg.seg_type in ("metadata", "boilerplate", "vesting_clause"):
            flush_content()
            result.append(seg)
        else:
            content_texts.append(seg.text)
            content_indices.extend(seg.chunk_indices)

    flush_content()
    return result


# ---------------------------------------------------------------------------
# Woolley & Peters ordering-phrase strategy
# ---------------------------------------------------------------------------

# Additional high-confidence directive verbs used by the extended W&P strategy.
# These supplement the original W&P phrase list for every document, regardless of
# whether the document has formal section headings.  The comma-delimited branch
# captures constructions such as ``shall, within 90 days, take`` without allowing
# the match to cross a sentence/semicolon boundary or span more than 160 characters.
_SHALL_ACTION_VERBS = (
    r"(?:take|develop|designate|establish|perform|make|issue|identify|prepare|"
    r"implement|determine|recommend|prescribe|seek|assist)"
)
_SHALL_COMMA_INTERVENING_MAX = 160
_SECTION_SHALL_ACTION = (
    r"shall(?:"
    r"\s+(?:(?:also|promptly|immediately)\s+){0,2}" + _SHALL_ACTION_VERBS +
    r"|\s*,\s*[^.;]{1," + str(_SHALL_COMMA_INTERVENING_MAX) + r"},\s*" +
    _SHALL_ACTION_VERBS +
    r")\b"
)


# Import phrase list lazily so the module loads even if ordering_phrases.py is absent.
def _build_ordering_re(section_extensions: bool = False) -> re.Pattern:
    from ordering_phrases import ORDERING_PHRASES, CURATED_OUT
    active = [p for p in ORDERING_PHRASES if p not in CURATED_OUT]
    # Sort longest-first so more-specific phrases win over shorter prefixes.
    active.sort(key=len, reverse=True)
    phrase_alt = "|".join(re.escape(p) for p in active)

    if not section_extensions:
        return re.compile(r"\b(" + phrase_alt + r")", re.IGNORECASE)

    return re.compile(
        r"\b(" + phrase_alt + r"|" + _SECTION_SHALL_ACTION + r")",
        re.IGNORECASE,
    )


_ordering_re_cache: re.Pattern | None = None           # W&P phrases only
_ordering_re_extended_cache: re.Pattern | None = None  # W&P + allowlisted shall verbs


def _get_ordering_re(extended: bool = False) -> re.Pattern:
    """Return the ordering-phrase regex.

    extended=False (default): pure W&P phrase list, used by strict_wp mode.
    extended=True: adds the allowlisted shall + verb pattern for the extended
        W&P strategy.
    """
    global _ordering_re_cache, _ordering_re_extended_cache
    if extended:
        if _ordering_re_extended_cache is None:
            _ordering_re_extended_cache = _build_ordering_re(section_extensions=True)
        return _ordering_re_extended_cache
    else:
        if _ordering_re_cache is None:
            _ordering_re_cache = _build_ordering_re(section_extensions=False)
        return _ordering_re_cache


# Sentence boundary: terminal punctuation followed by whitespace and a capital letter or "(".
# The two-char negative lookbehind (?<![A-Z]\.) blocks splitting after single-capital-letter
# abbreviations like "T.", "R.", "U.", "C." (covers "Robert T. Stafford", "U.S.C.", etc.).
# Does not protect lowercase abbreviations like "Jr." or "Mr." — acceptable for a viewer.
_SENT_SPLIT_RE = re.compile(r"(?<![A-Z]\.)(?<=[.!?])\s+(?=[A-Z(])")

# Intra-sentence punctuation used as a cut point just before an ordering phrase.
# Hyphen excluded to avoid splitting hyphenated words.
_PUNCT_RE = re.compile(r"[,;:—–]")

# High-confidence authority-invocation markers: the sentence IS an authority citation
# even when no ordering phrase follows.
_STRONG_VESTING_RE = re.compile(
    r"vested\s+in\s+(?:me|my(?=\s+by\b))"
    r"|by\s+virtue\s+of\s+the\s+authority"
    r"|by\s+virtue\s+of\s+and\s+pursuant\s+to\s+the\s+authority\s+vested\s+in\s+the\s+President"
    r"|by\s+virtue\s+of\s+my\s+authority\s+as\s+President\b"
    r"|pursuant\s+to\s+my\s+authority\s+(?:"
    r"to\s+regulate\s+federal\s+employment\b"
    r"|under\s+subsection\s+\d)",
    re.IGNORECASE,
)

_REVIEWED_COMMANDER_AUTHORITY_RE = re.compile(
    r"pursuant\s+to\s+my\s+authority\s+as\s+Commander\s+in\s+Chief"
    r"(?=,\s+I\s+hereby\s+(?:approve|rescind)\b)",
    re.IGNORECASE,
)

_INLINE_VESTING_RE = re.compile(
    r"\b(?:by\s+virtue\s+of\s+|by\s+)?the\s+authority\s+vested\s+in\s+"
    r"(?:me|my(?=\s+by\b))\b",
    re.IGNORECASE,
)

# Additional strong markers that apply only to proclamations.  Congressional joint
# resolutions and Public Law citations signal authority invocations in proclamations
# but are mere references in memos, EOs, and letters.
_PROC_VESTING_RE = re.compile(
    r"joint\s+resolution|public\s+law\b",
    re.IGNORECASE,
)

# Conditional authority markers: only create a vesting_clause carve-out when an
# ordering phrase also appears in the same sentence.
#   "now, therefore, i" — standard proclamation invocation formula
#   "pursuant to" — cite-authority prefix, qualified by a law citation
_CONDITIONAL_VESTING_RE = re.compile(
    r"\bnow,?\s+therefore,?\s+i\b",
    re.IGNORECASE,
)

# "Pursuant to" prefix used as a law-citation anchor for has_vesting
# and as an authority-marker anchor for _vesting_marker_end.
_PURSUANT_RE = re.compile(r"\bpursuant\s+to\b", re.IGNORECASE)

# First-person presidential reference.  Required alongside _PURSUANT_RE + an authority citation
# to avoid tagging cabinet-delegation sentences ("The Secretary of State … shall…") as
# vesting clauses.  True presidential authority sentences always use "I" as the actor.
_PRESIDENTIAL_I_RE = re.compile(r"\bI\b")

# Sentence-opening statutory authority citation.  "Pursuant to section X", "Under section Z"
# at the START of a sentence (checked via re.match) — indicates the sentence is an authority
# invocation regardless of whether an ordering phrase follows.  "Consistent with" is excluded:
# it signals non-disagreement with a law, not that the law authorizes the action.
_OPENING_AUTHORITY_RE = re.compile(
    r"(?:pursuant\s+to|under\s+(?:section|title|the\s+authority))",
    re.IGNORECASE,
)

# Law-citation anchor for "consistent with" / "pursuant to" qualification.
# Matches specific statutory/constitutional references; excludes vague terms like
# "applicable law" or "existing policy".
_LAW_CITATION_RE = re.compile(
    r"\b(?:"
    r"[Ss]ubsections?\s+\d"                  # "subsection 405(b)(1)"
    r"|[Ss]ection\s+\d"                      # "section 110", "Section 506A"
    r"|\d+\s+U\.S\.C\."                       # "22 U.S.C."
    r"|[Tt]itle\s+\d"                         # "Title 10"
    r"|[Cc]hapter\s+\d"                       # "Chapter 15"
    r"|[Pp]ublic\s+[Ll]aw"                    # "Public Law 106-386"
    r"|the\s+Constitution\b"                   # "the Constitution"
    r"|laws?\s+of\s+the\s+United\s+States"    # "laws of the United States"
    r"|statutes?\s+of\s+the\s+United\s+States"
    r"|[A-Z]\w+\s+Act\b"                      # "Trade Act", "USIFTA Act"
    r")"
)

_AUTHORITY_CITATION_RE = re.compile(
    _LAW_CITATION_RE.pattern
    + r"|\bmy\s+constitutional\s+authority\b",
    re.IGNORECASE,
)

# Text after an internal comma that remains part of the same statutory citation.  This lets
# inline vesting carve-outs span citation components without depending on a particular Act or
# directive's wording.
_CITATION_CONTINUATION_RE = re.compile(
    r"(?:"
    r"\d{4}\b"                              # "Act, 2020"
    r"|as\s+amended\b"                      # "Act of 1962, as amended"
    r"|\d+\s+U\.S\.C\."                     # "22 U.S.C. 2601"
    r"|United\s+States\s+Code\b"            # "title 5, United States Code"
    r"|\d+\s+Stat\."                        # "74 Stat. 898"
    r"|Public\s+Law\b|Pub\.\s*L\."          # Public Law references
    r"|\((?:\d+|H\.?R\.?|S\.\s*\d)"        # parenthetical citation components
    r"|(?:and|or)\s+(?:section|title|chapter|\d+\s+U\.S\.C\.)\b"
    r")",
    re.IGNORECASE,
)


def _vesting_marker_end(sent: str, limit: int, is_proclamation: bool = False) -> int:
    """End offset of the last authority-invocation marker at or before *limit*.

    Used to anchor the vesting/directive cut search: by starting the punctuation
    search after the last authority marker we avoid picking up the invocation comma
    (e.g. "…President of the United States of America,") as the cut point when no
    comma appears between the authority citation and the ordering phrase.
    Returns 0 when no qualifying marker precedes *limit*.
    """
    ends = [0]
    patterns = (
        _STRONG_VESTING_RE,
        _REVIEWED_COMMANDER_AUTHORITY_RE,
        _CONDITIONAL_VESTING_RE,
        _PURSUANT_RE,
    )
    if is_proclamation:
        patterns = patterns + (_PROC_VESTING_RE,)
    for rgx in patterns:
        ends += [am.end() for am in rgx.finditer(sent) if am.end() <= limit]
    return max(ends)


def _split_sentences(text: str) -> list[str]:
    """Split text on terminal punctuation outside parenthetical citations."""
    sentences = []
    start = scan_start = depth = 0
    for boundary in _SENT_SPLIT_RE.finditer(text):
        for char in text[scan_start:boundary.start()]:
            if char == "(":
                depth += 1
            elif char == ")":
                depth = max(0, depth - 1)
        scan_start = boundary.end()
        if depth:
            continue
        sentences.append(text[start:boundary.start()])
        start = boundary.end()
    sentences.append(text[start:])
    return [sentence for sentence in sentences if sentence.strip()]


def _inline_pursuant_start(sent: str, ordering_re: re.Pattern) -> int | None:
    """Return a presidential mid-sentence statutory ``pursuant to`` citation's start.

    Requiring both a preceding ordering phrase and first-person presidential actor keeps
    cabinet instructions such as "The Secretary shall, pursuant to section 5" from being
    treated as the President's vesting clause.
    """
    for match in _PURSUANT_RE.finditer(sent):
        preceding = sent[:match.start()]
        if (
            ordering_re.search(preceding)
            and (
                _PRESIDENTIAL_I_RE.search(preceding)
                or re.search(r"\bit\s+is\s+hereby,?\s+ordered\b", preceding, re.I)
            )
            and _AUTHORITY_CITATION_RE.search(sent, match.end())
        ):
            return match.start()
    return None


def _pursuant_authority_action_start(sent: str, ordering_re: re.Pattern) -> int | None:
    """Return a mid-sentence ``pursuant to`` citation before a reviewed presidential action."""
    start = None
    for match in _PURSUANT_RE.finditer(sent):
        action = ordering_re.search(sent, match.end())
        if not action:
            continue
        action_text = sent[action.start():action.start() + 40]
        if not re.match(r"I\s+(?:hereby\s+)?(?:determine|exempt)\b", action_text, re.I):
            continue
        intervening = sent[match.end():action.start()]
        if re.search(r"\b(?:consistent\s+with|in\s+accordance\s+with|in\s+response\s+to)\b", intervening, re.I):
            continue
        if _AUTHORITY_CITATION_RE.search(sent, match.end(), action.start()):
            start = match.start()
    return start


def _inline_vesting_start(sent: str, ordering_re: re.Pattern) -> int | None:
    """Return a post-ordering first-person vesting invocation's start."""
    for match in _INLINE_VESTING_RE.finditer(sent):
        preceding = sent[:match.start()]
        if ordering_re.search(preceding) and _PRESIDENTIAL_I_RE.search(preceding):
            return match.start()
    return None


def _carve_inline_pursuant(
    pieces: list[tuple[str, "SegmentType | None"]], ordering_re: re.Pattern
) -> list[tuple[str, "SegmentType | None"]]:
    """Carve a trailing mid-sentence statutory citation from an order-action piece."""
    result: list[tuple[str, "SegmentType | None"]] = []
    for text, seg_type in pieces:
        starts = (
            [_inline_pursuant_start(text, ordering_re), _inline_vesting_start(text, ordering_re)]
            if seg_type == "order_action"
            else []
        )
        start = min((value for value in starts if value is not None), default=None)
        if start is None:
            result.append((text, seg_type))
            continue
        directive = text[:start].strip()
        suffix = text[start:]
        end = len(suffix)
        for comma in re.finditer(r",", suffix):
            following = suffix[comma.end():].lstrip()
            if not following or not _CITATION_CONTINUATION_RE.match(following):
                end = comma.end()
                break
        citation = suffix[:end].strip()
        remainder = suffix[end:].strip()
        if directive:
            result.append((directive, seg_type))
        if citation:
            result.append((citation, "vesting_clause"))
        if remainder:
            result.append((remainder, seg_type))
    return result


def _opening_authority_cut(sent: str) -> int | None:
    """Return the end offset of a sentence-opening authority citation.

    Handles "Pursuant to section X ..., [operative text]" sentences that have no
    W&P ordering phrase.  Citation-internal commas are skipped until the following
    text no longer looks like a citation continuation.
    """
    if not _OPENING_AUTHORITY_RE.match(sent.lstrip()):
        return None
    for comma in re.finditer(r",", sent):
        prefix = sent[:comma.end()]
        if not _AUTHORITY_CITATION_RE.search(prefix):
            continue
        following = sent[comma.end():].lstrip()
        if following and _CITATION_CONTINUATION_RE.match(following):
            continue
        return comma.end()
    return None


def _segment_sentence(
    sent: str, ordering_re: re.Pattern, opening_authority: bool = True,
    is_proclamation: bool = False,
) -> list[tuple[str, "SegmentType | None"]]:
    """Split a sentence into (text, start_type) pieces for the W&P strategy.

    start_type is 'vesting_clause', 'directive', or None (continue the open segment).

    Rules:
    - If the sentence contains an authority-invocation marker, the text *before* the first
      ordering phrase is carved out as a vesting_clause piece; the remainder (starting at
      the punctuation cut before the ordering phrase) becomes a directive piece.
    - Authority markers come in two strengths:
        Strong ("vested in me", "by virtue of the authority"): the sentence is tagged
          vesting_clause even when no ordering phrase is present.
        Conditional ("now, therefore, i"; "pursuant to" + law citation):
          only creates a vesting_clause carve-out when an ordering phrase also appears.
    - For every ordering phrase after the first, we cut at the nearest punctuation mark
      before that phrase (within the span since the previous phrase ended); if none exists,
      we cut immediately before the phrase.
    - A sentence with a single ordering phrase and no authority marker returns
      [(sent, 'directive')].
    """
    lower = sent.lower()
    matches = list(ordering_re.finditer(sent))
    # Restrict authority-marker detection to the text before the first ordering phrase.
    # This prevents post-phrase citations like "I hereby order, by the authority vested in
    # me…" from triggering a spurious vesting carve-out of the contextual prefix.
    prefix = sent[:matches[0].start()] if matches else sent
    # A sentence that OPENS with "Pursuant to / Under section [law]"
    # is a statutory authority invocation — treat as strong vesting when extensions are on.
    _sentence_opens_with_authority = (
        opening_authority
        and bool(_OPENING_AUTHORITY_RE.match(sent.lstrip()))
        and bool(_AUTHORITY_CITATION_RE.search(sent))
    )
    has_strong_vesting = (
        bool(_STRONG_VESTING_RE.search(prefix))
        or bool(_REVIEWED_COMMANDER_AUTHORITY_RE.search(sent))
        or (is_proclamation and bool(_PROC_VESTING_RE.search(prefix)))
        or _sentence_opens_with_authority
    )
    has_vesting = has_strong_vesting or bool(
        _CONDITIONAL_VESTING_RE.search(prefix)
        or _pursuant_authority_action_start(sent, ordering_re) is not None
        or (
            _PURSUANT_RE.search(prefix)
            and _AUTHORITY_CITATION_RE.search(prefix)
            and _PRESIDENTIAL_I_RE.search(prefix)
        )
    )

    if not matches:
        # Strong markers → the sentence itself is the authority citation.
        # Conditional markers only create a carve-out when an ordering phrase follows.
        if _sentence_opens_with_authority:
            cut = _opening_authority_cut(sent)
            if cut is not None and cut < len(sent):
                return [
                    (sent[:cut].strip(), "vesting_clause"),
                    (sent[cut:].strip(), None),
                ]
        return [(sent, "vesting_clause" if has_strong_vesting else None)]

    # Build cut positions.  Each cut is the index in `sent` where a new piece starts.
    # We need a cut before the first match only when a vesting prefix needs to be carved out.
    cuts: list[int] = []
    for i, m in enumerate(matches):
        if i == 0 and not has_vesting:
            # First phrase, no vesting prefix — no cut needed before it.
            continue
        # Search for punctuation between the anchor and the start of this match.
        # For directive↔directive splits (i > 0): anchor at end of previous phrase.
        # For the vesting carve-out (i == 0): anchor at the end of the last
        # authority-invocation marker so we don't mistake the invocation comma
        # (e.g. "…President of the United States of America,") for the cut point.
        if i > 0:
            win_start = matches[i - 1].end()
        else:
            win_start = _vesting_marker_end(sent, m.start(), is_proclamation=is_proclamation)
        window = sent[win_start : m.start()]
        pm = list(_PUNCT_RE.finditer(window))
        if pm:
            cut_pos = win_start + pm[-1].end()
            # "including <statutory citation>" after the comma is a continuation of the
            # authority citation, not the start of a new directive clause — extend the
            # vesting prefix to right before the ordering phrase.
            after_cut = sent[cut_pos : m.start()].lstrip()
            cuts.append(
                m.start() if after_cut.lower().startswith("including ") else cut_pos
            )
        else:
            cuts.append(m.start())

    if not cuts:
        # Single ordering phrase, no vesting prefix — the whole sentence is one directive.
        return _carve_inline_pursuant([(sent, "order_action")], ordering_re)

    bounds = [0, *cuts, len(sent)]
    result: list[tuple[str, "SegmentType | None"]] = []
    for i in range(len(bounds) - 1):
        piece = sent[bounds[i] : bounds[i + 1]].strip()
        if not piece:
            continue
        seg_type: "SegmentType | None" = "vesting_clause" if (has_vesting and i == 0) else "order_action"
        result.append((piece, seg_type))
    return _carve_inline_pursuant(result, ordering_re)


def _chunk_has_vesting(chunk: str, ordering_re: re.Pattern, opening_authority: bool = True,
                       is_proclamation: bool = False) -> bool:
    """True if the chunk contains an authority-invocation marker that warrants a carve-out.

    Mirrors the has_vesting logic in _segment_sentence, evaluated at chunk level so that
    segment() can apply the same cutoff as segment_ordering().
    Strong markers ('vested in me', 'by virtue of the authority') trigger unconditionally;
    conditional markers ('now, therefore, I'; 'pursuant to' + law citation)
    only trigger when an ordering phrase is also present in the chunk.

    Opening marker searches are restricted to the text before the first ordering phrase.
    Separately, tightly scoped inline rules recognize presidential authority citations that
    immediately follow an ordering phrase.
    """
    first_match = ordering_re.search(chunk)
    prefix = chunk[:first_match.start()] if first_match else chunk
    if _STRONG_VESTING_RE.search(prefix):
        return True
    if _REVIEWED_COMMANDER_AUTHORITY_RE.search(chunk):
        return True
    if is_proclamation and _PROC_VESTING_RE.search(prefix):
        return True
    if opening_authority and any(
        _OPENING_AUTHORITY_RE.match(s.lstrip()) and _AUTHORITY_CITATION_RE.search(s)
        for s in (_split_sentences(chunk) or [chunk])
    ):
        return True
    if any(
        _inline_pursuant_start(s, ordering_re) is not None
        or _inline_vesting_start(s, ordering_re) is not None
        or _pursuant_authority_action_start(s, ordering_re) is not None
        for s in (_split_sentences(chunk) or [chunk])
    ):
        return True
    has_cond = bool(
        _CONDITIONAL_VESTING_RE.search(prefix)
        or (
            _PURSUANT_RE.search(prefix)
            and _AUTHORITY_CITATION_RE.search(prefix)
            and _PRESIDENTIAL_I_RE.search(prefix)
        )
    )
    return has_cond and bool(first_match)


def _carve_vesting(chunk: str, ordering_re: re.Pattern, opening_authority: bool = True,
                   is_proclamation: bool = False) -> list[tuple[str, bool]]:
    """Split a chunk into ordered (text, is_vesting) pieces using the W&P sentence carve.

    Non-vesting pieces (directive/None from _segment_sentence) are coalesced so that the
    structural grouper — not the ordering phrases — controls content granularity.
    """
    pieces: list[tuple[str, bool]] = []
    for sent in _split_sentences(chunk) or [chunk]:
        for text, start_type in _segment_sentence(sent, ordering_re, opening_authority=opening_authority,
                                                  is_proclamation=is_proclamation):
            pieces.append((text, start_type == "vesting_clause"))
    # Coalesce consecutive content pieces; vesting pieces are always kept standalone.
    coalesced: list[tuple[str, bool]] = []
    for text, is_v in pieces:
        if coalesced and not is_v and not coalesced[-1][1]:
            coalesced[-1] = (coalesced[-1][0] + " " + text, False)
        else:
            coalesced.append((text, is_v))
    return coalesced


# Matches the four list-marker families used in presidential documents.
# Group 1 captures the whole marker so we can detect the family.
_LIST_MARKER_RE = re.compile(
    r"(?<!\S)(\(\d+\)|\([a-z]\)|\([ivxlcdm]+\)|\d+\.)\s",
    re.IGNORECASE,
)

# Detects a sentence boundary inside a colon-list header: period followed by
# whitespace and an uppercase letter indicates multiple sentences ("intervening
# sections") between the ordering phrase and the colon.
_SENTENCE_BREAK_RE = re.compile(r"\.\s+[A-Z]")

# Family patterns — ordered most-specific first so roman doesn't eat letters.
_MARKER_FAMILIES: list[tuple[str, re.Pattern]] = [
    ("paren_digit",  re.compile(r"^\(\d+\)\s")),
    ("paren_roman",  re.compile(r"^\([ivxlcdm]+\)\s", re.IGNORECASE)),
    ("paren_alpha",  re.compile(r"^\([a-z]\)\s", re.IGNORECASE)),
    ("digit_dot",    re.compile(r"^\d+\.\s")),
]


def _detect_family(marker: str) -> str | None:
    """Return the family name for a single matched marker string."""
    for name, pat in _MARKER_FAMILIES:
        if pat.match(marker):
            return name
    return None


# Fixed legal-outline depth hierarchy:
#   Section N. / N.  → 0   (top-level numbered section)
#   (a)              → 1   (lettered subsection)
#   (1)              → 2   (numbered sub-item)
#   (i)/(ii)/…       → 3   (roman-numeral sub-sub-item)
# roman is checked BEFORE alpha so "(i)" reads as depth-3, not depth-1.
_DEPTH_PATTERNS: list[tuple[int, re.Pattern]] = [
    (0, re.compile(r"^(?:Section|Sec\.)\s+\d+[.\s]", re.IGNORECASE)),
    (0, re.compile(r"^\d+\.\s")),
    (3, re.compile(r"^\([ivxlcdm]+\)\s", re.IGNORECASE)),
    (1, re.compile(r"^\([a-z]\)\s", re.IGNORECASE)),
    (2, re.compile(r"^\(\d+\)\s")),
]


def _marker_depth(text: str) -> int | None:
    """Return the outline depth of segment text based on its leading marker, or None."""
    t = text.lstrip()
    for depth, pat in _DEPTH_PATTERNS:
        if pat.match(t):
            return depth
    return None


def _merge_sublists(segments: list[Segment]) -> list[Segment]:
    """Merge order_action (and deeper ordering_phrase) sub-items into their parent.

    An order_action or ordering_phrase whose leading marker is at a *greater* depth than
    the most recent emitted order_action is absorbed into that parent rather than emitted
    as a new segment.  This reassembles e.g.:

        order_action  "5. General Provisions."      depth 0
        ordering_phrase "(a) … (b) … affect:"       depth 1 → merged into #5
        order_action  "(i) the authority…"           depth 3 → merged into #5
        order_action  "(ii) the functions…"          depth 3 → merged into #5

    Segments whose type is neither order_action nor ordering_phrase (metadata, boilerplate,
    vesting_clause, preamble) always emit standalone and clear the current parent so merges
    never cross structural boundaries.

    ordering_phrase segments with NO leading marker (top-level list openers such as
    "it is hereby ordered as follows:") always emit standalone and clear the parent.
    """
    result: list[Segment] = []
    last_oa_idx: int | None = None   # index into result of the most recent order_action

    def _merge_into_parent(child: Segment) -> None:
        """Absorb child into result[last_oa_idx], keeping type=order_action."""
        parent = result[last_oa_idx]
        new_indices = parent.chunk_indices + [
            ci for ci in child.chunk_indices if ci not in parent.chunk_indices
        ]
        result[last_oa_idx] = Segment(
            parent.text + " " + child.text, "order_action", new_indices
        )

    for seg in segments:
        if seg.seg_type not in ("order_action", "ordering_phrase"):
            result.append(seg)
            last_oa_idx = None
            continue

        current_depth = _marker_depth(seg.text)

        if seg.seg_type == "ordering_phrase":
            if last_oa_idx is None or current_depth is None:
                # Top-level header (e.g. "it is hereby ordered as follows:") — standalone.
                result.append(seg)
                last_oa_idx = None
            else:
                parent_depth = _marker_depth(result[last_oa_idx].text)
                if parent_depth is not None and current_depth > parent_depth:
                    # Sub-item opener (e.g. "(a)…affect:") — absorb into parent.
                    _merge_into_parent(seg)
                    # last_oa_idx stays; subsequent (i)/(ii) will also merge in.
                else:
                    # Same/shallower level — emit standalone, clear parent.
                    result.append(seg)
                    last_oa_idx = None
            continue

        # seg.seg_type == "order_action"
        if last_oa_idx is None or current_depth is None:
            last_oa_idx = len(result)
            result.append(seg)
            continue

        parent = result[last_oa_idx]
        parent_depth = _marker_depth(parent.text)

        if parent_depth is not None and current_depth > parent_depth:
            _merge_into_parent(seg)
        else:
            last_oa_idx = len(result)
            result.append(seg)

    return result


_ORDERING_PHRASE_MAX_CHARS = 80


def _split_colon_lists(segments: list[Segment], ordering_re: re.Pattern | None = None) -> list[Segment]:
    """Split order_action segments that contain a colon-introduced list.

    Fix A: the header portion (text up through the colon) is only labeled
    'ordering_phrase' when it is <= _ORDERING_PHRASE_MAX_CHARS chars; longer headers
    stay 'order_action' (they are substantive directives, not mere lead-in phrases).

    Fix B: a short order_action (<= _ORDERING_PHRASE_MAX_CHARS chars total) that
    contains a colon is labeled 'ordering_phrase' outright, regardless of whether
    2+ list-item markers follow.  This catches phrases like "it is ordered as
    follows: SECTION 1." that the marker regex does not match.

    For segments that do contain a colon followed by 2+ same-family markers:
    - header (text up to colon inclusive) → 'ordering_phrase' if <= max chars, else
      'order_action'
    - each list item → 'order_action'

    When ordering_re is provided, a colon-list is only split if at least one of its
    items contains a W&P ordering phrase.  Lists whose items are purely quoted content
    (e.g. numbered sub-paragraphs in an amending order) are left whole.
    """
    result: list[Segment] = []
    for seg in segments:
        if seg.seg_type != "order_action":
            result.append(seg)
            continue

        colon_pos = seg.text.find(":")
        if colon_pos == -1:
            result.append(seg)
            continue

        # Fix B: short whole-segment with a colon → ordering_phrase immediately.
        if len(seg.text) <= _ORDERING_PHRASE_MAX_CHARS:
            result.append(Segment(seg.text, "ordering_phrase", seg.chunk_indices))
            continue

        after_colon = seg.text[colon_pos + 1:]

        # Find all markers in the text after the colon and detect the dominant family.
        matches = list(_LIST_MARKER_RE.finditer(after_colon))
        if len(matches) < 2:
            result.append(seg)
            continue

        family = _detect_family(matches[0].group(1) + " ")
        if family is None:
            result.append(seg)
            continue

        # Section-numbered lists (1. 2. 3.) are structural sections — do not split.
        if family == "digit_dot":
            result.append(seg)
            continue

        # Collect only split points that belong to the detected family.
        family_pat = next(pat for name, pat in _MARKER_FAMILIES if name == family)
        split_points = [m.start() for m in matches if family_pat.match(m.group(0))]
        if len(split_points) < 2:
            result.append(seg)
            continue

        header_text = seg.text[: colon_pos + 1].strip()

        # If the header spans multiple sentences the colon is not directly
        # following the ordering phrase — there are intervening sections.
        # Keep the segment whole rather than splitting out the list items.
        if _SENTENCE_BREAK_RE.search(header_text):
            result.append(seg)
            continue

        # Only split when at least one item carries an ordering phrase.  Lists
        # whose items are purely quoted content (e.g. numbered sub-paragraphs in
        # an amending order) should stay grouped under their parent directive.
        if ordering_re is not None:
            item_texts = []
            for k, sp in enumerate(split_points):
                end = split_points[k + 1] if k + 1 < len(split_points) else len(after_colon)
                item_texts.append(after_colon[sp:end].strip())
            if not any(ordering_re.search(t) for t in item_texts):
                result.append(seg)
                continue

        # Fix A: only label header 'ordering_phrase' when it is short enough.
        header_type: SegmentType = (
            "ordering_phrase" if len(header_text) <= _ORDERING_PHRASE_MAX_CHARS
            else "order_action"
        )
        result.append(Segment(header_text, header_type, seg.chunk_indices))

        # Emit each list item.
        for k, sp in enumerate(split_points):
            end = split_points[k + 1] if k + 1 < len(split_points) else len(after_colon)
            item_text = after_colon[sp:end].strip()
            if item_text:
                result.append(Segment(item_text, "order_action", seg.chunk_indices))

    return result


def _merge_short_fragments(segments: list[Segment]) -> list[Segment]:
    """Merge a dangling short order_action fragment into the following order_action.

    Handles cases like "do hereby" (9 chars) that become isolated when two
    adjacent ordering phrases ('do hereby' and 'call upon') both trigger splits
    on what is grammatically a single directive.  A fragment is detected by
    being short (<= 30 chars) and not ending with sentence-closing punctuation.
    """
    _FRAGMENT_MAX = 30
    result: list[Segment] = []
    for seg in segments:
        if (
            result
            and result[-1].seg_type == "order_action"
            and seg.seg_type == "order_action"
            and len(result[-1].text) <= _FRAGMENT_MAX
            and not result[-1].text.rstrip().endswith((".", "!", "?", ";", ":"))
        ):
            prev = result.pop()
            merged_indices = prev.chunk_indices[:]
            for ci in seg.chunk_indices:
                if ci not in merged_indices:
                    merged_indices.append(ci)
            result.append(Segment(
                prev.text.rstrip() + " " + seg.text.lstrip(),
                "order_action",
                merged_indices,
            ))
        else:
            result.append(seg)
    return result


_INTERRUPTED_DETERMINATION_RE = re.compile(
    r"^I\s+(?:further\s+)?determine\s*,\s*$",
    re.IGNORECASE,
)
_DETERMINATION_CONTINUATION_RE = re.compile(r"^(?:that|whether)\b", re.IGNORECASE)


def _relabel_interrupted_determination_connectors(
    segments: list[Segment],
) -> list[Segment]:
    """Do not code a vesting-interrupted ``I determine,`` as its own action.

    In ``I determine, pursuant to section X, that ...``, authority carving
    produces a connector, a vesting clause, and the substantive continuation.
    Preserve those splits while making the connector an unnumbered ordering
    phrase rather than an independently classifiable action.
    """
    result = segments[:]
    for index in range(len(result) - 2):
        connector, vesting, continuation = result[index : index + 3]
        if (
            connector.seg_type == "order_action"
            and _INTERRUPTED_DETERMINATION_RE.fullmatch(connector.text)
            and vesting.seg_type == "vesting_clause"
            and continuation.seg_type == "order_action"
            and _DETERMINATION_CONTINUATION_RE.match(continuation.text)
            and bool(set(connector.chunk_indices) & set(vesting.chunk_indices))
            and bool(set(vesting.chunk_indices) & set(continuation.chunk_indices))
        ):
            result[index] = Segment(
                connector.text, "ordering_phrase", connector.chunk_indices[:]
            )
    return result


def segment_ordering(doc_text: str, doc_type: str = "", strict_wp: bool = False) -> list[Segment]:
    """Segment a document using the Woolley & Peters ordering-phrase strategy.

    Each ordering phrase starts a new 'directive' segment.  When a sentence contains
    multiple ordering phrases, it is split at the nearest punctuation mark before each
    subsequent phrase (or immediately before the phrase when no punctuation exists).

    Text before the first ordering phrase becomes a 'preamble' segment.

    Chunks that look like metadata (headers, subject lines, signatures, datelines) are tagged
    'metadata' using the same _classify_chunk() logic as the Section/Paragraph strategy.
    The vesting-clause prefix ("By the authority vested in me … ,") is carved out of the
    sentence that contains the first ordering phrase and tagged 'vesting_clause'.

    Numbered/lettered list items (e.g. (1), (a), 1.) following an open directive are
    grouped into it only when they contain no ordering phrase of their own; list items
    that do contain an ordering phrase are processed normally and start a new directive.

    Formal section boundaries do not control this strategy.  The same extended
    ordering-phrase matcher is applied across documents with and without sections.

    strict_wp=True disables all extensions (allowlisted shall verbs, opening-authority vesting)
    and uses only the original W&P phrase list.

    Returns a list of Segment objects with seg_type in
    {'preamble', 'order_action', 'metadata', 'boilerplate', 'vesting_clause'}.
    """
    ordering_re = _get_ordering_re(extended=not strict_wp)
    opening_authority = not strict_wp
    is_proclamation = doc_type == "proclamation"

    raw_chunks = re.split(r"  +", doc_text)
    chunks = _resplit_embedded_sections(
        [c.strip() for c in raw_chunks if c.strip()]
    )
    total = len(chunks)

    # Ordering-phrase strategy for every document; section headings are ordinary
    # surrounding text rather than segmentation boundaries.
    segments: list[Segment] = []
    current_parts: list[str] = []   # text pieces for the open segment
    current_indices: list[int] = [] # original chunk indices
    current_type: SegmentType = "preamble"

    def flush() -> None:
        if current_parts:
            text = " ".join(current_parts)
            segments.append(Segment(text, current_type, current_indices[:]))
            current_parts.clear()
            current_indices.clear()

    for chunk_idx, chunk in enumerate(chunks):
        # Metadata and boilerplate chunks: flush the open segment and emit standalone.
        is_last_n = chunk_idx >= total - 5
        chunk_type = _classify_chunk(chunk, chunk_idx, total, is_last_n)
        if chunk_type == "metadata":
            embedded_command = _EMBEDDED_METADATA_COMMAND_RE.search(chunk)
            if embedded_command and embedded_command.start() > 0:
                flush()
                metadata_text = chunk[: embedded_command.start()].rstrip(" ,:;")
                if metadata_text:
                    segments.append(Segment(metadata_text, "metadata", [chunk_idx]))
                chunk = chunk[embedded_command.start() :]
                chunk_type = "paragraph"
        if chunk_type in ("metadata", "boilerplate"):
            flush()
            segments.append(Segment(chunk, chunk_type, [chunk_idx]))
            current_type = "preamble"
            continue

        # List items after an open directive are grouped in only when they contain no
        # ordering phrase of their own.  If they do, fall through to normal processing
        # so the ordering phrase starts a new directive.
        if _is_list_item(chunk) and current_type == "order_action" and not ordering_re.search(chunk):
            current_parts.append(chunk)
            current_indices.append(chunk_idx)
            continue

        # Split the chunk into sentences, then each sentence into typed pieces.
        for sent in _split_sentences(chunk) or [chunk]:
            for piece, start_type in _segment_sentence(sent, ordering_re):
                if start_type == "vesting_clause":
                    flush()
                    segments.append(Segment(piece, "vesting_clause", [chunk_idx]))
                elif start_type == "order_action":
                    flush()
                    current_type = "order_action"
                    current_parts.append(piece)
                    if chunk_idx not in current_indices:
                        current_indices.append(chunk_idx)
                else:
                    # None — continue accumulating into the open segment.
                    current_parts.append(piece)
                    if chunk_idx not in current_indices:
                        current_indices.append(chunk_idx)

    flush()
    segments = _merge_short_fragments(
        _merge_sublists(_split_colon_lists(segments, ordering_re))
    )
    return _relabel_interrupted_determination_connectors(segments)
