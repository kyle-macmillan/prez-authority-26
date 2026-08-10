#!/usr/bin/env python3
"""Create and validate grounded, authority-blind directive syntheses.

The script deliberately separates request creation from provider execution.  This
keeps the pilot reproducible across frontier providers and permits the same frozen
request set to be used in a model bake-off.  Provider responses are imported only
after they pass the shared schema and evidence-grounding checks.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


SCHEMA_VERSION = 1
PROMPT_VERSION = "parent-synthesis-v1"
SYSTEM_PROMPT = """You analyze presidential directives for drafting-precedent retrieval.
Use only the authority-blind source supplied. Do not infer, restore, or discuss legal
authority. Return JSON only. Describe the specific policy problem and every materially
operative action. Ground each statement in supplied segment IDs. Do not decide whether
another directive is a parent."""

RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["policy", "actions"],
    "properties": {
        "policy": {
            "type": "object",
            "required": [
                "problem", "subject_matter", "affected_entities", "geographic_scope",
                "triggers", "programs", "institutional_actors", "evidence_segment_ids",
            ],
        },
        "actions": {"type": "array"},
    },
}


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def source_hash(document: dict, segments: list[dict]) -> str:
    payload = {
        "text": document["cleaned_masked_text"],
        "segments": [(row["segment_id"], row["text"]) for row in segments],
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def requested_ids(
    scope: str, documents: list[dict], pilot_manifest: Path | None,
    candidates_path: Path | None,
) -> set[str]:
    if scope == "all":
        return {str(row["document_id"]) for row in documents}
    if pilot_manifest is None:
        raise ValueError("pilot scope requires --pilot-manifest")
    manifest = json.loads(pilot_manifest.read_text(encoding="utf-8"))
    pilot_rows = (
        manifest.get("children", []) + manifest.get("sampled_children", [])
        + manifest.get("development", [])
    )
    ids = {str(row.get("document_id", row.get("child_id"))) for row in pilot_rows}
    child_ids = set(ids)
    ids.update(str(value) for value in manifest.get("sampled_ids", []))
    if candidates_path:
        with candidates_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row["child_id"] in child_ids:
                    ids.add(row["parent_id"])
    return ids


def build_requests(
    documents: list[dict], segment_rows: list[dict], document_ids: set[str],
) -> list[dict]:
    by_document: dict[str, list[dict]] = {}
    for segment in segment_rows:
        by_document.setdefault(str(segment["document_id"]), []).append(segment)
    requests = []
    for document in documents:
        document_id = str(document["document_id"])
        if document_id not in document_ids:
            continue
        segments = sorted(
            by_document.get(document_id, []), key=lambda row: int(row["segment_index"])
        )
        source = {
            "document_id": document_id,
            "document_type": document["document_type"],
            "title": document.get("title", ""),
            "date": document["date"],
            "full_text_segment_id": f"{document_id}:full",
            "authority_blind_text": document["cleaned_masked_text"],
            "operative_segments": [
                {"segment_id": row["segment_id"], "text": row["text"]}
                for row in segments
            ],
        }
        requests.append({
            "request_id": f"synthesis:{document_id}:{PROMPT_VERSION}",
            "document_id": document_id,
            "schema_version": SCHEMA_VERSION,
            "prompt_version": PROMPT_VERSION,
            "source_sha256": source_hash(document, segments),
            "system_prompt": SYSTEM_PROMPT,
            "user_payload": source,
            "response_schema": RESPONSE_SCHEMA,
        })
    missing = document_ids - {row["document_id"] for row in requests}
    if missing:
        raise ValueError(f"requested document IDs not found: {sorted(missing)[:10]}")
    return requests


def validate_synthesis(response: dict, request: dict) -> dict:
    """Validate a provider-neutral response and add stable retrieval text."""
    content = response.get("output", response.get("response", response))
    if isinstance(content, str):
        content = json.loads(content)
    if not isinstance(content, dict) or not isinstance(content.get("policy"), dict):
        raise ValueError("response must contain a policy object")
    if not isinstance(content.get("actions"), list):
        raise ValueError("response must contain an actions array")
    policy = content["policy"]
    required = set(RESPONSE_SCHEMA["properties"]["policy"]["required"])
    if missing := required - set(policy):
        raise ValueError(f"policy is missing fields: {sorted(missing)}")
    source_segments = {
        row["segment_id"] for row in request["user_payload"]["operative_segments"]
    }
    for action_index, action in enumerate(content["actions"], 1):
        if not isinstance(action, dict):
            raise ValueError("each action must be an object")
        action.setdefault("action_id", f"{request['document_id']}:action:{action_index:03d}")
        evidence = action.get("evidence_segment_ids", [])
        if not evidence or not set(evidence) <= source_segments:
            raise ValueError(f"action {action_index} has invalid evidence segment IDs")
    policy_evidence = policy["evidence_segment_ids"]
    policy_sources = source_segments | {request["user_payload"]["full_text_segment_id"]}
    if not policy_evidence or not set(policy_evidence) <= policy_sources:
        raise ValueError("policy has invalid evidence segment IDs")
    embedding_parts = [
        str(policy.get("problem", "")), str(policy.get("subject_matter", "")),
        *[str(action.get(field, "")) for action in content["actions"]
          for field in ("actor", "action", "object", "mechanism", "conditions", "intended_effect")],
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "prompt_version": request["prompt_version"],
        "document_id": request["document_id"],
        "source_sha256": request["source_sha256"],
        "model": response.get("model", "unspecified"),
        "policy": policy,
        "actions": content["actions"],
        "embedding_text": "\n".join(part for part in embedding_parts if part).strip(),
    }


def import_responses(requests: list[dict], responses: list[dict]) -> list[dict]:
    by_request = {row["request_id"]: row for row in requests}
    outputs = []
    seen = set()
    for response in responses:
        request_id = response.get("request_id")
        if request_id not in by_request:
            raise ValueError(f"unknown request_id: {request_id}")
        if request_id in seen:
            raise ValueError(f"duplicate response: {request_id}")
        seen.add(request_id)
        outputs.append(validate_synthesis(response, by_request[request_id]))
    return sorted(outputs, key=lambda row: row["document_id"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=Path("data/parent_analysis"))
    parser.add_argument("--scope", choices=("pilot", "all"), default="pilot")
    parser.add_argument("--pilot-manifest", type=Path)
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--requests", type=Path)
    parser.add_argument("--responses", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    documents = read_jsonl(args.input_dir / "directive_similarity_documents.jsonl")
    segments = read_jsonl(args.input_dir / "directive_operative_segments.jsonl")
    ids = requested_ids(args.scope, documents, args.pilot_manifest, args.candidates)
    requests = build_requests(documents, segments, ids)
    requests_path = args.requests or args.input_dir / "synthesis_requests.jsonl"
    write_jsonl(requests_path, requests)
    print(f"wrote {len(requests)} frozen synthesis requests to {requests_path}")
    if args.responses:
        output = args.output or args.input_dir / "directive_syntheses.jsonl"
        syntheses = import_responses(requests, read_jsonl(args.responses))
        write_jsonl(output, syntheses)
        print(f"validated {len(syntheses)} syntheses to {output}")


if __name__ == "__main__":
    main()
