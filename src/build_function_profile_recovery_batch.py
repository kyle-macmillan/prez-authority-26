#!/usr/bin/env python3
"""Build a network-free rerun batch for invalid full-plan function profiles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from validate_function_profiles import _read_jsonl, validate_responses


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAN = ROOT / "data/parent_analysis/function_profile_full_plan"
DEFAULT_OUTPUT = ROOT / "data/parent_analysis/function_profile_recovery_run_001"
DEFAULT_DOCUMENTS = ROOT / "data/parent_analysis_full/directive_similarity_documents.jsonl"
DEFAULT_SEGMENTS = ROOT / "data/parent_analysis_full/directive_operative_segments.jsonl"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_recovery(plan_dir: Path, documents: list[dict], segments: list[dict]) -> tuple[list[dict], dict]:
    requests: dict[str, dict] = {}
    responses: list[dict] = []
    request_batches: dict[str, str] = {}
    source_batches: dict[str, int] = {}
    for batch_dir in sorted(plan_dir.glob("batch_*")):
        batch_requests = _read_jsonl(batch_dir / "function_profile_requests.jsonl")
        batch_responses = _read_jsonl(batch_dir / "function_profile_responses.jsonl")
        for request in batch_requests:
            request_id = str(request["request_id"])
            if request_id in requests:
                raise ValueError(f"duplicate planned request ID: {request_id}")
            requests[request_id] = request
            request_batches[request_id] = batch_dir.name
        responses.extend(batch_responses)

    _, errors = validate_responses(responses, documents, segments)
    invalid_ids = {str(row["request_id"]) for row in errors}
    for request_id in invalid_ids:
        batch = request_batches[request_id]
        source_batches[batch] = source_batches.get(batch, 0) + 1

    recovery = [requests[request_id] for request_id in sorted(
        invalid_ids, key=lambda value: int(requests[value]["metadata"]["document_id"])
    )]
    manifest = {
        "purpose": "rerun strictly invalid function-profile responses after conservative local normalization",
        "requests": len(recovery),
        "prompt_version": "function-profile-v1",
        "source_plan": str(plan_dir.resolve().relative_to(ROOT)),
        "source_invalid_counts": source_batches,
        "preserves_original_logs": True,
    }
    return recovery, manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--documents", type=Path, default=DEFAULT_DOCUMENTS)
    parser.add_argument("--segments", type=Path, default=DEFAULT_SEGMENTS)
    args = parser.parse_args()
    response_artifacts = list(args.output_dir.glob("function_profile_responses.jsonl*"))
    if response_artifacts:
        raise RuntimeError(f"refusing to replace recovery response artifacts: {response_artifacts}")
    requests, manifest = build_recovery(
        args.plan_dir, _read_jsonl(args.documents), _read_jsonl(args.segments)
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(args.output_dir / "function_profile_requests.jsonl", requests)
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
