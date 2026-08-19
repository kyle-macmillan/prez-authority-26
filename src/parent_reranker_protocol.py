#!/usr/bin/env python3
"""Freeze shared reranker inputs and normalize frontier/non-frontier outputs."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


RUBRIC_VERSION = "parent-reranker-v1"
OUTPUT_FIELDS = (
    "child_id", "parent_id", "reranker", "policy_problem_match",
    "operative_mechanism_match", "expected_precedent", "score", "rank",
    "evidence_segment_ids", "rationale",
)
RUBRIC = """Assess expected drafting precedent, not proven consultation.
A strong parent must address the same specific policy problem AND use a materially
similar operative mechanism. Generic subject overlap, shared actors, boilerplate, or
text reuse alone is insufficient. Score policy_problem_match, operative_mechanism_match,
and expected_precedent from 0 (none) through 3 (strong). Cite supplied segment IDs.
The source is authority-blind; do not infer or discuss authority."""


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def requests_for_candidates(
    candidates: list[dict], documents: list[dict], segments: list[dict],
    syntheses: list[dict] | None = None,
) -> list[dict]:
    docs = {str(row["document_id"]): row for row in documents}
    synth = {str(row["document_id"]): row for row in syntheses or []}
    by_document: dict[str, list[dict]] = defaultdict(list)
    for segment in segments:
        by_document[str(segment["document_id"])].append(segment)
    requests = []
    for row in candidates:
        child_id, parent_id = str(row["child_id"]), str(row["parent_id"])
        representations = {}
        for role, document_id in (("child", child_id), ("candidate_parent", parent_id)):
            document = docs[document_id]
            representations[role] = {
                "document_id": document_id,
                "document_type": document["document_type"],
                "date": document["date"],
                "title": document.get("title", ""),
                "synthesis": synth.get(document_id),
                "operative_segments": [
                    {"segment_id": item["segment_id"], "text": item["text"]}
                    for item in sorted(
                        by_document.get(document_id, []),
                        key=lambda item: int(item["segment_index"]),
                    )
                ],
            }
        requests.append({
            "request_id": f"rerank:{child_id}:{parent_id}:{RUBRIC_VERSION}",
            "child_id": child_id,
            "parent_id": parent_id,
            "rubric_version": RUBRIC_VERSION,
            "rubric": RUBRIC,
            "input": representations,
            "response_format": {
                "policy_problem_match": "integer 0..3",
                "operative_mechanism_match": "integer 0..3",
                "expected_precedent": "integer 0..3",
                "evidence_segment_ids": "array of supplied segment IDs",
                "rationale": "brief string",
            },
        })
    return requests


def no_llm_baseline(candidates: list[dict], rrf_k: int = 20) -> list[dict]:
    by_child: dict[str, list[dict]] = defaultdict(list)
    for row in candidates:
        by_child[str(row["child_id"])].append(row)
    output = []
    rank_fields = [key for key in candidates[0] if key.endswith("_rank")] if candidates else []
    for child_id, rows in by_child.items():
        scores = {}
        for row in rows:
            parent_id = str(row["parent_id"])
            if str(row.get("rrf_rank", "")).strip():
                scores[parent_id] = 1.0 / float(row["rrf_rank"])
            else:
                scores[parent_id] = sum(
                    1.0 / (rrf_k + int(row[field]))
                    for field in rank_fields if str(row.get(field, "")).strip()
                )
        ordered = sorted(scores, key=lambda key: (-scores[key], key))
        for rank, parent_id in enumerate(ordered, 1):
            output.append({
                "child_id": child_id, "parent_id": parent_id,
                "reranker": "no_llm_rrf", "policy_problem_match": "",
                "operative_mechanism_match": "", "expected_precedent": "",
                "score": scores[parent_id], "rank": rank,
                "evidence_segment_ids": "", "rationale": "",
            })
    return output


def normalize_qwen(rows: list[dict], model: str, mode: str = "full") -> list[dict]:
    score_field = f"qwen_{'full_operative' if mode == 'full' else 'matched_pairs'}_score"
    rank_field = f"qwen_{'full_operative' if mode == 'full' else 'matched_pairs'}_rank"
    return [{
        "child_id": row["child_id"], "parent_id": row["parent_id"],
        "reranker": model, "policy_problem_match": "",
        "operative_mechanism_match": "", "expected_precedent": "",
        "score": row[score_field], "rank": row[rank_field],
        "evidence_segment_ids": "", "rationale": "",
    } for row in rows]


def normalize_responses(requests: list[dict], responses: list[dict], model: str) -> list[dict]:
    request_by_id = {row["request_id"]: row for row in requests}
    by_child: dict[str, list[dict]] = defaultdict(list)
    for response in responses:
        request = request_by_id.get(response.get("request_id"))
        if request is None:
            raise ValueError(f"unknown request_id: {response.get('request_id')}")
        content = response.get("output", response.get("response", response))
        if isinstance(content, str):
            content = json.loads(content)
        scores = [
            int(content[field]) for field in (
                "policy_problem_match", "operative_mechanism_match", "expected_precedent"
            )
        ]
        if any(score < 0 or score > 3 for score in scores):
            raise ValueError("reranker scores must be integers from 0 through 3")
        evidence = content.get("evidence_segment_ids", [])
        supplied = {
            segment["segment_id"]
            for role in request["input"].values()
            for segment in role["operative_segments"]
        }
        if not set(evidence) <= supplied:
            raise ValueError("reranker cited an unknown segment ID")
        row = {
            "child_id": request["child_id"], "parent_id": request["parent_id"],
            "reranker": model,
            "policy_problem_match": scores[0],
            "operative_mechanism_match": scores[1],
            "expected_precedent": scores[2],
            # The conjunctive minimum prevents a high score on only one dimension
            # from dominating the rank.
            "score": min(scores),
            "evidence_segment_ids": json.dumps(evidence),
            "rationale": content.get("rationale", ""),
        }
        by_child[row["child_id"]].append(row)
    output = []
    for rows in by_child.values():
        rows.sort(key=lambda row: (-row["score"], -row["expected_precedent"], row["parent_id"]))
        for rank, row in enumerate(rows, 1):
            output.append({**row, "rank": rank})
    return output


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader(); writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=Path("data/parent_analysis"))
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--requests", type=Path)
    parser.add_argument("--responses", type=Path)
    parser.add_argument("--qwen-results", type=Path)
    parser.add_argument("--qwen-mode", choices=("full", "matched"), default="full")
    parser.add_argument("--model", help="Stable label, e.g. qwen3-0.6b, qwen3-4b, frontier")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    candidate_path = args.candidates or args.input_dir / "hybrid_candidate_pool.csv"
    with candidate_path.open(newline="", encoding="utf-8") as handle:
        candidates = list(csv.DictReader(handle))
    if candidates and "selected_top_10" in candidates[0]:
        candidates = [row for row in candidates if row["selected_top_10"].lower() == "true"]
    documents = read_jsonl(args.input_dir / "directive_similarity_documents.jsonl")
    segments = read_jsonl(args.input_dir / "directive_operative_segments.jsonl")
    synthesis_path = args.input_dir / "directive_syntheses.jsonl"
    syntheses = read_jsonl(synthesis_path) if synthesis_path.is_file() else []
    requests = requests_for_candidates(candidates, documents, segments, syntheses)
    request_path = args.requests or args.input_dir / "reranker_requests.jsonl"
    with request_path.open("w", encoding="utf-8") as handle:
        for row in requests:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    baseline = no_llm_baseline(candidates)
    output = args.output or args.input_dir / "reranker_comparison.csv"
    if args.responses or args.qwen_results:
        if not args.model:
            raise ValueError("--model is required when importing model results")
        existing = []
        if output.is_file():
            with output.open(newline="", encoding="utf-8") as handle:
                existing = [
                    row for row in csv.DictReader(handle)
                    if row["reranker"] not in {"no_llm_rrf", args.model}
                ]
        if args.qwen_results:
            with args.qwen_results.open(newline="", encoding="utf-8") as handle:
                model_rows = normalize_qwen(list(csv.DictReader(handle)), args.model, args.qwen_mode)
        else:
            model_rows = normalize_responses(requests, read_jsonl(args.responses), args.model)
        rows = baseline + existing + model_rows
    else:
        rows = baseline
    write_csv(output, rows)
    print(f"{len(requests)} frozen pair requests; {len(rows)} rankings; {output}")


if __name__ == "__main__":
    main()
