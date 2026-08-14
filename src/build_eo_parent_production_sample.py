#!/usr/bin/env python3
"""Select the reproducible first 1,000 unresolved operative EO children."""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import random
from collections import Counter
from datetime import datetime
from pathlib import Path

from validate_function_profiles import _read_jsonl


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data/parent_analysis_all_corpus"
DEFAULT_PROFILES = ROOT / "data/parent_analysis/canonical_profiles"
DEFAULT_OUTPUT = ROOT / "data/parent_analysis/gemini_flash_no_thinking_eo_1000"


def parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%B %d, %Y")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--profile-dir", type=Path, default=DEFAULT_PROFILES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--holdout-ids", type=Path, default=ROOT / "data/holdout_ids.json")
    parser.add_argument("--sample-size", type=int, default=1_000)
    parser.add_argument("--seed", type=int, default=20260814)
    parser.add_argument(
        "--allow-incomplete-profiles",
        action="store_true",
        help="proceed with validated profiles while recording unresolved profile exclusions",
    )
    args = parser.parse_args()

    snapshot = json.loads((args.profile_dir / "snapshot_manifest.json").read_text())
    if not snapshot.get("complete") and not args.allow_incomplete_profiles:
        raise RuntimeError("canonical profile snapshot is incomplete")
    profiles = _read_jsonl(args.profile_dir / "profiles.jsonl")
    profile_ids = {str(row["document_id"]) for row in profiles}
    if len(profile_ids) != len(profiles):
        raise ValueError("canonical registry contains duplicate profile IDs")

    documents = {
        str(row["document_id"]): row
        for row in _read_jsonl(args.input_dir / "directive_similarity_documents.jsonl")
    }
    operative_ids = {
        str(row["document_id"])
        for row in _read_jsonl(args.input_dir / "directive_operative_segments.jsonl")
    }
    if not profile_ids <= operative_ids:
        raise ValueError("canonical registry contains nonoperative document IDs")
    unresolved_profile_ids = operative_ids - profile_ids
    if unresolved_profile_ids and not args.allow_incomplete_profiles:
        raise ValueError("canonical profile IDs do not equal operative-document IDs")
    with (args.input_dir / "unresolved_children.csv").open(newline="", encoding="utf-8") as handle:
        unresolved = list(csv.DictReader(handle))

    eligible_dates = sorted(parse_date(documents[document_id]["date"]) for document_id in profile_ids)
    eligible = []
    excluded = Counter()
    for row in unresolved:
        document_id = row["document_id"]
        if row["document_type"] != "executive_order":
            continue
        if document_id not in profile_ids:
            excluded["no_canonical_operative_profile"] += 1
            continue
        earlier = bisect.bisect_left(eligible_dates, parse_date(row["date"]))
        if earlier < 25:
            excluded["fewer_than_25_earlier_profiles"] += 1
            continue
        eligible.append(row)
    if len(eligible) < args.sample_size:
        raise ValueError(f"only {len(eligible)} executive orders are eligible")

    rng = random.Random(args.seed)
    ordered = sorted(eligible, key=lambda row: int(row["document_id"]))
    rng.shuffle(ordered)
    selected = ordered[:args.sample_size]
    holdout = set(map(str, json.loads(args.holdout_ids.read_text())))
    for index, row in enumerate(selected, 1):
        row["sample_id"] = f"EO{index:04d}"
        row["partition"] = "segmentation_vesting_holdout" if row["document_id"] in holdout else "development"

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / "sampled_children.csv"
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(selected[0]))
        writer.writeheader()
        writer.writerows(selected)
    manifest = {
        "schema_version": 1,
        "purpose": "first production Gemini Flash no-thinking EO parent-identification batch",
        "seed": args.seed,
        "sample_size": len(selected),
        "canonical_snapshot_complete": bool(snapshot.get("complete")),
        "canonical_profile_count": len(profile_ids),
        "unresolved_profile_exclusions": len(unresolved_profile_ids),
        "allow_incomplete_profiles": args.allow_incomplete_profiles,
        "eligible_executive_orders": len(eligible),
        "excluded": dict(excluded),
        "partition_counts": dict(Counter(row["partition"] for row in selected)),
        "selection": "shuffle numeric-ID-sorted eligible population with random.Random(seed), take first N",
        "snapshot_hash": snapshot["snapshot_hash"],
        "canonical_build_hash": snapshot["canonical_build_hash"],
        "sampled_ids": [row["document_id"] for row in selected],
        "human_review_status": "provisional_unreviewed",
    }
    (args.output_dir / "sample_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: value for key, value in manifest.items() if key != "sampled_ids"}, sort_keys=True))


if __name__ == "__main__":
    main()
