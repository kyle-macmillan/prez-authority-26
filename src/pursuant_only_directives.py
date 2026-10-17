"""List directives that cite authority only with "pursuant to" language.

A directive is listed when it has no formal invocation ("By the authority vested in
me", "Now, Therefore, I", "I, [name], President …", or a proclamation's congressional
request) but its text uses "pursuant to".  ``pursuant_is_vesting_clause`` marks the
directives whose "pursuant to" citation serves as the vesting clause; in the rest the
phrase appears only in passing (e.g. "funds made available pursuant to chapter 4").

Run from the project root:
  python3 src/pursuant_only_directives.py
"""

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

from vesting_authority_stats import (
    DEFAULT_DEV,
    DEFAULT_HOLDOUT,
    DOC_TYPES,
    ROOT,
    extract_vesting_clauses,
    load_corpus,
    vesting_invocation_type,
)


DEFAULT_OUTPUT = ROOT / "data" / "pursuant_only_directives.csv"
PURSUANT_RE = re.compile(r"\bpursuant\s+to\b", re.IGNORECASE)
FIELDNAMES = [
    "ucsb_identifier", "url", "president", "date", "doc_type", "source_file",
    "pursuant_is_vesting_clause", "vesting_clauses", "first_pursuant_context",
]


def pursuant_only_rows(rows: list[dict]) -> list[dict]:
    output = []
    for row in rows:
        text = row["doc_text"]
        first = PURSUANT_RE.search(text)
        if not first:
            continue
        clauses = extract_vesting_clauses(text, row["doc_type"])
        if vesting_invocation_type(text, row["doc_type"], clauses) != "pursuant_only":
            continue
        output.append(
            {
                "ucsb_identifier": row["ucsb_identifier"],
                "url": row["url"],
                "president": row["president"],
                "date": row["date"],
                "doc_type": row["doc_type"],
                "source_file": row["source_file"],
                "pursuant_is_vesting_clause": str(
                    any(PURSUANT_RE.search(clause) for clause in clauses)
                ).lower(),
                "vesting_clauses": json.dumps(clauses),
                "first_pursuant_context": re.sub(
                    r"\s+", " ", text[max(0, first.start() - 100):first.start() + 200]
                ).strip(),
            }
        )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev", type=Path, default=DEFAULT_DEV)
    parser.add_argument("--holdout", type=Path, default=DEFAULT_HOLDOUT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    output = pursuant_only_rows(load_corpus([args.dev, args.holdout]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(output)

    counts = Counter(row["doc_type"] for row in output)
    as_vesting = Counter(
        row["doc_type"] for row in output if row["pursuant_is_vesting_clause"] == "true"
    )
    print(f"{'document type':<20} {'pursuant only':>13} {'as vesting':>11}")
    for doc_type in (*DOC_TYPES, "total"):
        total = sum(counts.values()) if doc_type == "total" else counts[doc_type]
        vesting = sum(as_vesting.values()) if doc_type == "total" else as_vesting[doc_type]
        print(f"{doc_type:<20} {total:>13,} {vesting:>11,}")
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
