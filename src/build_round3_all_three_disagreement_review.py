#!/usr/bin/env python3
"""Build a Round 3 viewer for units where all three annotations differ."""

from __future__ import annotations

import json
from pathlib import Path

from build_disagreement_review import build_html, extract_source_data
from build_round3_disagreement_review import SOURCE_VIEWER, load_results


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "Annotations" / "Round 3" / "all-three-disagreement-review.html"
FIELDS = ("code", "diplomacy", "military_ops")


def code_tuple(result: dict, doc_id: str, chunk_number: str | None) -> tuple[str | None, ...]:
    if chunk_number is None:
        raw = result.get(doc_id, {}).get("classification")
    else:
        raw = result.get(doc_id, {}).get("wp_chunks", {}).get(chunk_number)
    return tuple((raw or {}).get(field) for field in FIELDS)


def all_three(values: list[tuple[str | None, ...]]) -> bool:
    return all(None not in value for value in values) and len(set(values)) == 3


def main() -> None:
    metadata, chunks, doc_texts = extract_source_data(SOURCE_VIEWER.read_text())
    results = load_results()

    directive_ids = {
        doc_id for doc_id in metadata
        if all_three([code_tuple(result, doc_id, None) for result in results])
    }
    chunk_ids = {
        (doc_id, chunk_number)
        for doc_id in metadata
        for chunk_number in chunks.get(doc_id, {})
        if all_three([code_tuple(result, doc_id, chunk_number) for result in results])
    }
    selected_ids = directive_ids | {doc_id for doc_id, _ in chunk_ids}

    filtered_metadata = {doc_id: metadata[doc_id] for doc_id in metadata if doc_id in selected_ids}
    filtered_chunks = {
        doc_id: {
            chunk_number: chunks[doc_id][chunk_number]
            for current_doc_id, chunk_number in chunk_ids
            if current_doc_id == doc_id
        }
        for doc_id in selected_ids
        if any(current_doc_id == doc_id for current_doc_id, _ in chunk_ids)
    }
    filtered_results = []
    for result in results:
        filtered = {"annotator": result.get("annotator", "")}
        for doc_id in selected_ids:
            doc = result.get(doc_id, {})
            row = {}
            if doc_id in directive_ids:
                row["classification"] = doc.get("classification")
            target_chunks = {
                chunk_number for current_doc_id, chunk_number in chunk_ids
                if current_doc_id == doc_id
            }
            if target_chunks:
                row["wp_chunks"] = {
                    chunk_number: doc.get("wp_chunks", {}).get(chunk_number)
                    for chunk_number in target_chunks
                }
            filtered[doc_id] = row
        filtered_results.append(filtered)

    html = build_html(filtered_metadata, filtered_chunks, doc_texts, filtered_results)
    html = html.replace("Disagreement Review — Round 2", "All-three Disagreement Review — Round 3")
    html = html.replace(
        '<button class="mode-btn active" id="btn-directive"',
        '<button class="mode-btn" id="btn-directive"',
    )
    html = html.replace(
        '<button class="mode-btn" id="btn-subdirective"',
        '<button class="mode-btn active" id="btn-subdirective"',
    )
    html = html.replace("var mode='directive',activeTab=0;", "var mode='subdirective',activeTab=0;")
    OUT.write_text(html)
    print(f"Wrote {OUT.relative_to(ROOT)}")
    print(f"Document-level units: {len(directive_ids)}")
    print(f"Sub-directive units: {len(chunk_ids)}")
    print(f"Documents shown: {len(selected_ids)}")


if __name__ == "__main__":
    main()
