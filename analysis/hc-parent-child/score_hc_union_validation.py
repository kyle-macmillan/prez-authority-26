#!/usr/bin/env python3
"""Join and summarize the category-blind HC-union holdout decisions."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from build import sha256, write_csv


HERE = Path(__file__).resolve().parent
DEFAULT_HOLDOUT = HERE / "outputs" / "hc_union_holdout"
VALID = {"member", "not_member", "uncertain"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--holdout", type=Path, default=DEFAULT_HOLDOUT)
    parser.add_argument("--decisions", type=Path)
    args = parser.parse_args()
    decisions_path = args.decisions or args.holdout / "hc_union_holdout_decisions.csv"

    queue = {row["review_id"]: row for row in read_csv(args.holdout / "family_review_queue.csv")}
    key_rows = read_csv(args.holdout / "family_review_key.csv")
    decision_rows = read_csv(decisions_path)
    decisions = {row["review_id"]: row for row in decision_rows}
    expected = {row["review_id"] for row in key_rows}
    if len(decisions) != len(decision_rows):
        raise ValueError("duplicate review_id in decisions")
    if set(decisions) != expected:
        raise ValueError("decision/key review_id mismatch")
    invalid = {row.get("decision", "") for row in decision_rows} - VALID
    if invalid:
        raise ValueError(f"invalid or incomplete decisions: {sorted(invalid)}")

    joined, grouped = [], {}
    for hidden in key_rows:
        reviewed = decisions[hidden["review_id"]]
        visible = queue[hidden["review_id"]]
        decision = reviewed["decision"]
        grouped.setdefault(hidden["queue_type"], Counter())[decision] += 1
        joined.append({
            **hidden,
            "decision": decision,
            "review_notes": reviewed.get("review_notes", ""),
            "title": visible["title"],
            "date": visible["date"],
            "president": visible["president"],
            "document_type": visible["document_type"],
            "url": visible["url"],
        })

    summary = []
    for queue_type in ("proposed", "boundary"):
        count = grouped.get(queue_type, Counter())
        adjudicated = count["member"] + count["not_member"]
        summary.append({
            "queue_type": queue_type,
            "member": count["member"],
            "not_member": count["not_member"],
            "uncertain": count["uncertain"],
            "adjudicated": adjudicated,
            "observed_union_member_rate": count["member"] / adjudicated if adjudicated else "",
            "rule_diagnostic": (
                "false_positive_evidence" if queue_type == "proposed" and count["not_member"]
                else "false_negative_evidence" if queue_type == "boundary" and count["member"]
                else "no_sampled_disagreement"
            ),
        })

    adjudications_path = args.holdout / "hc_union_holdout_adjudications.csv"
    results_path = args.holdout / "hc_union_holdout_results.csv"
    write_csv(adjudications_path, joined)
    write_csv(results_path, summary)
    manifest = {
        "kind": "category_blind_hc_union_holdout_results",
        "rows": len(joined),
        "interpretation": (
            "Deterministic stratified diagnostics; observed rates are not population "
            "precision, recall, prevalence, sensitivity, or specificity estimates."
        ),
        "inputs": {
            "family_review_queue.csv": sha256(args.holdout / "family_review_queue.csv"),
            "family_review_key.csv": sha256(args.holdout / "family_review_key.csv"),
            decisions_path.name: sha256(decisions_path),
        },
        "outputs": {
            adjudications_path.name: sha256(adjudications_path),
            results_path.name: sha256(results_path),
        },
    }
    (args.holdout / "results_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"rows": len(joined), "summary": summary}, sort_keys=True))


if __name__ == "__main__":
    main()
