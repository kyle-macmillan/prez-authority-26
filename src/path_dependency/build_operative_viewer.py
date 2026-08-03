#!/usr/bin/env python3
"""Build the separate automated-Code-3 path-dependency pilot viewer."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from build_parent_candidate_viewer import (
    _candidate_rows, build_html, build_payload, read_jsonl,
)


ROOT = Path(__file__).resolve().parents[2]
PARENT_DIR = ROOT / "data" / "parent_analysis"
PILOT_DIR = PARENT_DIR / "path_dependency_pilot" / "operative"
SEED = 20260804


def main() -> None:
    with (PILOT_DIR / "sampled_children.csv").open(newline="", encoding="utf-8") as handle:
        sampled = list(csv.DictReader(handle))
    selections = {
        row["document_id"]: row
        for row in read_jsonl(PILOT_DIR / "selected_code3_classifications.jsonl")
    }
    sampled_ids = {row["document_id"] for row in sampled}
    candidates = _candidate_rows(PARENT_DIR / "ranked_candidates.csv", sampled_ids)
    documents = read_jsonl(PARENT_DIR / "directive_similarity_documents.jsonl")
    segments = read_jsonl(PARENT_DIR / "directive_operative_segments.jsonl")
    payload = build_payload(
        sampled, documents, segments, candidates, seed=SEED,
        selections=selections, sample_prefix="OP",
        viewer_title="Path-dependency pilot — legally operative children",
        storage_namespace="path-dependency-operative-pilot-v1",
        sample_design="50 strongest automated Code 3 children, precision-first",
    )
    viewer = PILOT_DIR / "parent_candidate_viewer.html"
    viewer.write_text(build_html(payload), encoding="utf-8")
    manifest_path = PILOT_DIR / "sample_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.update({
        "candidate_comparisons": sum(len(row["candidates"]) for row in payload["children"]),
        "candidate_order": payload["candidate_order"],
        "sample_counts_by_type": dict(Counter(row["document_type"] for row in sampled)),
        "viewer": "data/parent_analysis/path_dependency_pilot/operative/parent_candidate_viewer.html",
        "comparison_pilot": "data/parent_analysis/pilot/parent_candidate_viewer.html",
    })
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote {viewer} ({len(sampled)} children, {manifest['candidate_comparisons']} comparisons)")


if __name__ == "__main__":
    main()
