#!/usr/bin/env python3
"""Compare one validated method's decisions with the frozen manual review."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as handle:
        yield from (json.loads(line) for line in handle if line.strip())


def ratio(numerator: int, denominator: int):
    return numerator / denominator if denominator else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--decisions", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    review = json.loads(args.review.read_text(encoding="utf-8"))
    decisions = list(read_jsonl(args.decisions))
    cases = review["cases"]
    ids = [str(row["child_id"]) for row in decisions]
    if len(ids) != len(set(ids)) or set(ids) != set(cases):
        raise ValueError("decisions must contain exactly one record for every reviewed child")
    counts = Counter()
    for row in decisions:
        truth = cases[str(row["child_id"])]
        if row["decision"] == "none":
            outcome = "correct_abstention" if truth["decision"] == "none" else "false_abstention"
        elif truth["decision"] == "none":
            outcome = "false_candidate"
        elif str(row["best_candidate_id"]) == str(truth["selected_parent_id"]):
            outcome = "correct_candidate"
        else:
            outcome = "wrong_candidate"
        counts[outcome] += 1
    total = len(decisions)
    candidate_count = counts["correct_candidate"] + counts["wrong_candidate"] + counts["false_candidate"]
    abstention_count = counts["correct_abstention"] + counts["false_abstention"]
    report = {"schema_version": 1, "snapshot_hash": review["snapshot_hash"], "n": total,
              "method": decisions[0]["method"] if decisions else None, "counts": dict(counts),
              "exact_outcome_accuracy": ratio(counts["correct_candidate"] + counts["correct_abstention"], total),
              "candidate_precision": ratio(counts["correct_candidate"], candidate_count),
              "abstention_precision": ratio(counts["correct_abstention"], abstention_count),
              "coverage": ratio(candidate_count, total)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
