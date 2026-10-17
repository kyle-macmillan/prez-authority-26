#!/usr/bin/env python3
"""Combine finalized Round 2 codes with reviewed and unanimous Round 3 codes."""

from __future__ import annotations

import json
from pathlib import Path

from build_disagreement_review import extract_source_data
from build_round3_disagreement_review import ROUND3_DIR, SOURCE_VIEWER, load_results


ROOT = Path(__file__).resolve().parents[1]
ROUND2_FILE = ROOT / "data/Annotations/Round 2/round-2-finalized-validation-labels-with-subdirectives.json"
REVIEW_FILE = ROUND3_DIR / "round3-ground-truth-review.json"
DOC_ID_MAP_FILE = ROUND3_DIR / "doc_id_map_viewer.json"
OUTPUT = ROOT / "data/Annotations/round-2-and-3-subdirective-code-labels.json"
VALID_CODES = {"0", "1", "2", "3", "4"}


def build_dataset(round2: dict, chunks: dict, results: list[dict],
                  doc_id_map: dict, review: dict) -> dict:
    review_records = review["records"]
    reviewed = {(row["round_id"], str(row["chunk_number"])): row for row in review_records}
    if len(reviewed) != len(review_records):
        raise ValueError("Duplicate Round 3 review records")

    records = []
    for row in round2["subdirective_records"]:
        code = row["labels"]["code"]
        if code not in VALID_CODES:
            raise ValueError(f"Invalid Round 2 code: {row['round_id']} #{row['chunk_number']}")
        records.append({
            "annotation_round": "Round 2",
            "global_dev_id": str(row["global_dev_id"]),
            "round_id": row["round_id"],
            "chunk_number": str(row["chunk_number"]),
            "text": row["text"],
            "labels": {"code": code},
            "label_source": "finalized_round_2",
        })

    counts = {"round_2_finalized": len(records), "round_3_reviewed": 0,
              "round_3_unanimous": 0}
    excluded = []
    for doc_id, doc_chunks in chunks.items():
        for chunk_number, chunk_text in doc_chunks.items():
            key = (doc_id, chunk_number)
            votes = [
                (result.get(doc_id, {}).get("wp_chunks", {}).get(chunk_number) or {}).get("code")
                for result in results
            ]
            if any(code is None for code in votes):
                excluded.append({"round_id": doc_id, "chunk_number": chunk_number,
                                 "reason": "missing_annotation", "codes": votes})
                continue
            if len(set(votes)) == 1:
                if key in reviewed:
                    raise ValueError(f"Unanimous chunk has a review record: {key}")
                code, source = votes[0], "unanimous_round_3"
                counts["round_3_unanimous"] += 1
            else:
                row = reviewed.pop(key, None)
                if row is None:
                    raise ValueError(f"Missing Round 3 review record: {key}")
                code, source = row["ground_truth_code"], "reviewed_round_3"
                counts["round_3_reviewed"] += 1
            if code not in VALID_CODES:
                raise ValueError(f"Invalid Round 3 code: {key}: {code}")
            records.append({
                "annotation_round": "Round 3",
                "global_dev_id": str(doc_id_map[doc_id]),
                "round_id": doc_id,
                "chunk_number": chunk_number,
                "text": chunk_text,
                "labels": {"code": code},
                "label_source": source,
            })

    if reviewed:
        raise ValueError(f"Review records do not match disputed Round 3 chunks: {sorted(reviewed)}")
    keys = [(row["global_dev_id"], row["chunk_number"]) for row in records]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate sub-directives across rounds")
    return {
        "schema": "presidential-subdirective-code-labels",
        "schema_version": 1,
        "label_fields": ["code"],
        "sources": {
            "round_2": str(ROUND2_FILE.relative_to(ROOT)),
            "round_3_review": str(REVIEW_FILE.relative_to(ROOT)),
            "round_3_annotations": "data/Annotations/Round 3/",
        },
        "counts": counts,
        "excluded_round_3": excluded,
        "records": records,
    }


def main() -> None:
    round2 = json.loads(ROUND2_FILE.read_text())
    _, chunks, _ = extract_source_data(SOURCE_VIEWER.read_text())
    results = load_results()
    doc_id_map = json.loads(DOC_ID_MAP_FILE.read_text())
    review = json.loads(REVIEW_FILE.read_text())
    dataset = build_dataset(round2, chunks, results, doc_id_map, review)
    OUTPUT.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    print(dataset["counts"])
    print(f"Excluded Round 3 chunks: {len(dataset['excluded_round_3'])}")


if __name__ == "__main__":
    main()
