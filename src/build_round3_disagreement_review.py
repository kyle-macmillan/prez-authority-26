#!/usr/bin/env python3
"""Build a focused disagreement review viewer for Round 3 annotations."""

from __future__ import annotations

import json
from pathlib import Path

from build_disagreement_review import build_html, extract_source_data


ROOT = Path(__file__).resolve().parents[1]
ROUND3_DIR = ROOT / "data" / "Annotations" / "Round 3"
KYLE_FILES = [
    ROUND3_DIR / "annotations-viewer3-kylem-2026-08-19.json",
    ROUND3_DIR / "annotations-viewer3-kyle-2026-08-19 (1).json",
]
CLAIRE_FILE = ROUND3_DIR / "[CM Part 2] annotations-viewer3-claire-2026-08-19-2.json"
THOMAS_FILE = ROUND3_DIR / "annotations-viewer3-thomas_weil-2026-08-19.json"
SOURCE_VIEWER = ROUND3_DIR / "round_3.html"
OUTPUT = ROUND3_DIR / "disagreement-review.html"


def merge_values(existing: object, incoming: object, path: str) -> object:
    if existing is None:
        return incoming
    if incoming is None or existing == incoming:
        return existing
    if isinstance(existing, dict) and isinstance(incoming, dict):
        return {
            key: incoming[key] if key not in existing else existing[key]
            if key not in existing or key not in incoming
            else merge_values(existing[key], incoming[key], f"{path}.{key}")
            for key in existing.keys() | incoming.keys()
        }
    raise ValueError(f"Conflicting Kyle annotation at {path}")


def merge_kyle_results(paths: list[Path]) -> dict:
    """Combine Kyle's separately exported document subsets into one result set."""
    merged = {"annotator": "KyleM", "document_metadata": {}}
    for path in paths:
        result = json.loads(path.read_text())
        merged["document_metadata"] = merge_values(
            merged["document_metadata"], result.get("document_metadata", {}), "document_metadata"
        )
        for doc_id, annotation in result.items():
            if doc_id not in {"annotator", "document_metadata"}:
                merged[doc_id] = merge_values(merged.get(doc_id), annotation, doc_id)
    return merged


def load_results() -> list[dict]:
    return [
        json.loads(CLAIRE_FILE.read_text()),
        merge_kyle_results(KYLE_FILES),
        json.loads(THOMAS_FILE.read_text()),
    ]


def main() -> None:
    metadata, chunks, doc_texts = extract_source_data(SOURCE_VIEWER.read_text())
    results = load_results()
    html = build_html(metadata, chunks, doc_texts, results)
    html = html.replace("Disagreement Review — Round 2", "Disagreement Review — Round 3")
    OUTPUT.write_text(html)

    payload = json.loads(html.split('<script id="payload-data" type="application/json">', 1)[1].split("</script>", 1)[0])
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    print(f"Documents shown: {len(payload['groups'][0]['docs'])}")


if __name__ == "__main__":
    main()
