#!/usr/bin/env python3
"""Draw the provisional/final 50-child function-parent development sample."""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import random
from collections import Counter
from pathlib import Path

from function_profile_pilot import is_trade_proclamation, parse_date
from validate_function_profiles import _read_jsonl


ROOT = Path(__file__).resolve().parents[1]


def prior_reviewed_ids(data_dir: Path) -> set[str]:
    ids = set()
    paths = set(data_dir.glob("**/sample_manifest.json"))
    paths.update(data_dir.glob("**/pilot_manifest.json"))
    for path in paths:
        try: payload = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError): continue
        ids.update(map(str, payload.get("sampled_ids", [])))
    return ids


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, default=ROOT / "data/parent_analysis/function_parent_pilot/provisional")
    parser.add_argument("--input-dir", type=Path, default=ROOT / "data/parent_analysis_full")
    parser.add_argument("--holdout", type=Path, default=ROOT / "data/holdout_ids.json")
    parser.add_argument("--seed", type=int, default=20260813)
    parser.add_argument(
        "--directive-type",
        choices=("mixed", "executive_order"),
        default="mixed",
        help="Use the original mixed design or sample only executive orders.",
    )
    parser.add_argument(
        "--sample-size", type=int,
        help="Sample size for a single-type design (required with executive_order).",
    )
    args = parser.parse_args()
    snapshot = json.loads((args.snapshot_dir / "snapshot_manifest.json").read_text())
    # A syntactically valid profile may legitimately contain no functions
    # (for example, a purely personal letter). Such a child cannot be ranked
    # by any of the three function-profile methods and is not pilot-eligible.
    profiles = set()
    with (args.snapshot_dir / "profiles.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip(): continue
            row = json.loads(line); profile = row["profile"]
            if profile.get("policy_functions") or profile.get("operative_functions"):
                profiles.add(str(row["document_id"]))
    with (args.input_dir / "unresolved_children.csv").open(newline="", encoding="utf-8") as handle:
        unresolved = list(csv.DictReader(handle))
    docs = {str(row["document_id"]): row for row in unresolved}
    holdout = json.loads(args.holdout.read_text())
    if isinstance(holdout, dict): holdout = holdout.get("document_ids", holdout.get("ids", []))
    excluded = set(map(str, holdout)) | prior_reviewed_ids(ROOT / "data/parent_analysis")
    # Every selected child only needs a nontrivial earlier comparison set. The
    # full strictly-earlier profile filter is applied when candidates are built.
    valid_parent_dates = sorted(parse_date(row["date"]) for row in unresolved
                                if str(row["document_id"]) in profiles)
    eligible = []
    for row in unresolved:
        did = str(row["document_id"])
        if did not in profiles or did in excluded: continue
        earlier = bisect.bisect_left(valid_parent_dates, parse_date(row["date"]))
        if earlier >= 25: eligible.append(row)
    strata = {
        "trade_proclamation": [row for row in eligible if is_trade_proclamation(docs[row["document_id"]])],
        "executive_order": [row for row in eligible if row["document_type"] == "executive_order"],
        "memorandum": [row for row in eligible if row["document_type"] == "memorandum"],
        "letter": [row for row in eligible if row["document_type"] == "letter"],
    }
    if args.directive_type == "executive_order":
        if not args.sample_size or args.sample_size < 1:
            parser.error("--sample-size must be positive with --directive-type executive_order")
        targets = {"executive_order": args.sample_size}
    else:
        if args.sample_size is not None:
            parser.error("--sample-size is only supported with a single directive type")
        targets = {"trade_proclamation": 20, "executive_order": 10, "memorandum": 10, "letter": 10}
    rng = random.Random(args.seed); selected = []
    for stratum, count in targets.items():
        pool = sorted(strata[stratum], key=lambda row: int(row["document_id"]))
        if len(pool) < count: raise ValueError(f"{stratum} has only {len(pool)} eligible children")
        for row in rng.sample(pool, count): selected.append({**row, "sample_stratum": stratum})
    rng.shuffle(selected)
    for index, row in enumerate(selected, 1): row["sample_id"] = f"FP{index:03d}"
    output = args.snapshot_dir / "sampled_children.csv"
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(selected[0])); writer.writeheader(); writer.writerows(selected)
    manifest = {
        "schema_version": 1, "snapshot_hash": snapshot["snapshot_hash"],
        "provisional": snapshot["provisional"], "seed": args.seed,
        "directive_type": args.directive_type,
        "sample_size": len(selected), "strata": dict(Counter(x["sample_stratum"] for x in selected)),
        "holdout_and_prior_review_exclusions": len(excluded),
        "sampled_ids": [x["document_id"] for x in selected],
    }
    (args.snapshot_dir / "pilot_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__": main()
