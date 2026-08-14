#!/usr/bin/env python3
"""Validate Flash runs and consolidate them into a durable profile registry."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from validate_function_profiles import _read_jsonl, validate_responses


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCUMENTS = ROOT / "data/parent_analysis_full/directive_similarity_documents.jsonl"
DEFAULT_SEGMENTS = ROOT / "data/parent_analysis_full/directive_operative_segments.jsonl"
DEFAULT_CACHE = ROOT / "data/parent_analysis/function_profiles.jsonl"
DEFAULT_INVENTORY = ROOT / "data/parent_analysis/function_profile_inventory.csv"


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(path)


def _request_map(path: Path) -> dict[str, dict[str, Any]]:
    rows = _read_jsonl(path)
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        request_id = str(row["request_id"])
        if request_id in result:
            raise ValueError(f"duplicate request_id in {path}: {request_id}")
        result[request_id] = row
    return result


def _response_map(path: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in _read_jsonl(path):
        request_id = str(row["request_id"])
        if request_id in result:
            raise ValueError(f"duplicate response in {path}: {request_id}")
        result[request_id] = row
    return result


def _attempt_state(path: Path) -> dict[str, str]:
    state: dict[str, str] = {}
    if path.exists():
        for row in _read_jsonl(path):
            state[str(row["request_id"])] = str(row["status"])
    return state


def _source_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def consolidate_runs(
    run_dirs: list[Path], documents: list[dict[str, Any]], segments: list[dict[str, Any]],
    existing: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], dict[str, tuple[list[dict], list[dict]]]]:
    registry: dict[tuple[str, str], dict[str, Any]] = {}
    for row in existing or []:
        key = (str(row["document_id"]), str(row["prompt_version"]))
        if key in registry and registry[key] != row:
            raise ValueError(f"conflicting existing profiles for {key}")
        registry[key] = row

    inventory: list[dict[str, str]] = []
    validation: dict[str, tuple[list[dict], list[dict]]] = {}
    validated_at = datetime.now(timezone.utc).isoformat()
    for run_dir in run_dirs:
        requests_path = run_dir / "function_profile_requests.jsonl"
        responses_path = run_dir / "function_profile_responses.jsonl"
        attempts_path = run_dir / "function_profile_responses.jsonl.attempts.jsonl"
        requests = _request_map(requests_path)
        responses = _response_map(responses_path)
        attempts = _attempt_state(attempts_path)
        profiles, errors = validate_responses(list(responses.values()), documents, segments)
        validation[run_dir.name] = (profiles, errors)
        profile_by_request = {str(row["request_id"]): row for row in profiles}
        errors_by_request = {str(row["request_id"]): row for row in errors}

        for request_id, request in requests.items():
            metadata = request.get("metadata", {})
            document_id = str(metadata.get("document_id", ""))
            prompt_version = str(metadata.get("prompt_version", ""))
            response = responses.get(request_id)
            profile_row = profile_by_request.get(request_id)
            error_row = errors_by_request.get(request_id)
            if profile_row is not None:
                status = "validated"
                cache_row = {
                    **profile_row,
                    "prompt_version": prompt_version,
                    "run_id": run_dir.name,
                    "response_created_at": response.get("created_at") if response else None,
                    "validated_at": validated_at,
                    "source_request": _source_path(requests_path),
                    "source_response": _source_path(responses_path),
                    "source_attempt_log": _source_path(attempts_path),
                    "usage_metadata": response.get("usage_metadata") if response else None,
                }
                key = (document_id, prompt_version)
                prior = registry.get(key)
                if prior is not None and prior.get("profile") != cache_row.get("profile"):
                    raise ValueError(f"conflicting validated profiles for {key}")
                if prior is None:
                    registry[key] = cache_row
                else:
                    # Preserve the original validation timestamp while backfilling
                    # deterministic-normalization audit details added by newer code.
                    registry[key] = {
                        **prior,
                        "normalizations": cache_row["normalizations"],
                    }
            elif error_row is not None:
                status = "invalid"
            elif response is not None:
                status = "completed_unvalidated"
            elif attempts.get(request_id) in {"submitted", "unknown_outcome"}:
                status = "unknown"
            else:
                status = "not_submitted"
            inventory.append({
                "run_id": run_dir.name,
                "request_id": request_id,
                "document_id": document_id,
                "prompt_version": prompt_version,
                "attempt_status": attempts.get(request_id, ""),
                "response_saved": "true" if response is not None else "false",
                "validation_status": status,
                "error_count": str(len(error_row.get("errors", []))) if error_row else "0",
            })

        unrequested = set(responses) - set(requests)
        if unrequested:
            raise ValueError(f"responses without requests in {run_dir}: {sorted(unrequested)}")

    cache = sorted(registry.values(), key=lambda row: (str(row["prompt_version"]), int(row["document_id"])))
    inventory.sort(key=lambda row: (row["run_id"], int(row["document_id"])))
    return cache, inventory, validation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dirs", nargs="+", type=Path)
    parser.add_argument("--documents", type=Path, default=DEFAULT_DOCUMENTS)
    parser.add_argument("--segments", type=Path, default=DEFAULT_SEGMENTS)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    args = parser.parse_args()

    existing = _read_jsonl(args.cache) if args.cache.exists() else []
    cache, inventory, validation = consolidate_runs(
        args.run_dirs, _read_jsonl(args.documents), _read_jsonl(args.segments), existing
    )
    _write_jsonl(args.cache, cache)
    for run_dir in args.run_dirs:
        profiles, errors = validation[run_dir.name]
        _write_jsonl(run_dir / "function_profiles.jsonl", profiles)
        _write_jsonl(run_dir / "function_profile_errors.jsonl", errors)

    args.inventory.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.inventory.with_name(args.inventory.name + ".tmp")
    fields = list(inventory[0]) if inventory else [
        "run_id", "request_id", "document_id", "prompt_version", "attempt_status",
        "response_saved", "validation_status", "error_count",
    ]
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(inventory)
    temporary.replace(args.inventory)
    counts: dict[str, int] = {}
    for row in inventory:
        status = row["validation_status"]
        counts[status] = counts.get(status, 0) + 1
    print(json.dumps({"cache_profiles": len(cache), "inventory": counts}, sort_keys=True))


if __name__ == "__main__":
    main()
