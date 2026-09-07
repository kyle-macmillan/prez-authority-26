#!/usr/bin/env python3
"""Combine retained initial cases and replacements into the final HC-union result."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from build import sha256, write_csv


HERE = Path(__file__).resolve().parent
INITIAL = HERE / "outputs" / "hc_union_holdout_v2"
REPLACEMENTS = HERE / "outputs" / "hc_union_holdout_v2_replacements"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    scope_path = INITIAL / "confirmatory_scope_adjudication.csv"
    initial_adjudications_path = INITIAL / "hc_union_holdout_adjudications.csv"
    replacement_key_path = REPLACEMENTS / "family_review_key.csv"
    replacement_decisions_path = REPLACEMENTS / "hc_union_holdout_v2_replacement_decisions.csv"
    initial = {row["review_id"]: row for row in read_csv(initial_adjudications_path)}
    retained = [row for row in read_csv(scope_path) if row["confirmatory_status"] == "retained"]
    replacement_key = {row["review_id"]: row for row in read_csv(replacement_key_path)}
    replacement_decisions = {
        row["review_id"]: row for row in read_csv(replacement_decisions_path)
    }
    if set(replacement_key) != set(replacement_decisions):
        raise ValueError("replacement decision/key mismatch")

    rows = []
    for scope in retained:
        source = initial[scope["review_id"]]
        rows.append({
            "case_id": scope["review_id"], "document_id": scope["document_id"],
            "queue_type": scope["original_stratum"], "decision": scope["raw_decision"],
            "case_source": "initial_confirmatory_draw_retained",
            "decision_provenance": "downloaded_browser_review",
            "matched_families": source["matched_families"], "title": source["title"],
        })
    replacement_queue = {
        row["review_id"]: row for row in read_csv(REPLACEMENTS / "family_review_queue.csv")
    }
    for review_id, hidden in replacement_key.items():
        decision = replacement_decisions[review_id]
        visible = replacement_queue[review_id]
        rows.append({
            "case_id": review_id, "document_id": hidden["document_id"],
            "queue_type": hidden["queue_type"], "decision": decision["decision"],
            "case_source": "explicit_link_replacement",
            "decision_provenance": "reviewer_direct_statement_in_chat_2026-08-23",
            "matched_families": hidden["matched_families"], "title": visible["title"],
        })

    if len(rows) != 10:
        raise ValueError(f"expected ten final cases, found {len(rows)}")
    grouped: dict[str, Counter] = {}
    for row in rows:
        grouped.setdefault(row["queue_type"], Counter())[row["decision"]] += 1
    summary = []
    for queue_type in ("proposed", "boundary"):
        count = grouped[queue_type]
        adjudicated = count["member"] + count["not_member"]
        summary.append({
            "queue_type": queue_type, "member": count["member"],
            "not_member": count["not_member"], "uncertain": count["uncertain"],
            "adjudicated": adjudicated,
            "observed_union_member_rate": count["member"] / adjudicated,
            "expected_decision": "member" if queue_type == "proposed" else "not_member",
            "observed_rule_agreement": (
                count["member"] / adjudicated if queue_type == "proposed"
                else count["not_member"] / adjudicated
            ),
            "interpretation": "stratified_confirmatory_diagnostic_not_population_estimate",
        })

    cases_path = INITIAL / "final_confirmatory_cases.csv"
    results_path = INITIAL / "final_confirmatory_results.csv"
    write_csv(cases_path, rows); write_csv(results_path, summary)
    manifest = {
        "kind": "final_hc_union_confirmatory_results",
        "rows": 10, "excluded_initial_explicit_link_cases": ["V01", "V04"],
        "replacement_decision_provenance": "reviewer direct statement in chat on 2026-08-23",
        "interpretation": (
            "Five proposed and five hard-boundary cases; descriptive confirmatory "
            "diagnostic, not a population accuracy or prevalence estimate."
        ),
        "inputs": {path.name: sha256(path) for path in (
            scope_path, initial_adjudications_path, replacement_key_path,
            replacement_decisions_path,
        )},
        "outputs": {cases_path.name: sha256(cases_path), results_path.name: sha256(results_path)},
    }
    (INITIAL / "final_confirmatory_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"rows": 10, "summary": summary}, sort_keys=True))


if __name__ == "__main__":
    main()
