#!/usr/bin/env python3
"""Build an immutable validated-profile snapshot from original and recovery runs."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from function_profile_pilot import content_hash
from validate_function_profiles import _read_jsonl, validate_responses


ROOT = Path(__file__).resolve().parents[1]


def build_snapshot(plan: Path, recovery: Path | None, documents: list[dict], segments: list[dict]):
    responses: dict[str, dict] = {}
    for path in sorted(plan.glob("batch_*/function_profile_responses.jsonl")):
        for row in _read_jsonl(path):
            responses[str(row["request_id"])] = row
    recovery_count = 0
    if recovery and recovery.exists():
        for row in _read_jsonl(recovery):
            responses[str(row["request_id"])] = row
            recovery_count += 1
    profiles, errors = validate_responses(list(responses.values()), documents, segments)
    profiles.sort(key=lambda row: int(row["document_id"]))
    snapshot_hash = content_hash([
        {"document_id": row["document_id"], "profile": row["profile"]} for row in profiles
    ])
    return profiles, errors, {
        "schema_version": 1,
        "snapshot_hash": snapshot_hash,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "provisional": bool(recovery and recovery_count < recovery_request_count(recovery)),
        "responses_considered": len(responses),
        "validated_profiles": len(profiles),
        "invalid_profiles": len(errors),
        "recovery_responses_included": recovery_count,
        "validated_document_ids": [row["document_id"] for row in profiles],
    }


def recovery_request_count(response_path: Path) -> int:
    request_path = response_path.with_name("function_profile_requests.jsonl")
    if not request_path.exists(): return 0
    with request_path.open(encoding="utf-8") as handle:
        return sum(bool(line.strip()) for line in handle)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=ROOT / "data/parent_analysis/function_profile_full_plan")
    parser.add_argument("--recovery", type=Path, default=ROOT / "data/parent_analysis/function_profile_recovery_run_001/function_profile_responses.jsonl")
    parser.add_argument("--documents", type=Path, default=ROOT / "data/parent_analysis_full/directive_similarity_documents.jsonl")
    parser.add_argument("--segments", type=Path, default=ROOT / "data/parent_analysis_full/directive_operative_segments.jsonl")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/parent_analysis/function_parent_pilot/provisional")
    args = parser.parse_args()
    profiles, errors, manifest = build_snapshot(
        args.plan, args.recovery if args.recovery.exists() else None,
        _read_jsonl(args.documents), _read_jsonl(args.segments),
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in (("profiles.jsonl", profiles), ("profile_errors.jsonl", errors)):
        with (args.output_dir / name).open("w", encoding="utf-8") as handle:
            for row in rows: handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    (args.output_dir / "snapshot_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: value for key, value in manifest.items()
                      if key != "validated_document_ids"}, sort_keys=True))


if __name__ == "__main__": main()
