#!/usr/bin/env python3
"""Build the Round 4 minority subdirective review viewer."""

from __future__ import annotations

import json
from pathlib import Path

from build_disagreement_review import extract_source_data
from build_round3_unique_category_review import build_html, minority_units


ROOT = Path(__file__).resolve().parents[1]
ROUND4_DIR = ROOT / "data/Annotations/Round 4"
SOURCE_VIEWER = ROUND4_DIR / "round_4.html"
ANNOTATIONS = [
    ROUND4_DIR / "CM round 4 part 2.json",
    ROUND4_DIR / "annotations-viewer4-kylem-2026-10-07.json",
    ROUND4_DIR / "annotations-viewer4-thomas_weil-2026-10-07.json",
]
OUTPUT = ROUND4_DIR / "unique-category-review.html"


def main() -> None:
    metadata, chunks, doc_texts = extract_source_data(SOURCE_VIEWER.read_text())
    results = [json.loads(path.read_text()) for path in ANNOTATIONS]
    for result in results:
        missing = [f"{doc_id}:{chunk_number}"
                   for doc_id, doc_chunks in chunks.items()
                   for chunk_number in doc_chunks
                   if (result.get(doc_id, {}).get("wp_chunks", {}).get(chunk_number) or {}).get("code")
                   not in {"0", "1", "2", "3", "4"}]
        if missing:
            raise ValueError(f"{result['annotator']} has unclassified subdirectives: {', '.join(missing)}")

    html = build_html(metadata, chunks, doc_texts, results)
    html = html.replace("Round 3", "Round 4").replace("round3-", "round4-")
    OUTPUT.write_text(html)
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    for group in minority_units(chunks, results):
        print(f"{group['label']}: {len(group['units'])} minority subdirectives")


if __name__ == "__main__":
    main()
