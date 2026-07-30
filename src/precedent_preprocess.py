"""Authority masking and shared preprocessing for similarity-based EO retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass


AUTHORITY_TOKEN = "[AUTHORITY]"


@dataclass(frozen=True)
class MaskedSpan:
    start: int
    end: int
    text: str
    kind: str


# Patterns are ordered from larger compound citations to smaller authority names.
# Internal references such as "section 2 of this order" intentionally do not match.
AUTHORITY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "usc_section",
        re.compile(
            r"\bsections?\s+[\dA-Za-z().,\-\s]+?\s+of\s+title\s+\d+\s*,?\s*"
            r"United\s+States\s+Code\b"
            r"|\b\d+\s+U\.?\s*S\.?\s*C\.?\s*(?:§{1,2}\s*)?[\dA-Za-z().\-–—]+"
            r"(?:\s+et\s+seq\.)?",
            re.I,
        ),
    ),
    (
        "act_section",
        re.compile(
            r"\bsections?\s+[\dA-Za-z().,\-\s]+?\s+of\s+(?:the\s+)?"
            r"(?:[A-Z][A-Za-z0-9'’&.,\-]*\s+){1,12}Act(?:\s+of\s+\d{4})?\b",
        ),
    ),
    (
        "named_act",
        re.compile(
            r"\b(?:the\s+)?(?:[A-Z][A-Za-z0-9'’&.\-]*\s+){1,12}"
            r"Act(?:\s+of\s+\d{4})?\b"
        ),
    ),
    (
        "public_law",
        re.compile(r"\bPublic\s+Law\s+(?:No\.?\s*)?\d+(?:-\d+)?\b", re.I),
    ),
    (
        "statutes_at_large",
        re.compile(r"\b\d+\s+Stat\.?\s+\d+(?:[-–]\d+)?\b", re.I),
    ),
    (
        "executive_order",
        re.compile(
            r"\bExecutive\s+Orders?(?:\s+Nos?\.?)?\s+"
            r"\d{4,5}(?:\s*-\s*A)?\b",
            re.I,
        ),
    ),
    (
        "proclamation",
        re.compile(r"\bProclamation(?:\s+No\.?)?\s+\d+\b", re.I),
    ),
    (
        "constitution",
        re.compile(
            r"\b(?:Article\s+[IVXLC\d]+\s+of\s+)?(?:the\s+)?Constitution"
            r"(?:\s+of\s+the\s+United\s+States(?:\s+of\s+America)?)?\b",
            re.I,
        ),
    ),
    (
        "constitutional_power",
        re.compile(
            r"\b(?:Commander[-\s]+in[-\s]+Chief|Chief\s+Executive|"
            r"(?:First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth|"
            r"Eleventh|Twelfth|Thirteenth|Fourteenth|Fifteenth|Sixteenth|"
            r"Seventeenth|Eighteenth|Nineteenth|Twentieth|Twenty-First|Twenty-Second|"
            r"Twenty-Third|Twenty-Fourth|Twenty-Fifth|Twenty-Sixth|Twenty-Seventh|"
            r"\d+(?:st|nd|rd|th))\s+Amendment)\b",
            re.I,
        ),
    ),
    (
        "generic_laws",
        re.compile(
            r"\b(?:the\s+)?laws?\s+of\s+the\s+United\s+States"
            r"(?:\s+of\s+America)?\b",
            re.I,
        ),
    ),
    (
        "joint_resolution",
        re.compile(
            r"\b(?:House|Senate)?\s*(?:Joint|Concurrent)\s+Resolution"
            r"(?:\s+\d+)?\b",
            re.I,
        ),
    ),
)


BOILERPLATE_SIGNALS = (
    "nothing in this order shall be construed to impair or otherwise affect",
    "nothing in this order shall be construed to impair",
    "this order shall be implemented consistent with applicable law",
    "this order shall be implemented in accordance with applicable law",
    "this order is not intended to, and does not, create any right or benefit",
    "this order is not intended to create, and does not create, any right or benefit",
    "shall be published in the federal register",
)

SEVERABILITY_RE = re.compile(
    r"\bif\s+any\s+provision\s+of\s+this\s+order\b.{0,1200}?"
    r"\b(?:held\s+invalid|invalidated|not\s+given\s+effect)\b"
    r"|\bthe\s+invalidity\s+of\s+any\s+provision\s+of\s+this\s+order\b",
    re.I | re.S,
)

GENERAL_PROVISIONS_CONTINUATION_RE = re.compile(
    r"^\s*\((?:i|ii)\)\s+(?:the\s+)?(?:authority\s+granted\s+by\s+law|"
    r"functions?\s+of\s+the\s+Director\s+of\s+the\s+Office\s+of\s+Management\s+and\s+Budget)",
    re.I,
)


def authority_spans(text: str) -> list[MaskedSpan]:
    candidates = [
        MaskedSpan(match.start(), match.end(), match.group(0), kind)
        for kind, pattern in AUTHORITY_PATTERNS
        for match in pattern.finditer(text)
    ]
    # Prefer the longest candidate at a given location, then merge overlapping spans.
    candidates.sort(key=lambda span: (span.start, -(span.end - span.start)))
    selected: list[MaskedSpan] = []
    for span in candidates:
        if selected and span.start < selected[-1].end:
            if span.end > selected[-1].end:
                previous = selected[-1]
                selected[-1] = MaskedSpan(
                    previous.start,
                    span.end,
                    text[previous.start : span.end],
                    previous.kind,
                )
            continue
        selected.append(span)
    return selected


def mask_authorities(text: str) -> tuple[str, list[MaskedSpan]]:
    spans = authority_spans(text)
    if not spans:
        return text, []
    pieces = []
    cursor = 0
    for span in spans:
        pieces.append(text[cursor : span.start])
        pieces.append(AUTHORITY_TOKEN)
        cursor = span.end
    pieces.append(text[cursor:])
    return "".join(pieces), spans


def remove_similarity_boilerplate(text: str) -> tuple[str, list[str]]:
    """Remove recurring limitation/severability paragraphs, preserving other text."""
    paragraphs = [part.strip() for part in re.split(r" {2,}", text) if part.strip()]
    kept: list[str] = []
    removed: list[str] = []
    removing_impairment_subitems = False

    for paragraph in paragraphs:
        lower = paragraph.lower()
        is_impairment_start = any(
            signal in lower for signal in BOILERPLATE_SIGNALS[:2]
        )
        should_remove = (
            any(signal in lower for signal in BOILERPLATE_SIGNALS)
            or bool(SEVERABILITY_RE.search(paragraph))
            or (
                removing_impairment_subitems
                and bool(GENERAL_PROVISIONS_CONTINUATION_RE.match(paragraph))
            )
        )
        if should_remove:
            removed.append(paragraph)
        else:
            kept.append(paragraph)

        if is_impairment_start:
            removing_impairment_subitems = True
        elif removing_impairment_subitems and not GENERAL_PROVISIONS_CONTINUATION_RE.match(paragraph):
            removing_impairment_subitems = False

    return "  ".join(kept), removed


def preprocess_for_similarity(text: str) -> tuple[str, list[MaskedSpan], list[str]]:
    without_boilerplate, removed = remove_similarity_boilerplate(text)
    masked, spans = mask_authorities(without_boilerplate)
    return masked, spans, removed
