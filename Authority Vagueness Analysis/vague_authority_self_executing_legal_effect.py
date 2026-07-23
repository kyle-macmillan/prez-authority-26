"""Classify vague-authority directives for self-executing third-party legal effect.

Run from the project root:
  python3 "Authority Vagueness Analysis/vague_authority_self_executing_legal_effect.py"
"""

import argparse
import csv
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).parent.parent
ANALYSIS_DIR = ROOT / "Authority Vagueness Analysis"
DEFAULT_BREAKDOWN = ANALYSIS_DIR / "vesting_authority_breakdown.csv"
DEFAULT_DEV = ROOT / "data" / "4_28_2026_build_dev.csv"
DEFAULT_HOLDOUT = ROOT / "data" / "4_28_2026_build_holdout.csv"
DEFAULT_OUTPUT = ANALYSIS_DIR / "vague_authority_self_executing_legal_effect.csv"
DEFAULT_SUMMARY = ANALYSIS_DIR / "vague_authority_self_executing_summary.csv"

TARGET_AUTHORITY_CATEGORY = "constitution_laws_vague_only"
CATEGORIES = (
    "self_executing_legal_effect",
    "not_self_executing_legal_effect",
    "uncertain_review",
)
DOC_TYPES = ("executive_order", "memorandum", "proclamation", "letter")
INTERNAL_MANAGEMENT_TERMS = re.compile(
    r"\b(task force|council|commission|committee|board|working group|initiative|"
    r"mission|office|interagency|advisory|membership|members?|co-?chair)\b",
    re.I,
)
AGENCY_IMPLEMENTATION_TERMS = re.compile(
    r"\b(shall|must|should|may)\s+"
    r"(\w+ly\s+)?(consider|review|update|develop|propose|recommend|assess|submit|identify|"
    r"coordinate|consult|prepare|study|take appropriate action|take all appropriate action)\b",
    re.I,
)

SELF_EXECUTING_PATTERNS = (
    (
        "land/designation or legal instrument status change",
        re.compile(
            r"\b(designation|reservation|withdrawal|monument|national monument|"
            r"tariff-rate quota|tariff rate quota|regulation|rule|guidance document|"
            r"executive order|proclamation)\b.{0,180}"
            r"\b(is|are|is hereby|are hereby)\s+"
            r"(revoked|suspended|terminated|amended|modified|superseded|continued)\b|"
            r"\b(this order|this proclamation)\s+supersedes\b",
            re.I | re.S,
        ),
    ),
    (
        "tariff/import/HTS change",
        re.compile(
            r"\b(HTSUS|harmonized tariff schedule|tariff schedules of the united states)\b"
            r".{0,240}\b(modified|amended|adjusted|changed|increased|decreased)\b|"
            r"\b(modifies|amends|adjusts|changes|increases|decreases)\b.{0,240}"
            r"\b(HTSUS|harmonized tariff schedule|tariff schedules of the united states)\b|"
            r"\b(tariff-rate quota|tariff rate quota)\b.{0,180}"
            r"\b(modified|amended|adjusted|changed|increased|decreased)\b|"
            r"\b(customs dut(?:y|ies)|antidumping dut(?:y|ies)|countervailing dut(?:y|ies))\b"
            r".{0,180}\b(imposed|collected|paid|owed|assessed)\b|"
            r"\b(additional dut(?:y|ies)|dut(?:y|ies))\b.{0,160}"
            r"\b(shall be|are|is|must be)\s+(imposed|collected|increased|decreased|modified|paid)\b.{0,160}\b(imports?|importers?)\b|"
            r"\b(impose|increase|decrease|modify)\b.{0,100}\bdut(?:y|ies)\b.{0,120}\bimports?\b|"
            r"\b(imports?|importation|entry)\b.{0,140}\b(shall be|are|is)\s+"
            r"(prohibited|restricted|subject to|suspended)\b|"
            r"\b(prohibited|restricted|suspended)\b.{0,120}\b(importation|entry)\b",
            re.I | re.S,
        ),
    ),
    (
        "immigration entry restriction",
        re.compile(
            r"\b(entry|admission) of\b.{0,160}\b(is|are|shall be)\s+(hereby\s+)?"
            r"(suspended|restricted|limited|prohibited)\b|"
            r"\bsuspend(?:ed|s)?\s+.{0,120}\b(entry|admission) of\b",
            re.I | re.S,
        ),
    ),
    (
        "property blocking or transaction prohibition",
        re.compile(
            r"\b(property|interests? in property)\b.{0,180}\b(blocked|may not be "
            r"transferred|may not be paid|may not be exported|may not be withdrawn)\b|"
            r"\b(any|all)\s+(transaction|transactions|donation|donations|transfer|transfers)\b"
            r".{0,140}\b(prohibited|blocked)\b|"
            r"\b(prohibited|blocked)\b.{0,140}\b(transaction|transactions|donation|donations|transfer|transfers)\b",
            re.I | re.S,
        ),
    ),
    (
        "funding or eligibility legal consequence",
        re.compile(
            r"\b(no|none of the)\s+federal funds\b.{0,160}\b"
            r"(shall|may)\s+(be\s+)?(made available|used|provided)\b|"
            r"\bfunds?\b.{0,120}\b(are|is)\s+hereby\s+(withheld|terminated|suspended)\b|"
            r"\b(persons?|entities|recipients?|applicants?|contractors?|products?)\b"
            r".{0,160}\b(shall be|are hereby|is hereby)\s+(ineligible|disqualified|debarred|suspended)\b|"
            r"\b(shall be|are hereby|is hereby)\s+(ineligible|disqualified|debarred|suspended)\b.{0,160}"
            r"\b(persons?|entities|recipients?|applicants?|contractors?|products?)\b",
            re.I | re.S,
        ),
    ),
    (
        "procurement/acquisition prohibition",
        re.compile(
            r"\b(prohibit(?:ion|ed)?|barred|ban(?:ned)?)\b.{0,180}"
            r"\b(acquisition|procurement|contracting|contracts?|products?)\b|"
            r"\b(acquisition|procurement|contracting|contracts?|products?)\b.{0,180}"
            r"\b(prohibit(?:ion|ed)?|barred|ban(?:ned)?)\b",
            re.I | re.S,
        ),
    ),
)

NOT_SELF_EXECUTING_PATTERNS = (
    (
        "internal management establishment or membership",
        re.compile(
            r"\b(there is hereby established|is hereby established|is established|"
            r"establishment of)\b.{0,180}\b(task force|council|commission|committee|"
            r"board|working group|initiative|mission|office|interagency|advisory)\b|"
            r"\b(task force|council|commission|committee|board|working group|initiative|"
            r"mission|office)\b.{0,180}\b(shall include|shall consist|members?|co-?chair|"
            r"meet regularly|coordinate|advise|recommend|report)\b",
            re.I | re.S,
        ),
    ),
    (
        "agency reporting/review/coordination directive",
        re.compile(
            r"\b(agency|agencies|secretary|administrator|director|task force|council|"
            r"committee|department|departments)\b.{0,220}\b"
            r"(report|review|coordinate|consult|recommend|develop|prepare|submit|"
            r"assess|study|identify|establish procedures|provide assistance)\b",
            re.I | re.S,
        ),
    ),
    (
        "ceremonial observance language",
        re.compile(
            r"\b(do hereby )?(proclaim|designate|call upon|urge|invite|request)\b.{0,180}"
            r"\b(day|week|month|year|observance|ceremonies|appropriate activities)\b",
            re.I | re.S,
        ),
    ),
    (
        "rights disclaimer",
        re.compile(r"\bdoes not create any right or benefit\b", re.I),
    ),
)

UNCERTAIN_PATTERNS = ()


def load_corpus(paths: list[Path]) -> dict[str, dict]:
    corpus = {}
    for path in paths:
        with open(path, newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                corpus[row[""]] = row
    return corpus


def clean_excerpt(text: str) -> str:
    return " ".join(text.split())


def context_excerpt(text: str, start: int, end: int, radius: int = 140) -> str:
    excerpt_start = max(0, start - radius)
    excerpt_end = min(len(text), end + radius)
    prefix = "..." if excerpt_start else ""
    suffix = "..." if excerpt_end < len(text) else ""
    return prefix + clean_excerpt(text[excerpt_start:excerpt_end]) + suffix


def first_match(patterns: tuple[tuple[str, re.Pattern], ...], text: str) -> tuple[str, str, str]:
    for rationale, pattern in patterns:
        match = pattern.search(text)
        if match:
            excerpt = context_excerpt(text, match.start(), match.end())
            excerpt_lower = excerpt.lower()
            if "nothing in this order shall be construed" in excerpt_lower:
                continue
            if rationale == "land/designation or legal instrument status change":
                if INTERNAL_MANAGEMENT_TERMS.search(excerpt):
                    continue
            if rationale in {
                "tariff/import/HTS change",
                "procurement/acquisition prohibition",
                "funding or eligibility legal consequence",
            }:
                if AGENCY_IMPLEMENTATION_TERMS.search(excerpt):
                    continue
                if "strategy shall address" in excerpt_lower:
                    continue
                if "criteria shall include" in excerpt_lower:
                    continue
                if "shall include a criterion" in excerpt_lower:
                    continue
                if "shall provide for" in excerpt_lower:
                    continue
                if "regulations proposed" in excerpt_lower:
                    continue
                if "it is the policy of the united states" in excerpt_lower:
                    continue
                if "it is therefore the policy" in excerpt_lower:
                    continue
                if " means " in excerpt_lower:
                    continue
            return rationale, clean_excerpt(match.group(0)), excerpt
    return "", "", ""


def classify_self_executing_legal_effect(doc_text: str, doc_type: str) -> tuple[str, str, str, str]:
    """Return (category, rationale, evidence phrase, evidence excerpt)."""
    rationale, evidence, excerpt = first_match(SELF_EXECUTING_PATTERNS, doc_text)
    if rationale:
        return "self_executing_legal_effect", rationale, evidence, excerpt

    uncertain_rationale, uncertain_evidence, uncertain_excerpt = first_match(UNCERTAIN_PATTERNS, doc_text)
    not_rationale, not_evidence, not_excerpt = first_match(NOT_SELF_EXECUTING_PATTERNS, doc_text)

    if doc_type == "proclamation" and not_rationale:
        return "not_self_executing_legal_effect", not_rationale, not_evidence, not_excerpt
    if uncertain_rationale:
        return "uncertain_review", uncertain_rationale, uncertain_evidence, uncertain_excerpt
    if not_rationale:
        return "not_self_executing_legal_effect", not_rationale, not_evidence, not_excerpt
    if doc_type == "proclamation":
        return "not_self_executing_legal_effect", "proclamation without direct private-party effect trigger", "", ""
    return "uncertain_review", "no conservative rule matched", "", ""


def directive_title(row: dict) -> str:
    text = " ".join(row["doc_text"].split())
    for marker in (" Subject:", " By the authority", " Now, Therefore", " A Proclamation"):
        if marker in text:
            text = text.split(marker, 1)[0]
            break
    lower_text = text.lower()
    if not text or lower_text.startswith("by the authority vested") or lower_text.startswith("by the president"):
        slug = row["url"].rstrip("/").rsplit("/", 1)[-1]
        text = " ".join(part for part in slug.split("-") if part).title()
    return text[:140]


def analyze(breakdown_path: Path, corpus_paths: list[Path]) -> tuple[list[dict], Counter]:
    corpus = load_corpus(corpus_paths)
    output = []
    counts = Counter()
    with open(breakdown_path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["authority_category"] != TARGET_AUTHORITY_CATEGORY:
                continue
            corpus_row = corpus[row["document_id"]]
            category, rationale, evidence, excerpt = classify_self_executing_legal_effect(
                corpus_row["doc_text"], row["doc_type"]
            )
            counts[("total", category)] += 1
            counts[(row["doc_type"], category)] += 1
            output.append(
                {
                    "document_id": row["document_id"],
                    "url": row["url"],
                    "date": row["date"],
                    "president": row["president"],
                    "doc_type": row["doc_type"],
                    "term": row["term"],
                    "source_file": row["source_file"],
                    "authority_category": row["authority_category"],
                    "self_executing_category": category,
                    "rationale": rationale,
                    "evidence_phrase": evidence,
                    "evidence_excerpt": excerpt,
                    "directive_title": directive_title(corpus_row),
                    "vesting_clauses": row["vesting_clauses"],
                }
            )
    return output, counts


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "document_id",
        "url",
        "date",
        "president",
        "doc_type",
        "term",
        "source_file",
        "authority_category",
        "self_executing_category",
        "rationale",
        "evidence_phrase",
        "evidence_excerpt",
        "directive_title",
        "vesting_clauses",
    ]
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, counts: Counter) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["doc_type", "self_executing_category", "count"])
        writer.writeheader()
        for doc_type in (*DOC_TYPES, "total"):
            for category in CATEGORIES:
                writer.writerow(
                    {
                        "doc_type": doc_type,
                        "self_executing_category": category,
                        "count": counts[(doc_type, category)],
                    }
                )


def print_summary(counts: Counter) -> None:
    print(f"{'document type':<18} {'self-executing category':<34} {'count':>8}")
    print("-" * 62)
    for doc_type in (*DOC_TYPES, "total"):
        for category in CATEGORIES:
            print(f"{doc_type:<18} {category:<34} {counts[(doc_type, category)]:>8,}")
        if doc_type != "total":
            print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--breakdown", type=Path, default=DEFAULT_BREAKDOWN)
    parser.add_argument("--dev", type=Path, default=DEFAULT_DEV)
    parser.add_argument("--holdout", type=Path, default=DEFAULT_HOLDOUT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    rows, counts = analyze(args.breakdown, [args.dev, args.holdout])
    write_rows(args.out, rows)
    write_summary(args.summary, counts)
    print_summary(counts)
    print(f"\nRows: {args.out} ({len(rows):,} directives)")
    print(f"Summary: {args.summary}")


if __name__ == "__main__":
    main()
