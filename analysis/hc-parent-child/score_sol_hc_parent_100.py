#!/usr/bin/env python3
"""Score objective retrieval channels against Sol's accepted HC parent selections."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent
DEFAULT_PACKAGE = HERE / "outputs/sol_hc_parent_100"
CHANNELS = ("word5", "word10", "bm25", "function")


def retrieval_summary(rows: list[dict], channel: str) -> dict:
    ranks = [int(row[f"{channel}_rank"]) for row in rows if row.get(f"{channel}_rank") not in (None, "")]
    return {
        "channel": channel,
        "accepted_candidates": len(rows),
        "rank_available": len(ranks),
        "recall_at_1": sum(rank <= 1 for rank in ranks) / len(rows) if rows else "",
        "recall_at_5": sum(rank <= 5 for rank in ranks) / len(rows) if rows else "",
        "recall_at_10": sum(rank <= 10 for rank in ranks) / len(rows) if rows else "",
        "recall_at_25": sum(rank <= 25 for rank in ranks) / len(rows) if rows else "",
        "mean_reciprocal_rank": sum(1 / rank for rank in ranks) / len(rows) if rows else "",
        "interpretation": "retrieval_of_sol_accepted_silver_parent_not_ground_truth_accuracy",
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-dir", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    sample = {row["case_id"]: row for row in csv.DictReader(
        (args.package_dir / "sampled_children.csv").open(newline="", encoding="utf-8")
    )}
    key_rows = list(csv.DictReader(
        (args.package_dir / "candidate_pool_key.csv").open(newline="", encoding="utf-8")
    ))
    key = {(row["case_id"], row["candidate_label"]): row for row in key_rows}
    response_paths = sorted((args.package_dir / "responses").glob("SHC*.json"))
    if args.require_complete and len(response_paths) != len(sample):
        raise SystemExit(f"expected {len(sample)} responses, found {len(response_paths)}")
    selections = []
    top_rankings = []
    decisions = Counter()
    by_family = Counter()
    for path in response_paths:
        response = json.loads(path.read_text(encoding="utf-8"))
        case_id = response["case_id"]
        decisions[response["decision"]] += 1
        by_family[(sample[case_id]["assigned_family"], response["decision"])] += 1
        row = {
            "case_id": case_id,
            "child_id": sample[case_id]["document_id"],
            "assigned_family": sample[case_id]["assigned_family"],
            "decision": response["decision"],
            "selected_candidate_label": response["selected_candidate_label"],
            "confidence": response["confidence"],
            "relationship_type": response["relationship_type"],
            "rationale": response["rationale"],
            "candidate_ranking": "|".join(response["candidate_ranking"]),
        }
        for sol_rank, candidate_label in enumerate(response["candidate_ranking"], 1):
            candidate = key[(case_id, candidate_label)]
            top_rankings.append({
                "case_id": case_id,
                "child_id": sample[case_id]["document_id"],
                "assigned_family": sample[case_id]["assigned_family"],
                "decision": response["decision"],
                "sol_rank": sol_rank,
                "candidate_label": candidate_label,
                "parent_id": candidate["parent_id"],
                "retrieval_sources": candidate["retrieval_sources"],
                **{
                    field: candidate[field]
                    for channel in CHANNELS for field in (f"{channel}_score", f"{channel}_rank")
                },
                "rrf_score": candidate["rrf_score"],
                "rrf_rank": candidate["rrf_rank"],
            })
        if response["decision"] == "candidate":
            candidate = key[(case_id, response["selected_candidate_label"])]
            row.update({
                "selected_parent_id": candidate["parent_id"],
                "retrieval_sources": candidate["retrieval_sources"],
                **{
                    field: candidate[field]
                    for channel in CHANNELS for field in (f"{channel}_score", f"{channel}_rank")
                },
            })
        selections.append(row)
    write_csv(args.package_dir / "sol_parent_selections.csv", selections)
    write_csv(args.package_dir / "sol_top3_rankings.csv", top_rankings)
    accepted = [row for row in selections if row["decision"] == "candidate"]
    summaries = [retrieval_summary(accepted, channel) for channel in CHANNELS]
    write_csv(args.package_dir / "metric_retrieval_summary.csv", summaries)
    family_rows = [
        {"assigned_family": family, "decision": decision, "count": count}
        for (family, decision), count in sorted(by_family.items())
    ]
    write_csv(args.package_dir / "decision_summary_by_family.csv", family_rows)
    print(json.dumps({
        "responses": len(response_paths), "decisions": dict(decisions),
        "metric_summary": summaries,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
