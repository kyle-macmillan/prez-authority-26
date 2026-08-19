#!/usr/bin/env python3
"""Build a deduplicated, network-free Flash batch for candidate parents."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from build_function_profile_requests import (
    DEFAULT_DOCUMENTS, DEFAULT_SEGMENTS, _read_jsonl, build_requests, read_document_ids,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHILD_REQUESTS = ROOT / "data/parent_analysis/function_profile_run_001/function_profile_requests.jsonl"
DEFAULT_CANDIDATES = ROOT / "data/parent_analysis/ranked_candidates.csv"
DEFAULT_CACHE = ROOT / "data/parent_analysis/function_profiles.jsonl"
DEFAULT_COMPLETED = ROOT / "data/parent_analysis/function_profile_inventory.csv"
DEFAULT_LEGACY = ROOT / "data/parent_analysis/function_profile_prior_consumed_ids.csv"
DEFAULT_OUTPUT_DIR = ROOT / "data/parent_analysis/function_profile_candidate_run_001"


def _parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%B %d, %Y")


def build_candidate_inventory(
    child_ids: set[str], candidate_rows: list[dict[str, str]], validated_ids: set[str],
    completed_ids: set[str], legacy_ids: set[str],
) -> tuple[list[dict[str, Any]], list[str], dict[str, int]]:
    by_parent: dict[str, list[dict[str, str]]] = defaultdict(list)
    covered_children: set[str] = set()
    pairs = 0
    for row in candidate_rows:
        if row["child_id"] not in child_ids:
            continue
        if _parse_date(row["parent_date"]) >= _parse_date(row["child_date"]):
            raise ValueError(f"candidate is not strictly earlier: {row['child_id']} -> {row['parent_id']}")
        by_parent[row["parent_id"]].append(row)
        covered_children.add(row["child_id"])
        pairs += 1

    inventory = []
    requested = []
    for parent_id, rows in by_parent.items():
        validated = parent_id in validated_ids
        completed = parent_id in completed_ids
        legacy = parent_id in legacy_ids
        needs_profile = not (validated or completed or legacy)
        if needs_profile:
            requested.append(parent_id)
        inventory.append({
            "document_id": parent_id,
            "candidate_for_children": len({row["child_id"] for row in rows}),
            "candidate_pair_count": len(rows),
            "best_document_embedding_rank": min(int(row["document_embedding_rank"]) for row in rows),
            "validated_profile": str(validated).lower(),
            "prior_response_saved": str(completed).lower(),
            "legacy_consumed": str(legacy).lower(),
            "needs_profile": str(needs_profile).lower(),
        })
    inventory.sort(key=lambda row: int(row["document_id"]))
    requested.sort(key=int)
    summary = {
        "children": len(child_ids),
        "children_with_candidates": len(covered_children),
        "children_without_candidates": len(child_ids - covered_children),
        "candidate_pairs": pairs,
        "unique_candidate_parents": len(by_parent),
        "already_validated": sum(row["validated_profile"] == "true" for row in inventory),
        "prior_response_saved": sum(row["prior_response_saved"] == "true" for row in inventory),
        "legacy_consumed": sum(row["legacy_consumed"] == "true" for row in inventory),
        "requests": len(requested),
    }
    return inventory, requested, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child-requests", type=Path, default=DEFAULT_CHILD_REQUESTS)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--documents", type=Path, default=DEFAULT_DOCUMENTS)
    parser.add_argument("--segments", type=Path, default=DEFAULT_SEGMENTS)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--completed-inventory", type=Path, default=DEFAULT_COMPLETED)
    parser.add_argument("--legacy-consumed", type=Path, default=DEFAULT_LEGACY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    child_requests = _read_jsonl(args.child_requests)
    child_ids = {str(row["metadata"]["document_id"]) for row in child_requests}
    if len(child_ids) != len(child_requests):
        raise ValueError("child request file contains duplicate document IDs")
    with args.candidates.open(newline="", encoding="utf-8") as handle:
        candidate_rows = list(csv.DictReader(handle))
    validated_ids = read_document_ids(args.cache)
    completed_ids = read_document_ids(args.completed_inventory)
    legacy_ids = read_document_ids(args.legacy_consumed)
    inventory, requested_ids, summary = build_candidate_inventory(
        child_ids, candidate_rows, validated_ids, completed_ids, legacy_ids
    )

    requests = build_requests(
        _read_jsonl(args.documents), _read_jsonl(args.segments), ids=set(requested_ids),
        require_operative_segments=True,
    )
    built_ids = {row["metadata"]["document_id"] for row in requests}
    if built_ids != set(requested_ids):
        missing = sorted(set(requested_ids) - built_ids, key=int)
        raise ValueError(f"requested candidate IDs were not buildable: {missing}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    requests_path = args.output_dir / "function_profile_requests.jsonl"
    with requests_path.open("w", encoding="utf-8") as handle:
        for row in requests:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    inventory_path = args.output_dir / "candidate_parent_inventory.csv"
    with inventory_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(inventory[0]))
        writer.writeheader()
        writer.writerows(inventory)
    candidate_counts: dict[str, int] = defaultdict(int)
    for row in candidate_rows:
        if row["child_id"] in child_ids:
            candidate_counts[row["child_id"]] += 1
    coverage = [
        {"child_id": child_id, "candidate_count": candidate_counts[child_id]}
        for child_id in sorted(child_ids, key=int)
    ]
    coverage_path = args.output_dir / "child_candidate_coverage.csv"
    with coverage_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["child_id", "candidate_count"])
        writer.writeheader()
        writer.writerows(coverage)
    manifest = {
        **summary,
        "network_executed": False,
        "child_requests": str(args.child_requests),
        "candidate_rankings": str(args.candidates),
        "validated_cache": str(args.cache),
        "completed_inventory": str(args.completed_inventory),
        "legacy_consumed_ids": str(args.legacy_consumed),
        "request_file": str(requests_path),
        "candidate_parent_inventory": str(inventory_path),
        "child_candidate_coverage": str(coverage_path),
        "children_without_candidate_ids": [
            row["child_id"] for row in coverage if row["candidate_count"] == 0
        ],
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
