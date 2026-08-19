#!/usr/bin/env python3
"""Build the one-profile-per-operative-directive canonical registry.

This command is network-free.  It revalidates existing derived profiles against a
frozen parent-analysis corpus, overlays explicitly supplied repair responses, and
emits reviewed request JSONL only for directives that still need a usable profile.
Raw historical request/response logs remain untouched.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from build_function_profile_requests import _prompt
from function_profiles import validate_profile
from validate_function_profiles import (
    _read_jsonl,
    normalize_profile_response,
    parse_json_response,
    validate_responses,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data/parent_analysis_all_corpus"
DEFAULT_OUTPUT = ROOT / "data/parent_analysis/canonical_profiles"
DEFAULT_SOURCES = (
    ROOT / "data/parent_analysis/function_profiles.jsonl",
    ROOT / "data/parent_analysis/function_parent_pilot/provisional/profiles.jsonl",
)
PROMPT_VERSION = "function-profile-v1"
REPAIR_PROMPT_VERSION = "function-profile-v1-canonical-repair"
CONFIRM_PROMPT_VERSION = "function-profile-v1-zero-confirmation"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(path)


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def read_source_profiles(paths: Iterable[Path]) -> dict[str, list[tuple[Path, dict[str, Any]]]]:
    profiles: dict[str, list[tuple[Path, dict[str, Any]]]] = defaultdict(list)
    for path in paths:
        if not path.exists():
            continue
        for row in _read_jsonl(path):
            profiles[str(row["document_id"])].append((path, row))
    return profiles


def current_profile(
    document_id: str,
    candidates: list[tuple[Path, dict[str, Any]]],
    document: dict[str, Any],
    segments: dict[str, str],
) -> tuple[dict[str, Any] | None, str, list[str]]:
    valid: list[tuple[Path, dict[str, Any], list[str]]] = []
    errors: list[str] = []
    for path, row in candidates:
        normalized, changes = normalize_profile_response(
            row["profile"],
            full_text=document["cleaned_masked_text"],
            segment_texts=segments,
        )
        result = validate_profile(
            normalized,
            document_id=document_id,
            full_text=document["cleaned_masked_text"],
            segment_texts=segments,
        )
        if result.errors:
            errors.extend(f"{path}: {error}" for error in result.errors)
            continue
        canonical = {
            **row,
            "document_id": document_id,
            "profile": result.profile,
            "normalizations": sorted(set([*row.get("normalizations", []), *changes])),
            "canonical_source": str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path),
        }
        valid.append((path, canonical, changes))
    if not valid:
        return None, "missing" if not candidates else "stale_or_invalid", errors
    unique = {canonical_json(row["profile"]): row for _, row, _ in valid}
    if len(unique) > 1:
        return None, "conflicting_valid_profiles", [
            f"{len(unique)} distinct valid profiles remain after normalization"
        ]
    selected = next(iter(unique.values()))
    if not selected["profile"].get("operative_functions"):
        return selected, "zero_operative_functions", errors
    return selected, "reused", errors


def validated_repairs(
    response_paths: Iterable[Path],
    documents: list[dict[str, Any]],
    segment_rows: list[dict[str, Any]],
) -> tuple[
    dict[str, tuple[dict[str, Any], dict[str, Any]]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    response_groups: dict[str, list[tuple[str, int, dict[str, Any]]]] = defaultdict(list)
    for path in response_paths:
        if not path.exists():
            continue
        for line_number, row in enumerate(_read_jsonl(path), 1):
            response_groups[str(row["request_id"])].append((str(path), line_number, row))

    document_map = {str(row["document_id"]): row for row in documents}
    segment_map: dict[str, dict[str, str]] = defaultdict(dict)
    for row in segment_rows:
        segment_map[str(row["document_id"])][str(row["segment_id"])] = row["text"]

    def is_valid_candidate(row: dict[str, Any]) -> bool:
        metadata = row.get("metadata", {})
        document_id = str(metadata.get("document_id", ""))
        document = document_map.get(document_id)
        if document is None:
            return False
        try:
            raw = parse_json_response(row.get("text", ""))
            normalized, _ = normalize_profile_response(
                raw,
                full_text=document["cleaned_masked_text"],
                segment_texts=segment_map.get(document_id, {}),
            )
            result = validate_profile(
                normalized,
                document_id=document_id,
                full_text=document["cleaned_masked_text"],
                segment_texts=segment_map.get(document_id, {}),
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            return False
        return not result.errors

    responses: dict[str, dict[str, Any]] = {}
    duplicate_audit: list[dict[str, Any]] = []
    for request_id, candidates in sorted(response_groups.items()):
        ordered = sorted(
            candidates,
            key=lambda item: (
                str(item[2].get("created_at", "9999")),
                item[0],
                item[1],
            ),
        )
        valid_ordered = [item for item in ordered if is_valid_candidate(item[2])]
        selected_path, selected_line, selected = (valid_ordered or ordered)[0]
        responses[request_id] = selected
        texts = {str(item[2].get("text", "")) for item in candidates}
        duplicate_audit.append({
            "request_id": request_id,
            "response_count": len(candidates),
            "distinct_text_count": len(texts),
            "selected_created_at": selected.get("created_at", ""),
            "selected_path": selected_path,
            "selected_line": selected_line,
            "selected_valid": bool(valid_ordered),
            "valid_response_count": len(valid_ordered),
            "selection_rule": "earliest_valid_created_at_then_path_then_line",
        })
    profiles, errors = validate_responses(list(responses.values()), documents, segment_rows)
    response_by_request = {str(row["request_id"]): row for row in responses.values()}
    output: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for profile in profiles:
        response = response_by_request[str(profile["request_id"])]
        metadata = response.get("metadata", {})
        document_id = str(profile["document_id"])
        output[document_id] = (profile, metadata)
    return output, errors, duplicate_audit


def request_row(
    document: dict[str, Any],
    segments: list[dict[str, Any]],
    *,
    build_hash: str,
    stage: str,
) -> dict[str, Any]:
    prompt = _prompt(document, segments)
    prompt_version = CONFIRM_PROMPT_VERSION if stage == "zero_confirmation" else REPAIR_PROMPT_VERSION
    if stage == "zero_confirmation":
        prompt = (
            "A prior valid extraction returned zero operative functions even though operative "
            "segments were supplied. Re-examine every supplied segment carefully. Return an "
            "operative function only when the text supports one; do not invent a function merely "
            "to avoid an empty result.\n\n" + prompt
        )
    return {
        "request_id": f"{prompt_version}:{build_hash[:12]}:{document['document_id']}",
        "contents": prompt,
        "metadata": {
            "document_id": str(document["document_id"]),
            "document_type": document["document_type"],
            "prompt_version": prompt_version,
            "canonical_build_hash": build_hash,
            "repair_stage": stage,
            "context_search_allowed": True,
            "operative_segment_ids": [str(row["segment_id"]) for row in segments],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--profile-source", type=Path, action="append")
    parser.add_argument("--repair-responses", type=Path, action="append", default=[])
    args = parser.parse_args()

    documents_path = args.input_dir / "directive_similarity_documents.jsonl"
    segments_path = args.input_dir / "directive_operative_segments.jsonl"
    documents = _read_jsonl(documents_path)
    segment_rows = _read_jsonl(segments_path)
    document_map = {str(row["document_id"]): row for row in documents}
    segments: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in segment_rows:
        segments[str(row["document_id"])].append(row)
    eligible_ids = set(segments)
    if len(eligible_ids) != 9_762:
        raise ValueError(f"expected 9,762 operative directives, found {len(eligible_ids):,}")
    missing_documents = eligible_ids - set(document_map)
    if missing_documents:
        raise ValueError(f"operative IDs missing documents: {sorted(missing_documents, key=int)[:10]}")

    corpus_hashes = {
        "documents_sha256": sha256_file(documents_path),
        "segments_sha256": sha256_file(segments_path),
        "operative_ids_sha256": content_hash(sorted(eligible_ids, key=int)),
    }
    build_hash = content_hash(corpus_hashes)
    source_paths = args.profile_source or list(DEFAULT_SOURCES)
    sources = read_source_profiles(source_paths)
    repairs, repair_errors, duplicate_audit = validated_repairs(
        args.repair_responses, documents, segment_rows
    )

    registry: list[dict[str, Any]] = []
    inventory: list[dict[str, Any]] = []
    requests: list[dict[str, Any]] = []
    error_rows: list[dict[str, Any]] = list(repair_errors)
    for document_id in sorted(eligible_ids, key=int):
        document = document_map[document_id]
        segment_list = sorted(segments[document_id], key=lambda row: int(row["segment_index"]))
        segment_map = {str(row["segment_id"]): row["text"] for row in segment_list}
        selected, status, errors = current_profile(
            document_id, sources.get(document_id, []), document, segment_map
        )
        repair = repairs.get(document_id)
        confirmed_zero = False
        if repair is not None:
            repair_profile, metadata = repair
            selected = {
                **repair_profile,
                "canonical_source": "repair_response",
                "repair_stage": metadata.get("repair_stage", "repair"),
            }
            if selected["profile"].get("operative_functions"):
                status = "repaired"
            elif metadata.get("repair_stage") == "zero_confirmation":
                status = "confirmed_zero_operative_functions"
                confirmed_zero = True
            else:
                status = "needs_zero_confirmation"
        if selected is not None and status in {
            "reused", "repaired", "confirmed_zero_operative_functions"
        }:
            selected = {
                **selected,
                "canonical_build_hash": build_hash,
                "confirmed_zero_operative_functions": confirmed_zero,
            }
            registry.append(selected)
        else:
            stage = "zero_confirmation" if status in {
                "zero_operative_functions", "needs_zero_confirmation"
            } else "repair"
            requests.append(request_row(
                document, segment_list, build_hash=build_hash, stage=stage
            ))
        inventory.append({
            "document_id": document_id,
            "document_type": document["document_type"],
            "date": document["date"],
            "operative_segment_count": len(segment_list),
            "status": status,
            "canonical_profile": str(
                status in {"reused", "repaired", "confirmed_zero_operative_functions"}
            ).lower(),
            "request_stage": (
                "" if status in {"reused", "repaired", "confirmed_zero_operative_functions"}
                else ("zero_confirmation" if status in {
                    "zero_operative_functions", "needs_zero_confirmation"
                } else "repair")
            ),
            "prior_profile_rows": len(sources.get(document_id, [])),
            "validation_error_count": len(errors),
        })
        if errors:
            error_rows.append({"document_id": document_id, "errors": errors})

    extra_ids = sorted(set(sources) - eligible_ids, key=int)
    superseded = [
        {"document_id": document_id, "profile_rows": len(sources[document_id]),
         "reason": "no_current_operative_provision"}
        for document_id in extra_ids
    ]
    complete = len(registry) == len(eligible_ids) and not requests
    unresolved = [row for row in inventory if row["request_stage"]]
    registry_ids = {str(row["document_id"]) for row in registry}
    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "canonical_build_hash": build_hash,
        "snapshot_hash": content_hash([
            {"document_id": row["document_id"], "profile": row["profile"]}
            for row in registry
        ]),
        "complete": complete,
        "operative_directives": len(eligible_ids),
        "canonical_profiles": len(registry),
        "requests_remaining": len(requests),
        "superseded_nonoperative_profile_ids": len(extra_ids),
        "status_counts": dict(Counter(row["status"] for row in inventory)),
        "profile_sources": [str(path) for path in source_paths],
        "repair_response_sources": [str(path) for path in args.repair_responses],
        "repair_response_requests": len(duplicate_audit),
        "repair_response_duplicate_requests": sum(
            row["response_count"] > 1 for row in duplicate_audit
        ),
        "repair_response_conflicting_duplicate_requests": sum(
            row["distinct_text_count"] > 1 for row in duplicate_audit
        ),
        "corpus": corpus_hashes,
        "invariants": {
            "unique_registry_ids": len(registry_ids) == len(registry),
            "registry_subset_of_operative_ids": registry_ids <= eligible_ids,
            "registry_equals_operative_ids": registry_ids == eligible_ids,
            "no_nonoperative_profiles": not (registry_ids - eligible_ids),
        },
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output_dir / "profiles.jsonl", registry)
    write_jsonl(args.output_dir / "profile_requests.jsonl", requests)
    write_jsonl(args.output_dir / "profile_validation_errors.jsonl", error_rows)
    write_jsonl(args.output_dir / "repair_response_duplicate_audit.jsonl", duplicate_audit)
    write_csv(args.output_dir / "profile_inventory.csv", inventory, list(inventory[0]))
    write_csv(
        args.output_dir / "unresolved_profiles.csv",
        unresolved,
        list(inventory[0]),
    )
    write_csv(
        args.output_dir / "superseded_profiles.csv",
        superseded,
        ["document_id", "profile_rows", "reason"],
    )
    (args.output_dir / "snapshot_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output_dir / "README.md").write_text(
        "# Canonical function profiles\n\n"
        "This directory is the only downstream profile source for full-corpus parent "
        "analysis. It contains exactly one current, validated profile per operative "
        "directive when `snapshot_manifest.json` reports `complete: true`. Historical "
        "derived caches are superseded but raw request, response, attempt, and usage logs "
        "remain preserved for audit.\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "operative_directives": len(eligible_ids),
        "canonical_profiles": len(registry),
        "requests_remaining": len(requests),
        "complete": complete,
        "status_counts": manifest["status_counts"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
