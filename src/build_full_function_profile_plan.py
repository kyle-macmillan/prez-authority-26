#!/usr/bin/env python3
"""Build the full eligible-corpus profile inventory and network-free checkpoints."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from build_function_profile_requests import (
    DEFAULT_DOCUMENTS, DEFAULT_SEGMENTS, _read_jsonl, build_requests, read_document_ids,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATES = ROOT / "data/parent_analysis/ranked_candidates.csv"
DEFAULT_CACHE = ROOT / "data/parent_analysis/function_profiles.jsonl"
DEFAULT_INVENTORY = ROOT / "data/parent_analysis/function_profile_inventory.csv"
DEFAULT_LEGACY = ROOT / "data/parent_analysis/function_profile_prior_consumed_ids.csv"
DEFAULT_USAGE_RESPONSES = ROOT / "data/parent_analysis/function_profile_run_001/function_profile_responses.jsonl"
DEFAULT_USAGE_REQUESTS = ROOT / "data/parent_analysis/function_profile_run_001/function_profile_requests.jsonl"
DEFAULT_OUTPUT = ROOT / "data/parent_analysis/function_profile_full_plan"


def prior_statuses(cache: set[str], inventory_rows: list[dict[str, str]],
                   legacy: set[str]) -> dict[str, str]:
    saved = {
        row["document_id"] for row in inventory_rows
        if row.get("response_saved", "").lower() == "true"
    }
    unknown = {
        row["document_id"] for row in inventory_rows
        if row.get("validation_status") == "unknown"
        or row.get("attempt_status") in {"submitted", "unknown_outcome"}
    } - saved
    document_ids = cache | saved | unknown | legacy
    result = {}
    for document_id in document_ids:
        if document_id in cache:
            result[document_id] = "validated"
        elif document_id in saved:
            result[document_id] = "completed_invalid"
        elif document_id in unknown:
            result[document_id] = "submitted_unknown"
        else:
            result[document_id] = "legacy_consumed"
    return result


def usage_baseline(requests: list[dict[str, Any]], responses: list[dict[str, Any]]) -> dict[str, float]:
    request_map = {str(row["request_id"]): row for row in requests}
    prompt_tokens = output_tokens = prompt_chars = observations = 0
    for response in responses:
        usage = response.get("usage_metadata") or {}
        request = request_map.get(str(response.get("request_id")))
        if request is None or usage.get("prompt_token_count") is None:
            continue
        prompt_tokens += int(usage["prompt_token_count"])
        output_tokens += int(usage.get("candidates_token_count") or 0)
        prompt_chars += len(request["contents"])
        observations += 1
    if not observations or not prompt_chars or not prompt_tokens:
        raise ValueError("usage baseline contains no matched token observations")
    return {
        "observations": observations,
        "prompt_tokens_per_character": prompt_tokens / prompt_chars,
        "output_tokens_per_prompt_token": output_tokens / prompt_tokens,
    }


def build_scope(candidate_rows: list[dict[str, str]]) -> tuple[set[str], set[str], dict[str, int]]:
    children = {row["child_id"] for row in candidate_rows}
    parents = {row["parent_id"] for row in candidate_rows}
    pair_counts = Counter(row["parent_id"] for row in candidate_rows)
    return children, parents, dict(pair_counts)


def interleave_by_document_type(requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Round-robin document types so each checkpoint supports broad quality review."""
    pools: dict[str, list[dict[str, Any]]] = {}
    for request in requests:
        pools.setdefault(request["metadata"]["document_type"], []).append(request)
    ordered = []
    positions = {document_type: 0 for document_type in pools}
    while len(ordered) < len(requests):
        for document_type in sorted(pools):
            position = positions[document_type]
            if position < len(pools[document_type]):
                ordered.append(pools[document_type][position])
                positions[document_type] += 1
    return ordered


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--documents", type=Path, default=DEFAULT_DOCUMENTS)
    parser.add_argument("--segments", type=Path, default=DEFAULT_SEGMENTS)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--legacy", type=Path, default=DEFAULT_LEGACY)
    parser.add_argument("--usage-requests", type=Path, default=DEFAULT_USAGE_REQUESTS)
    parser.add_argument("--usage-responses", type=Path, default=DEFAULT_USAGE_RESPONSES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()
    if args.batch_size < 1:
        raise ValueError("batch size must be positive")

    with args.candidates.open(newline="", encoding="utf-8") as handle:
        candidate_rows = list(csv.DictReader(handle))
    children, parents, parent_pair_counts = build_scope(candidate_rows)
    required = children | parents
    validated = read_document_ids(args.cache)
    with args.inventory.open(newline="", encoding="utf-8") as handle:
        prior_inventory = list(csv.DictReader(handle))
    legacy = read_document_ids(args.legacy)
    statuses = prior_statuses(validated, prior_inventory, legacy)
    never_attempted = required - set(statuses)

    documents = _read_jsonl(args.documents)
    document_map = {str(row["document_id"]): row for row in documents}
    missing_documents = required - set(document_map)
    if missing_documents:
        raise ValueError(f"required IDs missing from document artifact: {sorted(missing_documents)}")
    requests = build_requests(
        documents, _read_jsonl(args.segments), ids=never_attempted,
        require_operative_segments=True,
    )
    request_ids = {row["metadata"]["document_id"] for row in requests}
    if request_ids != never_attempted:
        raise ValueError(
            f"request coverage mismatch: missing={sorted(never_attempted-request_ids, key=int)}"
        )
    requests = interleave_by_document_type(requests)

    if args.output_dir.exists():
        protected = list(args.output_dir.glob("batch_*/function_profile_responses.jsonl*"))
        if protected:
            raise RuntimeError(f"refusing to rebuild plan with response artifacts: {protected[0]}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    batches = []
    assignment: dict[str, str] = {}
    baseline = usage_baseline(_read_jsonl(args.usage_requests), _read_jsonl(args.usage_responses))
    for offset in range(0, len(requests), args.batch_size):
        number = offset // args.batch_size + 1
        batch_id = f"batch_{number:03d}"
        batch_rows = requests[offset:offset + args.batch_size]
        batch_dir = args.output_dir / batch_id
        batch_dir.mkdir(parents=True, exist_ok=True)
        request_path = batch_dir / "function_profile_requests.jsonl"
        with request_path.open("w", encoding="utf-8") as handle:
            for row in batch_rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                assignment[row["metadata"]["document_id"]] = batch_id
        prompt_chars = sum(len(row["contents"]) for row in batch_rows)
        estimated_input = round(prompt_chars * baseline["prompt_tokens_per_character"])
        estimated_output = round(estimated_input * baseline["output_tokens_per_prompt_token"])
        batch_manifest = {
            "batch_id": batch_id,
            "requests": len(batch_rows),
            "network_executed": False,
            "prompt_characters": prompt_chars,
            "estimated_input_tokens": estimated_input,
            "estimated_output_tokens": estimated_output,
            "estimated_standard_model_cost_usd": round(
                estimated_input / 1_000_000 * 1.50 + estimated_output / 1_000_000 * 7.50, 2
            ),
            "estimate_excludes_grounding_charges": True,
        }
        (batch_dir / "manifest.json").write_text(
            json.dumps(batch_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        batches.append(batch_manifest)

    inventory = []
    child_pair_counts = Counter(row["child_id"] for row in candidate_rows)
    for document_id in sorted(required, key=int):
        status = statuses.get(document_id, "requested_not_submitted")
        inventory.append({
            "document_id": document_id,
            "document_type": document_map[document_id]["document_type"],
            "date": document_map[document_id]["date"],
            "is_eligible_child": str(document_id in children).lower(),
            "is_candidate_parent": str(document_id in parents).lower(),
            "child_candidate_count": child_pair_counts[document_id],
            "candidate_parent_pair_count": parent_pair_counts.get(document_id, 0),
            "status": status,
            "planned_batch": assignment.get(document_id, ""),
        })
    inventory_path = args.output_dir / "master_inventory.csv"
    with inventory_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(inventory[0]))
        writer.writeheader()
        writer.writerows(inventory)

    total_input = sum(row["estimated_input_tokens"] for row in batches)
    total_output = sum(row["estimated_output_tokens"] for row in batches)
    manifest = {
        "eligible_children": len(children),
        "unique_candidate_parents": len(parents),
        "candidate_pairs": len(candidate_rows),
        "required_directive_union": len(required),
        "status_counts": dict(Counter(row["status"] for row in inventory)),
        "never_attempted_before_planning": len(never_attempted),
        "batch_size": args.batch_size,
        "batches": len(batches),
        "batch_request_counts": [row["requests"] for row in batches],
        "estimated_input_tokens": total_input,
        "estimated_output_tokens": total_output,
        "estimated_standard_model_cost_usd": round(
            total_input / 1_000_000 * 1.50 + total_output / 1_000_000 * 7.50, 2
        ),
        "estimate_basis": {
            **baseline,
            "rates_usd_per_million_tokens": {"input": 1.50, "output": 7.50},
            "excludes_google_search_grounding_charges": True,
        },
        "network_executed": False,
        "master_inventory": str(inventory_path),
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
