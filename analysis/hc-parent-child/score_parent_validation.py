#!/usr/bin/env python3
"""Score the frozen preliminary HC parent-pair review without conflating scope flags."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from build import sha256, write_csv


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "outputs"
RELATIONSHIP = {"parent", "not_parent"}
SCOPE = {"not_high_confidence_family", "out_of_scope"}
VALID = RELATIONSHIP | SCOPE | {"uncertain"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    decisions_path = OUTPUT / "parent_pair_decisions.csv"
    key_path = OUTPUT / "parent_pair_review_key.csv"
    queue_path = OUTPUT / "parent_pair_review.csv"
    decisions_rows = read_csv(decisions_path)
    key_rows = read_csv(key_path)
    decisions = {row["pair_id"]: row for row in decisions_rows}
    key = {row["pair_id"]: row for row in key_rows}
    queue = {row["pair_id"]: row for row in read_csv(queue_path)}
    if len(decisions) != len(decisions_rows) or set(decisions) != set(key):
        raise ValueError("decision/key mismatch or duplicate pair_id")
    invalid = {row.get("decision", "") for row in decisions_rows} - VALID
    if invalid:
        raise ValueError(f"invalid or incomplete decisions: {sorted(invalid)}")

    joined, grouped = [], {}
    for hidden in key_rows:
        reviewed, visible = decisions[hidden["pair_id"]], queue[hidden["pair_id"]]
        decision = reviewed["decision"]
        grouped.setdefault(hidden["score_stratum"], Counter())[decision] += 1
        grouped.setdefault("all", Counter())[decision] += 1
        joined.append({
            **hidden, "decision": decision,
            "review_notes": reviewed.get("review_notes", ""),
            "child_title": visible["child_title"], "parent_title": visible["parent_title"],
            "child_date": visible["child_date"], "parent_date": visible["parent_date"],
        })

    summary = []
    for stratum in ("all", "operative_profile", "document_semantic"):
        count = grouped.get(stratum, Counter())
        relationship_n = count["parent"] + count["not_parent"]
        summary.append({
            "score_stratum": stratum, "reviewed_pairs": sum(count.values()),
            "plausible_parent": count["parent"], "not_parent": count["not_parent"],
            "relationship_adjudicated": relationship_n,
            "observed_plausible_parent_rate": count["parent"] / relationship_n if relationship_n else "",
            "uncertain": count["uncertain"],
            "scope_or_family_exclusions": sum(count[value] for value in SCOPE),
            "interpretation": "preliminary_stratified_diagnostic_not_population_estimate",
        })

    joined_path = OUTPUT / "parent_pair_adjudications.csv"
    summary_path = OUTPUT / "parent_pair_results.csv"
    write_csv(joined_path, joined); write_csv(summary_path, summary)
    manifest = {
        "kind": "preliminary_hc_parent_pair_results", "rows": len(joined),
        "denominator_rule": (
            "Only parent/not_parent judgments enter the plausible-parent rate. "
            "Uncertain and scope/family exclusions are reported separately."
        ),
        "inputs": {path.name: sha256(path) for path in (decisions_path, key_path, queue_path)},
        "outputs": {joined_path.name: sha256(joined_path), summary_path.name: sha256(summary_path)},
    }
    (OUTPUT / "parent_pair_results_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"rows": len(joined), "summary": summary}, sort_keys=True))


if __name__ == "__main__":
    main()
