#!/usr/bin/env python3
"""Build reviewed, authority-masked Gemini requests for function extraction.

This command only writes JSONL request files.  It never contacts Gemini.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path
from typing import Any

from function_profiles import FUNCTION_FIELDS


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCUMENTS = ROOT / "data/parent_analysis_full/directive_similarity_documents.jsonl"
DEFAULT_SEGMENTS = ROOT / "data/parent_analysis_full/directive_operative_segments.jsonl"
DEFAULT_CHILDREN = ROOT / "data/parent_analysis_full/unresolved_children.csv"
DEFAULT_CONSUMED = (
    ROOT / "data/parent_analysis/function_profiles.jsonl",
    ROOT / "data/parent_analysis/function_profile_inventory.csv",
    ROOT / "data/parent_analysis/function_profile_prior_consumed_ids.csv",
)
DEFAULT_OUTPUT = ROOT / "data/parent_analysis/function_profile_requests.jsonl"

PROMPT_VERSION = "function-profile-v1"
OUTPUT_FIELDS = ", ".join(FUNCTION_FIELDS)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def read_document_ids(path: Path) -> set[str]:
    """Read document IDs from a CSV allowlist or validated-profile JSONL cache."""
    if path.suffix == ".jsonl":
        if not path.exists():
            return set()
        return {
            str(row["document_id"])
            for row in _read_jsonl(path)
            if row.get("document_id") is not None
        }
    with path.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        if "document_id" not in (rows.fieldnames or []):
            raise ValueError(f"{path} must contain a document_id column")
        return {
            str(row["document_id"])
            for row in rows
            if row.get("document_id")
            and ("response_saved" not in row or row.get("response_saved", "").lower() == "true")
        }


def _prompt(document: dict[str, Any], segments: list[dict[str, Any]]) -> str:
    segment_block = "\n\n".join(
        f"SEGMENT {segment['segment_id']}\n{segment['text']}"
        for segment in segments
    )
    return f"""You are extracting an auditable functional representation of one presidential directive.

Rules:
- Use the supplied text as the primary evidence for every function. You may use Google Search for contextual background, definitions, institutional roles, or historical context when it helps interpret the supplied text.
- Do not use outside context to invent a function or fill an attribute that the directive does not support. If the directive is silent, use an empty string.
- The text contains [AUTHORITY] placeholders. Treat them as opaque. Never search for, identify, reconstruct, infer, or cite the masked authorities or the text they replace.
- Do not let search results override the supplied directive text.
- Policy functions are multi-label: return every distinct policy purpose supported by the document, or [] if none.
- Return zero or more operative functions for each supplied segment. Do not force a function when a segment is not operative.
- Represent functions at the level of distinct policy actions, not every sub-clause or implementation detail. Combine subordinate clauses that serve one action.
- Keep line-item numbers, formulas, classifications, and effective dates in evidence or attributes when useful, but omit them from broad labels and targets unless they are essential to the policy subject.
- Distinguish the President's directive from the subordinate actor's task: a subordinate who "shall" do something is directed to do it, not necessarily empowered or authorized. Use "empower" or "authorize" only when the text expressly grants discretion or authority.
- A short open label is required, but every label must be supported by an exact evidence excerpt.
- Use an empty string for an attribute that is not stated. Use null only for unavailable evidence offsets.
- Do not decide whether any other directive is a parent. Do not output similarity judgments.
- Return one JSON object and no Markdown.

Each function object must contain exactly these fields:
{OUTPUT_FIELDS}
For operative functions, add segment_id. Evidence offsets are relative to the full document for policy functions and to that segment for operative functions.

Document ID: {document['document_id']}
Document type: {document['document_type']}
Title: {document['title']}

FULL AUTHORITY-MASKED DOCUMENT:
{document['cleaned_masked_text']}

OPERATIVE SEGMENTS:
{segment_block}

Return this shape:
{{"document_id":"{document['document_id']}","policy_functions":[],"operative_functions":[],"notes":""}}
"""


def build_requests(documents: list[dict[str, Any]], segments: list[dict[str, Any]],
                   *, ids: set[str] | None = None, limit: int | None = None,
                   sample_per_type: int | None = None, seed: int = 20260810,
                   require_operative_segments: bool = False) -> list[dict[str, Any]]:
    by_document: dict[str, list[dict[str, Any]]] = {}
    for segment in segments:
        by_document.setdefault(str(segment["document_id"]), []).append(segment)
    selected = [doc for doc in documents if ids is None or str(doc["document_id"]) in ids]
    if require_operative_segments:
        selected = [doc for doc in selected if by_document.get(str(doc["document_id"]), [])]
    selected.sort(key=lambda row: (row["document_type"], row["date"], str(row["document_id"])))
    if sample_per_type is not None:
        if sample_per_type < 1:
            raise ValueError("sample_per_type must be positive")
        rng = random.Random(seed)
        sampled = []
        for document_type in sorted({row["document_type"] for row in selected}):
            pool = [row for row in selected if row["document_type"] == document_type]
            sampled.extend(rng.sample(pool, min(sample_per_type, len(pool))))
        selected = sorted(sampled, key=lambda row: (row["document_type"], row["date"], str(row["document_id"])))
    if limit is not None:
        selected = selected[:limit]
    requests = []
    for document in selected:
        document_id = str(document["document_id"])
        requests.append({
            "request_id": f"{PROMPT_VERSION}:{document_id}",
            "contents": _prompt(document, sorted(by_document.get(document_id, []),
                                                  key=lambda row: int(row["segment_index"]))),
            "metadata": {
                "document_id": document_id,
                "document_type": document["document_type"],
                "prompt_version": PROMPT_VERSION,
                "context_search_allowed": True,
                "operative_segment_ids": [row["segment_id"] for row in by_document.get(document_id, [])],
            },
        })
    return requests


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", type=Path, default=DEFAULT_DOCUMENTS)
    parser.add_argument("--segments", type=Path, default=DEFAULT_SEGMENTS)
    parser.add_argument(
        "--children-csv", type=Path, default=DEFAULT_CHILDREN,
        help="Allowlist of document IDs; defaults to non-ceremonial directives with no automatic edge.",
    )
    parser.add_argument(
        "--all-documents", action="store_true",
        help="Opt out of the safe children-csv allowlist and use the full documents file.",
    )
    parser.add_argument(
        "--consumed-ids", "--consumed-ids-csv", action="append", type=Path,
        help=("Validated-profile JSONL cache or legacy consumed-ID CSV to exclude; may be "
              "repeated. Defaults to both the durable cache and legacy consumed-ID list."),
    )
    parser.add_argument(
        "--ignore-consumed", action="store_true",
        help="Explicitly allow IDs listed in consumed-ids-csv (unsafe for budgeted runs).",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--document-id", action="append", dest="document_ids")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--sample-per-type", type=int)
    parser.add_argument("--seed", type=int, default=20260810)
    parser.add_argument(
        "--require-operative-segments",
        action="store_true",
        help="Exclude directives with no W&P operative segments.",
    )
    args = parser.parse_args()
    documents = _read_jsonl(args.documents)
    segments = _read_jsonl(args.segments)
    selected_ids = set(args.document_ids) if args.document_ids else None
    if args.all_documents and selected_ids is None:
        selected_ids = {str(document["document_id"]) for document in documents}
    if not args.all_documents:
        allowlist = read_document_ids(args.children_csv)
        selected_ids = allowlist if selected_ids is None else selected_ids & allowlist
    if not args.ignore_consumed:
        consumed_paths = args.consumed_ids or list(DEFAULT_CONSUMED)
        consumed = set().union(*(read_document_ids(path) for path in consumed_paths))
        selected_ids = (set() if selected_ids is None else selected_ids) - consumed
    requests = build_requests(documents, segments,
                              ids=selected_ids,
                              limit=args.limit, sample_per_type=args.sample_per_type, seed=args.seed,
                              require_operative_segments=args.require_operative_segments)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for request in requests:
            handle.write(json.dumps(request, ensure_ascii=False) + "\n")
    print(json.dumps({"requests": len(requests), "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
