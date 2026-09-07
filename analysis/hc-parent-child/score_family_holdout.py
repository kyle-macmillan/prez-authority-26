#!/usr/bin/env python3
"""Join frozen family-holdout decisions to the hidden key and summarize agreement."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from build import sha256, write_csv


HERE = Path(__file__).resolve().parent
DEFAULT_HOLDOUT = HERE / "outputs" / "family_holdout_v2"
VALID_DECISIONS = {"member", "not_member", "uncertain"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def diagnostic(proposed: Counter, boundary: Counter) -> str:
    flags = []
    if proposed["not_member"]:
        flags.append("false_positive_evidence")
    if boundary["member"]:
        flags.append("false_negative_evidence")
    return "|".join(flags) or "no_sampled_disagreement"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--holdout", type=Path, default=DEFAULT_HOLDOUT)
    parser.add_argument("--decisions", type=Path)
    args = parser.parse_args()
    decisions_path = args.decisions or args.holdout / "family_holdout_v2_decisions.csv"

    queue = {row["review_id"]: row for row in read_csv(args.holdout / "family_review_queue.csv")}
    key_rows = read_csv(args.holdout / "family_review_key.csv")
    key = {row["review_id"]: row for row in key_rows}
    decisions_rows = read_csv(decisions_path)
    decisions = {row["review_id"]: row for row in decisions_rows}

    if len(decisions) != len(decisions_rows):
        raise ValueError("duplicate review_id in decisions")
    if set(decisions) != set(key):
        raise ValueError(
            f"decision/key mismatch: missing={sorted(set(key) - set(decisions))}, "
            f"unknown={sorted(set(decisions) - set(key))}"
        )
    invalid = {row.get("decision", "") for row in decisions_rows} - VALID_DECISIONS
    if invalid:
        raise ValueError(f"invalid or incomplete decisions: {sorted(invalid)}")

    joined = []
    grouped: dict[tuple[str, str], Counter] = {}
    for hidden in key_rows:
        review_id = hidden["review_id"]
        visible = queue[review_id]
        reviewed = decisions[review_id]
        decision = reviewed["decision"]
        group = (hidden["family_id"], hidden["queue_type"])
        grouped.setdefault(group, Counter())[decision] += 1
        joined.append({
            "review_id": review_id,
            "family_id": hidden["family_id"],
            "queue_type": hidden["queue_type"],
            "document_id": hidden["document_id"],
            "decision": decision,
            "review_notes": reviewed.get("review_notes", ""),
            "title": visible["title"],
            "date": visible["date"],
            "president": visible["president"],
            "document_type": visible["document_type"],
            "url": visible["url"],
        })

    families = sorted({row["family_id"] for row in key_rows})
    summary = []
    for family in families:
        proposed = grouped.get((family, "proposed"), Counter())
        boundary = grouped.get((family, "boundary"), Counter())
        proposed_adjudicated = proposed["member"] + proposed["not_member"]
        boundary_adjudicated = boundary["member"] + boundary["not_member"]
        summary.append({
            "family_id": family,
            "proposed_member": proposed["member"],
            "proposed_not_member": proposed["not_member"],
            "proposed_uncertain": proposed["uncertain"],
            "proposed_adjudicated": proposed_adjudicated,
            "observed_proposed_agreement": (
                proposed["member"] / proposed_adjudicated if proposed_adjudicated else ""
            ),
            "boundary_member": boundary["member"],
            "boundary_not_member": boundary["not_member"],
            "boundary_uncertain": boundary["uncertain"],
            "boundary_adjudicated": boundary_adjudicated,
            "observed_boundary_member_rate": (
                boundary["member"] / boundary_adjudicated if boundary_adjudicated else ""
            ),
            "rule_diagnostic": diagnostic(proposed, boundary),
        })

    joined_path = args.holdout / "family_holdout_adjudications.csv"
    summary_path = args.holdout / "family_holdout_results.csv"
    write_csv(joined_path, joined)
    write_csv(summary_path, summary)
    manifest = {
        "kind": "descriptive_family_holdout_results",
        "rows": len(joined),
        "uncertain_decisions": sum(row["decision"] == "uncertain" for row in joined),
        "interpretation": (
            "Deterministic stratified holdout diagnostics; observed rates are not "
            "population precision or recall estimates."
        ),
        "inputs": {
            "family_review_queue.csv": sha256(args.holdout / "family_review_queue.csv"),
            "family_review_key.csv": sha256(args.holdout / "family_review_key.csv"),
            decisions_path.name: sha256(decisions_path),
        },
        "outputs": {
            joined_path.name: sha256(joined_path),
            summary_path.name: sha256(summary_path),
        },
    }
    (args.holdout / "results_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"rows": len(joined), "summary": str(summary_path)}, sort_keys=True))


if __name__ == "__main__":
    main()
