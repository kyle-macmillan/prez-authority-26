#!/usr/bin/env python3
"""Join occurrence frequencies to OLRC source text for recipient review."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

FIELDS = (
    "canonical_authority_id", "title", "section", "subsections", "occurrences", "earliest_directive", "latest_directive",
    "cited_locators", "heading", "operative_text", "source_credit", "amendment_notes",
    "official_source_url", "source_status", "recipient_class", "power_type",
    "operative_excerpt", "rationale", "historical_status", "review_status",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    here = Path(__file__).resolve().parent
    parser.add_argument("--occurrences", type=Path, default=here / "outputs" / "citation_occurrences.csv")
    parser.add_argument("--sources", type=Path, default=here / "outputs" / "current_uscode_sources.csv")
    parser.add_argument("--output", type=Path, default=here / "outputs" / "recipient_review_queue.csv")
    args = parser.parse_args()
    csv.field_size_limit(sys.maxsize)
    grouped = defaultdict(list)
    with args.occurrences.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["citation_kind"] == "usc":
                grouped[row["canonical_authority_id"]].append(row)
    with args.sources.open(newline="", encoding="utf-8") as handle:
        sources = {row["canonical_authority_id"]: row for row in csv.DictReader(handle)}
    output = []
    for authority, occurrences in grouped.items():
        dates = [datetime.strptime(row["date"], "%B %d, %Y").date() for row in occurrences]
        source = sources.get(authority, {})
        output.append({
            "canonical_authority_id": authority,
            "occurrences": len(occurrences),
            "earliest_directive": min(dates).isoformat(),
            "latest_directive": max(dates).isoformat(),
            "cited_locators": ";".join(sorted({row["canonical_authority_id"] for row in occurrences})),
            **source,
            "recipient_class": "", "power_type": "", "operative_excerpt": "",
            "rationale": "", "historical_status": "pending", "review_status": "pending",
        })
    output.sort(key=lambda row: (-int(row["occurrences"]), row["canonical_authority_id"]))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader(); writer.writerows(output)
    print(f"wrote {len(output)} review rows to {args.output}")


if __name__ == "__main__":
    main()
