#!/usr/bin/env python3
"""Recode a completed family holdout for membership in the HC-family union."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

from build import sha256, write_csv


HERE = Path(__file__).resolve().parent
DEFAULT_HOLDOUT = HERE / "outputs" / "ieepa_holdout_v3"
HC_NOTE = re.compile(r"\b(?:IEEPA|emergenc\w*|block\w*|propert(?:y|ies)|monument\w*|trad(?:e|ing)|tariff\w*|dut(?:y|ies)|quota\w*)\b", re.I)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--holdout", type=Path, default=DEFAULT_HOLDOUT)
    parser.add_argument("--decisions", type=Path)
    args = parser.parse_args()
    decisions_path = args.decisions or args.holdout / "ieepa_holdout_v3_decisions.csv"

    key_rows = read_csv(args.holdout / "family_review_key.csv")
    decisions = {row["review_id"]: row for row in read_csv(decisions_path)}
    if set(decisions) != {row["review_id"] for row in key_rows}:
        raise ValueError("decision/key review_id mismatch")

    joined = []
    counts: dict[str, Counter] = {}
    for hidden in key_rows:
        reviewed = decisions[hidden["review_id"]]
        raw = reviewed["decision"]
        notes = reviewed.get("review_notes", "")
        if raw == "member":
            union, basis = "member", "raw_member"
        elif HC_NOTE.search(notes):
            union, basis = "member", "review_note_explicitly_names_an_hc_category"
        elif raw == "uncertain":
            union, basis = "uncertain", "raw_uncertain_without_cross_category_evidence"
        else:
            union, basis = "not_member", "raw_not_member_without_cross_category_evidence"
        counts.setdefault(hidden["queue_type"], Counter())[union] += 1
        joined.append({
            **hidden,
            "original_family_decision": raw,
            "hc_union_decision": union,
            "union_adjudication_basis": basis,
            "review_notes": notes,
        })

    summary = []
    for queue_type in ("proposed", "boundary"):
        count = counts.get(queue_type, Counter())
        adjudicated = count["member"] + count["not_member"]
        summary.append({
            "queue_type": queue_type,
            "member": count["member"],
            "not_member": count["not_member"],
            "uncertain": count["uncertain"],
            "adjudicated": adjudicated,
            "observed_union_member_rate": count["member"] / adjudicated if adjudicated else "",
            "interpretation": "stratified_rule_diagnostic_not_population_estimate",
        })

    adjudications_path = args.holdout / "hc_union_adjudications.csv"
    results_path = args.holdout / "hc_union_results.csv"
    write_csv(adjudications_path, joined)
    write_csv(results_path, summary)
    manifest = {
        "kind": "hc_union_holdout_results",
        "primary_estimand": "membership_in_any_high_confidence_category",
        "rows": len(joined),
        "inputs": {
            "family_review_key.csv": sha256(args.holdout / "family_review_key.csv"),
            decisions_path.name: sha256(decisions_path),
        },
        "outputs": {
            adjudications_path.name: sha256(adjudications_path),
            results_path.name: sha256(results_path),
        },
        "recode_rule": (
            "Raw members remain members. A raw not-member or uncertain decision becomes "
            "a union member only when its contemporaneous review note explicitly names "
            "another HC category. Unexplained uncertain cases remain uncertain."
        ),
    }
    (args.holdout / "hc_union_results_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"rows": len(joined), "summary": summary}, sort_keys=True))


if __name__ == "__main__":
    main()
