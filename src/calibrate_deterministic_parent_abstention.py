#!/usr/bin/env python3
"""Calibrate deterministic top-candidate abstention from blinded case labels."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from validate_function_profiles import _read_jsonl

ROOT = Path(__file__).resolve().parents[1]


def threshold_candidates(rows: list[dict]) -> list[float]:
    values = sorted({float(row["score"]) for row in rows})
    return [math.inf] + [(left + right) / 2 for left, right in zip(values, values[1:])] + [-math.inf]


def correct(row: dict, label: dict, threshold: float) -> bool:
    predicts_candidate = float(row["score"]) >= threshold
    if predicts_candidate:
        return label["decision"] == "candidate" and str(label["selected_parent_id"]) == str(row["parent_id"])
    return label["decision"] == "none"


def choose_threshold(rows: list[dict], labels: dict[str, dict]) -> tuple[float, float]:
    scored = []
    for threshold in threshold_candidates(rows):
        accuracy = sum(correct(row, labels[str(row["child_id"])], threshold) for row in rows) / len(rows)
        scored.append((accuracy, threshold))
    # Accuracy first; a higher threshold is the conservative tie-break.
    return max(scored, key=lambda item: (item[0], item[1]))[1], max(item[0] for item in scored)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review", type=Path)
    parser.add_argument("--snapshot-dir", type=Path, default=ROOT / "data/parent_analysis/function_parent_pilot/provisional")
    parser.add_argument("--rankings", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    rankings = args.rankings or args.snapshot_dir / "deterministic_rankings.jsonl"
    output = args.output or args.snapshot_dir / "deterministic_decisions.jsonl"
    report_path = args.report or args.snapshot_dir / "deterministic_abstention_calibration.json"
    review = json.loads(args.review.read_text())
    manifest = json.loads((args.snapshot_dir / "snapshot_manifest.json").read_text())
    if review.get("schema_version") != 2: raise ValueError("review must use schema version 2")
    if review.get("snapshot_hash") != manifest["snapshot_hash"]: raise ValueError("review snapshot mismatch")
    labels = {str(key): value for key, value in review["cases"].items()}
    incomplete = [key for key, value in labels.items() if value.get("decision") not in {"candidate", "none"}]
    if incomplete: raise ValueError(f"incomplete review cases: {', '.join(sorted(incomplete, key=int))}")
    top = sorted((row for row in _read_jsonl(rankings) if int(row["rank"]) == 1), key=lambda row: int(row["child_id"]))
    if set(labels) != {str(row["child_id"]) for row in top}: raise ValueError("review/ranking child sets differ")
    final_threshold, apparent_accuracy = choose_threshold(top, labels)
    loo_thresholds, loo_correct = {}, {}
    for held_out in top:
        child_id = str(held_out["child_id"])
        training = [row for row in top if str(row["child_id"]) != child_id]
        threshold, _ = choose_threshold(training, labels)
        loo_thresholds[child_id] = threshold; loo_correct[child_id] = correct(held_out, labels[child_id], threshold)
    with output.open("w", encoding="utf-8") as handle:
        for row in top:
            score = float(row["score"]); predicts = score >= final_threshold
            decision = {"schema_version": 1, "child_id": str(row["child_id"]), "method": "deterministic",
                        "best_candidate_id": str(row["parent_id"]), "ranking_score": score,
                        "decision": "candidate" if predicts else "none", "acceptance_score": score,
                        "score_semantics": "weighted_function_alignment_cosine",
                        "decision_source": "pilot_calibrated_threshold", "reason": "", "matches": row.get("matches", {}),
                        "model": None, "prompt_version": None, "threshold": final_threshold,
                        "snapshot_hash": manifest["snapshot_hash"]}
            handle.write(json.dumps(decision, ensure_ascii=False) + "\n")
    report = {"schema_version": 1, "snapshot_hash": manifest["snapshot_hash"], "cases": len(top),
              "threshold_selection": "maximize exact case accuracy; higher threshold breaks ties",
              "final_threshold": final_threshold, "apparent_accuracy": apparent_accuracy,
              "leave_one_out_accuracy": sum(loo_correct.values()) / len(loo_correct),
              "leave_one_out_thresholds": loo_thresholds, "leave_one_out_correct": loo_correct}
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"decisions": len(top), "final_threshold": final_threshold,
                      "leave_one_out_accuracy": report["leave_one_out_accuracy"], "output": str(output)}, sort_keys=True))


if __name__ == "__main__": main()
