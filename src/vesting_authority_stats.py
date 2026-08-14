"""Count documents whose vesting clauses cite only generic presidential authority.

The default corpus is the union of the development and holdout CSVs.  A document
qualifies when at least one vesting clause cites the Constitution or the law(s) of
the United States, and no vesting clause cites a more specific named authority.

Run from the project root:
  python3 src/vesting_authority_stats.py
"""

import argparse
import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from segmenter import (
    _AUTHORITY_CITATION_RE,
    _CONDITIONAL_VESTING_RE,
    _get_ordering_re,
    _inline_pursuant_start,
    _pursuant_authority_action_start,
    _PRESIDENTIAL_I_RE,
    _PROC_VESTING_RE,
    _PURSUANT_RE,
    _REVIEWED_COMMANDER_AUTHORITY_RE,
    _segment_sentence,
    _split_sentences,
    _STRONG_VESTING_RE,
    segment_ordering,
)


ROOT = Path(__file__).parent.parent
DEFAULT_DEV = ROOT / "data" / "4_28_2026_build_dev.csv"
DEFAULT_HOLDOUT = ROOT / "data" / "4_28_2026_build_holdout.csv"
DEFAULT_AUDIT = ROOT / "data" / "generic_vesting_authority_audit.csv"
EXPECTED_FULL_CORPUS_SIZE = 18_418
DOC_TYPES = ("executive_order", "memorandum", "letter", "proclamation")

PRESIDENTIAL_TITLE_INVOCATION_RE = re.compile(
    r"\bI,\s+"
    r"[A-Z][A-Za-z.'’\-]*(?:\s+[A-Z][A-Za-z.'’\-]*)*"
    r"(?:,\s*(?:Jr|Sr)\.?)?,\s+"
    r"President\s+of\s+the\s+United\s+States(?:\s+of\s+America)?\b",
    re.IGNORECASE,
)

UNITED_STATES_VARIANT = (
    r"(?:United\s+States|United\s+State\b|United\s+State\s+s|United\s+Sates|Untied\s+States)"
)

PRESIDENTIAL_TITLE_CAPACITY_RE = re.compile(
    rf"\bPresi\.?\s*dent,?\s+of\s+the\s+{UNITED_STATES_VARIANT}"
    r"(?:\s+of\s+America)?\b",
    re.IGNORECASE,
)

PRESIDENTIAL_CAPACITY_RE = re.compile(
    rf"\bas\s+(?:the\s+)?President\s+of\s+the\s+{UNITED_STATES_VARIANT}"
    r"(?:\s+of\s+America)?\b",
    re.IGNORECASE,
)

GENERIC_CONSTITUTIONAL_AUTHORITY_RE = re.compile(
    r"\b(?:my|the\s+President'?s|his|her)\s+constitutional\s+authority\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern


@dataclass(frozen=True)
class RuleMatch:
    rule: str
    text: str


GENERIC_RULES = (
    Rule("presidential_title_invocation", PRESIDENTIAL_TITLE_INVOCATION_RE),
    Rule("presidential_title_capacity", PRESIDENTIAL_TITLE_CAPACITY_RE),
    Rule("presidential_capacity", PRESIDENTIAL_CAPACITY_RE),
    Rule("generic_constitutional_authority", GENERIC_CONSTITUTIONAL_AUTHORITY_RE),
    Rule(
        "constitution",
        re.compile(
            r"\b(?:the\s+)?Constitution"
            r"(?:\s+of\s+the\s+United\s+States(?:\s+of\s+America)?)?\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "laws_of_united_states",
        re.compile(
            r"\b(?:the\s+)?laws?\s+of\s+the\s+United\s+States"
            r"(?:\s+of\s+America)?\b",
            re.IGNORECASE,
        ),
    ),
)


# These rules intentionally favor transparent, auditable matching over inference.
# Generic references such as "applicable law" do not match any rule below.
SPECIFIC_RULES = (
    Rule("usc", re.compile(r"\b(?:\d+\s+U\.?S\.?C\.?|U\.?S\.?C\.?\s*§)", re.I)),
    Rule("legal_section", re.compile(r"\bsections?\s+[\dIVXivx]", re.I)),
    Rule("legal_title", re.compile(r"\btitle\s+\d+", re.I)),
    Rule("legal_chapter", re.compile(r"\bchapter\s+\d+", re.I)),
    Rule("public_law", re.compile(r"\bPublic\s+Law(?:\s+(?:No\.?\s*)?\d+(?:-\d+)?)?", re.I)),
    Rule("statutes_at_large", re.compile(r"\b\d+\s+Stat\.?\s+\d+", re.I)),
    Rule("congressional_measure", re.compile(r"\b(?:H\.?\s*R\.?|S\.?)\s*\d+\b", re.I)),
    Rule(
        "named_act",
        re.compile(
            r"\b(?:the\s+)?(?:[A-Z][A-Za-z0-9'&.-]*\s+){1,10}Act(?:\s+of\s+\d{4})?\b"
        ),
    ),
    Rule("referenced_act", re.compile(r"\b(?:the|this|such)\s+Act\b", re.I)),
    Rule(
        "referenced_statutory_provisions",
        re.compile(
            r"\b(?:above[- ](?:quoted|mentioned)|foregoing)\s+"
            r"(?:(?:statutory|legal)\s+)?(?:provisions?|law|act)\b",
            re.I,
        ),
    ),
    Rule(
        "executive_order",
        re.compile(r"\bExecutive\s+Order\s+(?:(?:No\.?\s*)?\d+|entitled\s+['\"])", re.I),
    ),
    Rule(
        "proclamation",
        re.compile(r"\bProclamation\s+(?:(?:No\.?\s*)?\d+|entitled\s+['\"])", re.I),
    ),
    Rule("joint_resolution", re.compile(r"\b(?:joint|concurrent)\s+resolution\b", re.I)),
    Rule(
        "treaty",
        re.compile(
            r"\b(?:the\s+)?(?:"
            r"[A-Z][A-Za-z'&.-]*(?:\s+[A-Z][A-Za-z'&.-]*){0,8}\s+Treaty"
            r"|Treaty\s+of\s+[A-Z][A-Za-z'&.-]*(?:\s+[A-Z][A-Za-z'&.-]*){0,8}"
            r")\b"
        ),
    ),
    Rule("referenced_treaty", re.compile(r"\bthe\s+Treaty\b", re.I)),
    Rule(
        "named_covenant_or_convention",
        re.compile(
            r"\b(?:International\s+)?Covenant\s+on\s+[A-Z]"
            r"|\bConvention\s+(?:Against|on|for)\s+[A-Z]"
        ),
    ),
    Rule(
        "agreement_or_settlement",
        re.compile(
            r"\b(?:the\s+)?(?:[A-Z][A-Za-z0-9'&.-]*\s+){1,10}"
            r"(?:Agreement|Settlement|Accord|Conventions?|Protocol)\b"
        ),
    ),
    Rule("settlement_agreement", re.compile(r"\b(?:claims?\s+)?settlement\s+agreement\b", re.I)),
    Rule("constitutional_article", re.compile(r"\bArticle\s+[IVXLC\d]+\b", re.I)),
    Rule("constitutional_amendment", re.compile(r"\b(?:\d+(?:st|nd|rd|th)|First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth|Eleventh|Twelfth|Thirteenth|Fourteenth|Fifteenth|Sixteenth|Seventeenth|Eighteenth|Nineteenth|Twentieth|Twenty-First|Twenty-Second|Twenty-Third|Twenty-Fourth|Twenty-Fifth|Twenty-Sixth|Twenty-Seventh)\s+Amendment\b", re.I)),
    Rule("constitutional_clause", re.compile(r"\b[A-Z][A-Za-z-]+\s+Clause\b")),
    Rule("commander_in_chief", re.compile(r"\bCommander[-\s]+in[-\s]+Chief\b", re.I)),
    Rule("chief_executive", re.compile(r"\bChief\s+Executive\b", re.I)),
    Rule("pardon_power", re.compile(r"\b(?:grant\s+)?(?:reprieves?|pardons?)\b", re.I)),
)


def find_matches(text: str, rules: tuple[Rule, ...]) -> list[RuleMatch]:
    """Return deterministic rule matches in rule and text order."""
    matches = []
    for rule in rules:
        matches.extend(RuleMatch(rule.name, match.group(0)) for match in rule.pattern.finditer(text))
    return matches


def classify_vesting_clauses(clauses: list[str]) -> tuple[bool, list[RuleMatch], list[RuleMatch]]:
    """Return (qualifies, generic matches, specific matches) for one document."""
    generic = [match for clause in clauses for match in find_matches(clause, GENERIC_RULES)]
    specific = [match for clause in clauses for match in find_matches(clause, SPECIFIC_RULES)]
    return bool(generic) and not specific, generic, specific


def extract_vesting_clauses(doc_text: str, doc_type: str) -> list[str]:
    """Extract clauses using the vesting-carve stage of the project segmenter.

    The later segment grouping stages cannot create vesting clauses.  Stopping after
    the carve avoids doing unrelated ordering-phrase and section classification work.
    """
    # The scraper occasionally inserts a paragraph break inside a citation (for
    # example, between "10" and "U.S.C.").  Normalize whitespace before carving so
    # the complete authority invocation is evaluated as one sentence.
    normalized_text = re.sub(r"\s+", " ", doc_text).strip()
    ordering_re = _get_ordering_re(extended=False)
    is_proclamation = doc_type == "proclamation"
    clauses = []
    for sentence in _split_sentences(normalized_text) or [normalized_text]:
        title_invocation = PRESIDENTIAL_TITLE_INVOCATION_RE.search(sentence)
        could_be_vesting = bool(
            title_invocation
            or _STRONG_VESTING_RE.search(sentence)
            or (is_proclamation and _PROC_VESTING_RE.search(sentence))
            or _CONDITIONAL_VESTING_RE.search(sentence)
            or _REVIEWED_COMMANDER_AUTHORITY_RE.search(sentence)
            or (
                _PURSUANT_RE.search(sentence)
                and _AUTHORITY_CITATION_RE.search(sentence)
                and _PRESIDENTIAL_I_RE.search(sentence)
            )
            or (
                sentence.lstrip().lower().startswith("pursuant to")
                and _AUTHORITY_CITATION_RE.search(sentence)
            )
            or _inline_pursuant_start(sentence, ordering_re) is not None
        )
        if not could_be_vesting:
            continue
        sentence_authority_action_start = _pursuant_authority_action_start(sentence, ordering_re)
        sentence_clauses = []
        for text, start_type in _segment_sentence(
                sentence,
                ordering_re,
                opening_authority=True,
                is_proclamation=is_proclamation,
            ):
            if start_type != "vesting_clause":
                continue
            # A proclamation's semicolon-separated recitals can occupy the same
            # grammatical sentence as "Now, Therefore".  Authority mentioned in a
            # recital is not part of the vesting invocation, so begin at the actual
            # authority marker rather than retaining the entire recital block.
            strong = _STRONG_VESTING_RE.search(text)
            if strong:
                start = strong.start()
                preceding = text[max(0, start - 250):start]
                anchors = list(
                    re.finditer(r"\b(?:pursuant\s+to|under\s+(?:section|title))\b", preceding, re.I)
                )
                anchors.extend(
                    re.finditer(r"\bby\s+(?:the\s+)?authority\b", preceding, re.I)
                )
                if anchors:
                    start = max(0, start - 250) + max(anchors, key=lambda match: match.start()).start()
            else:
                authority_markers = list(_PURSUANT_RE.finditer(text))
                if sentence_authority_action_start is not None and authority_markers:
                    start = authority_markers[-1].start()
                else:
                    markers = [
                        match
                        for regex in (_CONDITIONAL_VESTING_RE, _PURSUANT_RE, _PROC_VESTING_RE)
                        for match in regex.finditer(text)
                    ]
                    start = min((match.start() for match in markers), default=0)
            clause = text[start:].strip()
            explicit_order = re.search(
                r"\b(?:it\s+is|I\s+do)\s+hereby,?\s+(?:order(?:ed)?|proclaim)\b",
                clause,
                re.I,
            )
            if explicit_order:
                clause = clause[:explicit_order.start()].rstrip(" ,;:")
            presidential_authority = re.match(
                r"By\s+virtue\s+of\s+my\s+authority\s+as\s+President\s+of\s+the\s+"
                r"United\s+States(?:\s+of\s+America)?(?=,\s+and\s+in\s+order\s+to\b)",
                clause,
                re.I,
            )
            if presidential_authority:
                clause = clause[:presidential_authority.end()]
            historical_order = re.search(
                r"\bExecutive\s+Order(?:\s+No\.?)?\s+\d+\s+of\s+"
                r"(?:January|February|March|April|May|June|July|August|September|October|"
                r"November|December)\s+\d{1,2},\s+\d{4}"
                r"(?=,\s+as\s+amended,\s+(?:prescribing|entitled)\b)",
                clause,
                re.I,
            )
            if historical_order:
                clause = clause[:historical_order.end()]
            clause = re.sub(
                r"(\bProclamation(?:\s+No\.?)?\s+\d+\s+of\s+"
                r"(?:January|February|March|April|May|June|July|August|September|October|"
                r"November|December)\s+\d{1,2},\s+\d{4}),\s+as\s+amended,$",
                r"\1,",
                clause,
                flags=re.I,
            )
            sentence_clauses.append(clause)

        # The formal "I, [name], President ..." formula is itself a generic
        # invocation even when no other vesting marker occurs.  Retain legal
        # citations before the formula and capacity qualifiers after it, but stop
        # before the first ordering phrase that follows the presidential title.
        if title_invocation and not any(
            PRESIDENTIAL_TITLE_INVOCATION_RE.search(clause) for clause in sentence_clauses
        ):
            start = 0
            preceding_now = list(_CONDITIONAL_VESTING_RE.finditer(sentence, 0, title_invocation.start()))
            if preceding_now:
                start = preceding_now[-1].start()
            following_order = ordering_re.search(sentence, title_invocation.end())
            end = following_order.start() if following_order else title_invocation.end()
            sentence_clauses.append(sentence[start:end].strip().rstrip(" ,;:"))

        clauses.extend(sentence_clauses)

    # The normalized-text pass above handles citations split across scraper paragraph
    # boundaries and proclamation-specific formulas.  If it found nothing, fall back to
    # structural segmentation so an authority clause beginning after metadata or another
    # body paragraph is not hidden when whitespace normalization combines the chunks.
    if not clauses:
        clauses = [
            segment.text
            for segment in segment_ordering(doc_text, doc_type)
            if segment.seg_type == "vesting_clause"
        ]
    return clauses


def load_corpus(paths: list[Path]) -> list[dict]:
    rows = []
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    for path in paths:
        with open(path, newline="", encoding="utf-8-sig") as handle:
            source_rows = list(csv.DictReader(handle))
        for row in source_rows:
            doc_id = row[""]
            url = row["url"]
            if doc_id in seen_ids:
                raise ValueError(f"duplicate document ID across corpus: {doc_id}")
            if url in seen_urls:
                raise ValueError(f"duplicate document URL across corpus: {url}")
            if row["doc_type"] not in DOC_TYPES:
                raise ValueError(f"unexpected document type {row['doc_type']!r} for ID {doc_id}")
            seen_ids.add(doc_id)
            seen_urls.add(url)
            row["source_file"] = path.name
            rows.append(row)
    return rows


def _matches_json(matches: list[RuleMatch]) -> str:
    return json.dumps([{"rule": match.rule, "text": match.text} for match in matches])


def analyze(rows: list[dict]) -> tuple[list[dict], Counter, Counter]:
    """Analyze rows and return generic candidates, qualifying counts, and denominators."""
    audit_rows = []
    qualifying = Counter()
    denominators = Counter(row["doc_type"] for row in rows)

    for row in rows:
        # A generic reference cannot appear in a vesting clause unless it appears in
        # the document.  This exact-rule prefilter avoids segmenting clear non-candidates.
        if not find_matches(row["doc_text"], GENERIC_RULES):
            continue
        clauses = extract_vesting_clauses(row["doc_text"], row["doc_type"])
        qualifies, generic, specific = classify_vesting_clauses(clauses)
        if not generic:
            continue
        if qualifies:
            qualifying[row["doc_type"]] += 1
        audit_rows.append(
            {
                "document_id": row[""],
                "url": row["url"],
                "doc_type": row["doc_type"],
                "source_file": row["source_file"],
                "qualifies": str(qualifies).lower(),
                "reason": "generic authority only" if qualifies else "specific authority cited",
                "generic_authority_matches": _matches_json(generic),
                "specific_authority_matches": _matches_json(specific),
                "vesting_clauses": json.dumps(clauses),
            }
        )
    return audit_rows, qualifying, denominators


def write_audit(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "document_id", "url", "doc_type", "source_file", "qualifies", "reason",
        "generic_authority_matches", "specific_authority_matches", "vesting_clauses",
    ]
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(qualifying: Counter, denominators: Counter) -> None:
    print(f"{'document type':<20} {'qualifying':>10} {'documents':>10} {'percent':>9}")
    print("-" * 52)
    for doc_type in (*DOC_TYPES, "total"):
        if doc_type == "total":
            numerator = sum(qualifying.values())
            denominator = sum(denominators.values())
        else:
            numerator = qualifying[doc_type]
            denominator = denominators[doc_type]
        percent = 100 * numerator / denominator if denominator else 0
        print(f"{doc_type:<20} {numerator:>10,} {denominator:>10,} {percent:>8.2f}%")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev", type=Path, default=DEFAULT_DEV)
    parser.add_argument("--holdout", type=Path)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    args = parser.parse_args()

    paths = [args.dev] + ([args.holdout] if args.holdout else [])
    rows = load_corpus(paths)
    if args.dev == DEFAULT_DEV and args.holdout is None and len(rows) != EXPECTED_FULL_CORPUS_SIZE:
        raise ValueError(
            f"expected {EXPECTED_FULL_CORPUS_SIZE:,} development documents, found {len(rows):,}"
        )
    audit_rows, qualifying, denominators = analyze(rows)
    write_audit(args.audit, audit_rows)
    print_summary(qualifying, denominators)
    print(f"\nAudit: {args.audit} ({len(audit_rows):,} documents with generic authority)")


if __name__ == "__main__":
    main()
