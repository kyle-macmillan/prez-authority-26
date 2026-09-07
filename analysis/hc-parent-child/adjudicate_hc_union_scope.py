#!/usr/bin/env python3
"""Apply the frozen formal-emergency scope to the completed HC-union review."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from build import sha256, write_csv


HERE = Path(__file__).resolve().parent
HOLDOUT = HERE / "outputs" / "hc_union_holdout"
SCOPE_EXCLUSIONS = {
    "U13": "emergency_assistance_fund_without_emergency_status_action",
    "U16": "emergency_budget_designation_without_emergency_status_action",
    "U18": "policy_response_or_emergency_recital_without_emergency_status_action",
}
MECHANICAL_CORRECTIONS = {"U06", "U07"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    source = HOLDOUT / "hc_union_holdout_adjudications.csv"
    rows = read_csv(source)
    output = []
    agreements = 0
    adjudicated = 0
    for row in rows:
        raw = row["decision"]
        review_id = row["review_id"]
        if review_id in SCOPE_EXCLUSIONS:
            scope_decision = "not_member"
            basis = SCOPE_EXCLUSIONS[review_id]
        else:
            scope_decision = raw
            basis = "raw_union_judgment_consistent_with_frozen_scope"

        if review_id in MECHANICAL_CORRECTIONS:
            revised_rule = "not_member"
        else:
            revised_rule = "member" if row["queue_type"] == "proposed" else "not_member"
        agreement = ""
        if scope_decision != "uncertain":
            adjudicated += 1
            agreement = str(scope_decision == revised_rule).lower()
            agreements += scope_decision == revised_rule
        output.append({
            **row,
            "raw_review_decision": raw,
            "scope_adjudicated_decision": scope_decision,
            "scope_adjudication_basis": basis,
            "post_revision_rule_decision": revised_rule,
            "post_revision_agreement": agreement,
        })

    output_path = HOLDOUT / "hc_union_scope_adjudications.csv"
    summary_path = HOLDOUT / "post_revision_development_summary.csv"
    write_csv(output_path, output)
    write_csv(summary_path, [{
        "status": "development_evidence_not_holdout_validation",
        "rows": len(output),
        "adjudicated": adjudicated,
        "uncertain": len(output) - adjudicated,
        "post_revision_agreements": agreements,
        "post_revision_development_agreement_rate": agreements / adjudicated,
        "scope": "formal_emergency_status_actions_only",
    }])
    manifest = {
        "kind": "hc_union_scope_adjudication",
        "status": "development_evidence_not_holdout_validation",
        "scope_decision": (
            "Emergency requires declaration, continuation, modification, renewal, "
            "revocation, or termination of formal emergency status. Emergency funds, "
            "budget designations, and responses or recitals are excluded."
        ),
        "inputs": {source.name: sha256(source)},
        "outputs": {
            output_path.name: sha256(output_path),
            summary_path.name: sha256(summary_path),
        },
    }
    (HOLDOUT / "scope_adjudication_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"adjudicated": adjudicated, "agreements": agreements}, sort_keys=True))


if __name__ == "__main__":
    main()
