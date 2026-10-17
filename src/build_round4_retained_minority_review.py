#!/usr/bin/env python3
"""Build a joint review of Round 4 minority votes retained after individual review."""

from __future__ import annotations

import json
from pathlib import Path

from build_disagreement_review import VALUE_LABELS, extract_source_data
from build_round3_unique_category_review import TEMPLATE, minority_units, reviewed_units
from build_round4_unique_category_review import ANNOTATIONS, ROOT, ROUND4_DIR, SOURCE_VIEWER


REVIEW_EXPORTS = [
    ROUND4_DIR / "claire-round4-minority-review.json",
    ROUND4_DIR / "round4-minority-review-kylem.json",
    ROUND4_DIR / "round4-minority-review-thomas-weil.json",
]
OUTPUT = ROUND4_DIR / "retained-minority-review.html"


def retained_units(chunks: dict, results: list[dict], reviews: list[dict]) -> list[dict]:
    groups = minority_units(chunks, results)
    by_name = {review["annotator"]: review for review in reviews}
    if set(by_name) != {group["label"] for group in groups}:
        raise ValueError("Minority review annotators do not match the Round 4 annotations")
    for group in groups:
        review = by_name[group["label"]]
        if review.get("schema") != "round4-minority-subdirective-review":
            raise ValueError(f"Unexpected review schema for {group['label']}")
        expected = {(unit["docId"], unit["chunkNumber"]) for unit in group["units"]}
        records = review["records"]
        actual = [(record["round_id"], str(record["chunk_number"])) for record in records]
        if len(actual) != len(set(actual)) or set(actual) != expected:
            raise ValueError(f"Incomplete or duplicate minority review for {group['label']}")
        if any(record["reviewed_code"] not in {None, "0", "1", "2", "3", "4"} for record in records):
            raise ValueError(f"Invalid reviewed code for {group['label']}")
    return [unit for unit in reviewed_units(groups, reviews)
            if unit["groundTruthCode"] == unit["originalCode"]]


def main() -> None:
    metadata, chunks, doc_texts = extract_source_data(SOURCE_VIEWER.read_text())
    results = [json.loads(path.read_text()) for path in ANNOTATIONS]
    reviews = [json.loads(path.read_text()) for path in REVIEW_EXPORTS]
    units = retained_units(chunks, results, reviews)
    selected_docs = {unit["docId"] for unit in units}
    payload = {
        "annotators": [result["annotator"] for result in results],
        "groups": [{"label": "Retained minority votes", "groundTruth": True, "units": units}],
        "metadata": {doc_id: metadata[doc_id] for doc_id in selected_docs},
        "docTexts": {doc_id: doc_texts[doc_id] for doc_id in selected_docs},
        "chunks": {doc_id: chunks[doc_id] for doc_id in selected_docs},
        "valueLabels": {code: VALUE_LABELS[code] for code in ("0", "1", "2", "3", "4")},
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = TEMPLATE.replace("__PAYLOAD__", encoded).replace(
        "__DESCRIPTION__",
        "These are the subdirectives where one annotator disagreed with the other two and kept their original code after review. Choose the final category for each case.",
    )
    html = (html.replace("Minority Sub-directive Review — Round 3", "Retained Minority Review — Round 4")
                .replace("round3-", "round4-")
                .replace("round4-ground-truth-review", "round4-retained-minority-review"))
    OUTPUT.write_text(html)
    print(f"Wrote {OUTPUT.relative_to(ROOT)} ({len(units)} retained minority votes)")


if __name__ == "__main__":
    main()
