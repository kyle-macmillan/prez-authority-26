#!/usr/bin/env python3
"""Validate and evaluate four candidate-or-none methods against review schema 2."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METHODS = {"deterministic", "qwen", "gemini_search", "gemini_search_thinking_medium"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review", type=Path)
    parser.add_argument("decisions", type=Path, nargs="+")
    parser.add_argument("--snapshot-dir", type=Path, default=ROOT / "data/parent_analysis/function_parent_pilot/provisional")
    args = parser.parse_args()
    review = json.loads(args.review.read_text()); manifest = json.loads((args.snapshot_dir / "snapshot_manifest.json").read_text())
    if review.get("schema_version") != 2 or review.get("snapshot_hash") != manifest["snapshot_hash"]: raise ValueError("review schema/snapshot mismatch")
    sample = {}
    import csv
    with (args.snapshot_dir / "sampled_children.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle): sample[row["document_id"]] = row
    rows = []
    for path in args.decisions:
        rows.extend(json.loads(line) for line in path.open() if line.strip())
    keys = [(str(row["child_id"]), row["method"]) for row in rows]
    expected = {(child_id, method) for child_id in review["cases"] for method in METHODS}
    if len(keys) != len(set(keys)) or set(keys) != expected: raise ValueError("decisions must contain one row per child and method")
    outcomes = defaultdict(Counter)
    for row in rows:
        child_id = str(row["child_id"]); label = review["cases"][child_id]
        if row["snapshot_hash"] != manifest["snapshot_hash"]: raise ValueError("decision snapshot mismatch")
        if row["decision"] == "none": outcome = "correct_abstention" if label["decision"] == "none" else "false_abstention"
        elif label["decision"] == "none": outcome = "false_candidate"
        elif str(row["best_candidate_id"]) == str(label["selected_parent_id"]): outcome = "correct_candidate"
        else: outcome = "wrong_candidate"
        outcomes[row["method"]][outcome] += 1
        outcomes[row["method"]][f"stratum:{sample[child_id]['sample_stratum']}:{outcome}"] += 1
    report = {"schema_version": 1, "snapshot_hash": manifest["snapshot_hash"], "methods": {}}
    for method in sorted(METHODS):
        counts = outcomes[method]; correct = counts["correct_candidate"] + counts["correct_abstention"]
        predicted_candidate = counts["correct_candidate"] + counts["wrong_candidate"] + counts["false_candidate"]
        predicted_none = counts["correct_abstention"] + counts["false_abstention"]
        report["methods"][method] = {"counts": dict(counts), "exact_outcome_accuracy": correct / 50,
            "coverage": predicted_candidate / 50,
            "candidate_precision": counts["correct_candidate"] / predicted_candidate if predicted_candidate else None,
            "abstention_precision": counts["correct_abstention"] / predicted_none if predicted_none else None}
    (args.snapshot_dir / "method_decision_evaluation.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    with (args.snapshot_dir / "method_decisions.jsonl").open("w", encoding="utf-8") as handle:
        for row in sorted(rows, key=lambda item: (int(item["child_id"]), item["method"])): handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"decisions": len(rows), "methods": sorted(METHODS)}, sort_keys=True))


if __name__ == "__main__": main()
