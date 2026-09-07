#!/usr/bin/env python3
"""Conservatively code explicit power recipients in current OLRC text."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build import CENSUS_FIELDS  # noqa: E402

POWER = (
    r"may\b(?!\s+not\b)|is\s+(?:hereby\s+)?authorized\b|is\s+(?:hereby\s+)?empowered\b|"
    r"shall\s+(?!not\b)(?!submit\b)(?!report\b)(?!transmit\b)(?!consult\b)"
    r"(?:determine|designate|appoint|issue|prescribe|proclaim|establish|suspend|waive|"
    r"exempt|reserve|withdraw|transfer|authorize|direct|approve|adjust|modify|terminate|"
    r"impose|prohibit|permit|extend|revoke|allocate|make|enter|provide|declare|recognize)\b|"
    r"shall\s+have\s+(?:the\s+)?(?:power|authority)\b"
)
PRESIDENT = re.compile(rf"\b(?:the\s+)?President(?:\s+of\s+the\s+United\s+States)?\s+(?:{POWER})", re.I)
OFFICER_NAME = (
    r"(?:the\s+)?(?:Secretary(?:\s+of\s+[A-Z][A-Za-z ]+)?|Attorney\s+General|Administrator|"
    r"Director|Commission|Board|department|agency|head\s+of\s+(?:an|any|the)\s+(?:department|agency))"
)
OFFICER = re.compile(rf"\b{OFFICER_NAME}\s+(?:{POWER})", re.I)
OTHER = re.compile(rf"\b(?:Congress|a\s+court|the\s+court|any\s+State|a\s+State)\s+(?:{POWER})", re.I)
AMENDMENT_YEAR = re.compile(r"\b(19\d{2}|20\d{2})\s*[—-]")


def sentence_excerpt(text: str, match: re.Match) -> str:
    boundary = text.rfind(". ", 0, match.start())
    start = boundary + 2 if boundary >= 0 else 0
    end = text.find(". ", match.end())
    if end < 0: end = len(text)
    words = text[start:end + 1].strip().split()
    return " ".join(words[:45])


def classify(text: str) -> tuple[str, str, str] | None:
    president = list(PRESIDENT.finditer(text))
    officer = list(OFFICER.finditer(text))
    other = list(OTHER.finditer(text))
    if president and officer:
        return "both", "multiple affirmative statutory powers", sentence_excerpt(text, president[0])
    if president:
        return "president_only", "express presidential power", sentence_excerpt(text, president[0])
    if officer:
        return "agency_or_officer_only", "express agency or officer power", sentence_excerpt(text, officer[0])
    if other:
        return "other_recipient", "express nonexecutive power", sentence_excerpt(text, other[0])
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=HERE / "outputs" / "recipient_review_queue.csv")
    parser.add_argument("--output", type=Path, default=HERE / "provision_census.csv")
    parser.add_argument("--overrides", type=Path, default=HERE / "reviewed_overrides.csv")
    args = parser.parse_args()
    csv.field_size_limit(sys.maxsize)
    with args.queue.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    census = []
    for row in rows:
        if row["source_status"] != "found": continue
        decision = classify(row["operative_text"])
        if not decision: continue
        earliest_year = int(row["earliest_directive"][:4])
        later_amendments = sorted({int(year) for year in AMENDMENT_YEAR.findall(row["amendment_notes"])
                                   if int(year) > earliest_year})
        if later_amendments:
            # Current text cannot safely be applied to the earlier occurrences.
            continue
        recipient, power_type, excerpt = decision
        census.append({
            "canonical_authority_id": row["canonical_authority_id"],
            "version_start": row["earliest_directive"], "version_end": "",
            "recipient_class": recipient, "power_type": power_type,
            "operative_excerpt": excerpt,
            "rationale": "Explicit actor-power construction in OLRC operative text; no post-earliest-directive amendment is listed for this section.",
            "official_source_url": row["official_source_url"],
            "official_source_citation": f"{row['title']} U.S.C. {row['section']} (OLRC release 119-102not101)",
            "confidence": "high_deterministic_current_text",
            "review_status": "resolved by conservative source rule; historical stability screened from OLRC amendment notes",
        })
    if args.overrides.exists():
        with args.overrides.open(newline="", encoding="utf-8") as handle:
            overrides = list(csv.DictReader(handle))
        override_keys = {(row["canonical_authority_id"], row["version_start"], row["version_end"])
                         for row in overrides}
        census = [row for row in census
                  if not any(row["canonical_authority_id"] == key[0] for key in override_keys)]
        census.extend(overrides)
    census.sort(key=lambda row: (row["canonical_authority_id"], row["version_start"]))
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CENSUS_FIELDS)
        writer.writeheader(); writer.writerows(census)
    print(f"wrote {len(census)} conservative provision decisions")


if __name__ == "__main__":
    main()
