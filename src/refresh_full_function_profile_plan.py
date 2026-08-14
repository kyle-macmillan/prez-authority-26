#!/usr/bin/env python3
"""Refresh full-plan statuses and completed batch manifests without submitting requests."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from build_function_profile_requests import read_document_ids


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAN = ROOT / "data/parent_analysis/function_profile_full_plan"
DEFAULT_CACHE = ROOT / "data/parent_analysis/function_profiles.jsonl"
DEFAULT_INVENTORY = ROOT / "data/parent_analysis/function_profile_inventory.csv"


def refreshed_status(document_id: str, *, validated: set[str],
                     run_status: dict[str, dict[str, str]], prior: str) -> str:
    if document_id in validated:
        return "validated"
    row = run_status.get(document_id)
    if row and row.get("response_saved", "").lower() == "true":
        return "completed_invalid"
    if row and (row.get("validation_status") == "unknown"
                or row.get("attempt_status") in {"submitted", "unknown_outcome"}):
        return "submitted_unknown"
    return prior


def _write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    args = parser.parse_args()

    validated = read_document_ids(args.cache)
    with args.inventory.open(newline="", encoding="utf-8") as handle:
        run_rows = list(csv.DictReader(handle))
    run_status = {row["document_id"]: row for row in run_rows}
    master_path = args.plan_dir / "master_inventory.csv"
    with master_path.open(newline="", encoding="utf-8") as handle:
        master = list(csv.DictReader(handle))
    for row in master:
        row["status"] = refreshed_status(
            row["document_id"], validated=validated, run_status=run_status, prior=row["status"]
        )
    temporary = master_path.with_name(master_path.name + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(master[0]))
        writer.writeheader()
        writer.writerows(master)
    temporary.replace(master_path)

    plan_manifest_path = args.plan_dir / "manifest.json"
    plan_manifest = json.loads(plan_manifest_path.read_text(encoding="utf-8"))
    plan_manifest["status_counts"] = dict(Counter(row["status"] for row in master))
    plan_manifest["network_executed"] = any(
        row["status"] in {"validated", "completed_invalid"} and row["planned_batch"]
        for row in master
    )
    _write_json(plan_manifest_path, plan_manifest)

    refreshed_batches = 0
    for batch_dir in sorted(args.plan_dir.glob("batch_*")):
        responses_path = batch_dir / "function_profile_responses.jsonl"
        if not responses_path.exists():
            continue
        responses = [json.loads(line) for line in responses_path.open(encoding="utf-8") if line.strip()]
        profiles_path = batch_dir / "function_profiles.jsonl"
        errors_path = batch_dir / "function_profile_errors.jsonl"
        profiles = sum(1 for line in profiles_path.open(encoding="utf-8") if line.strip())
        errors = sum(1 for line in errors_path.open(encoding="utf-8") if line.strip())
        prompt_tokens = sum((row.get("usage_metadata") or {}).get("prompt_token_count") or 0
                            for row in responses)
        output_tokens = sum((row.get("usage_metadata") or {}).get("candidates_token_count") or 0
                            for row in responses)
        manifest_path = batch_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update({
            "network_executed": True,
            "responses_saved": len(responses),
            "validated_profiles": profiles,
            "invalid_profiles": errors,
            "actual_input_tokens": prompt_tokens,
            "actual_output_tokens": output_tokens,
            "actual_standard_model_cost_usd": round(
                prompt_tokens / 1_000_000 * 1.50 + output_tokens / 1_000_000 * 7.50, 2
            ),
            "actual_cost_excludes_grounding_charges": True,
        })
        _write_json(manifest_path, manifest)
        refreshed_batches += 1
    print(json.dumps({
        "master_rows": len(master), "status_counts": plan_manifest["status_counts"],
        "refreshed_batches": refreshed_batches,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
