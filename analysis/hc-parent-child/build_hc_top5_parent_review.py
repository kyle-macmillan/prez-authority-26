#!/usr/bin/env python3
"""Build a blinded top-five drafting-template review for HC pilot children."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from build import AUTOMATIC_EDGES, DEFAULT_OUTPUT, assign_families, balanced_sample, explicit_parent_child_ids, load_documents, load_profiles, read_csv, write_csv


HERE = Path(__file__).resolve().parent
OUTPUT = DEFAULT_OUTPUT / "hc_top5_parent_review"


def reviewed_children() -> set[str]:
    paths = [
        DEFAULT_OUTPUT / "family_parent_rule_development" / "parent_pair_review.csv",
        DEFAULT_OUTPUT / "parent_pair_noncontrol_scope_screen.csv",
        DEFAULT_OUTPUT / "parent_pair_adjudications.csv",
        DEFAULT_OUTPUT / "parent_pair_review.csv",
    ]
    result = set()
    for path in paths:
        if path.is_file():
            result.update(row["child_id"] for row in read_csv(path) if row.get("child_id"))
    return result


def slot_order(review_id: str) -> list[int]:
    return sorted(range(5), key=lambda rank: hashlib.sha256(f"top5-display:{review_id}:{rank}".encode()).hexdigest())


def main() -> None:
    documents, _ = load_documents()
    assign_families(documents, load_profiles())
    by_id = {row["document_id"]: row for row in documents}
    explicit = explicit_parent_child_ids(read_csv(AUTOMATIC_EDGES))
    seen = reviewed_children()
    candidates = defaultdict(list)
    for row in read_csv(DEFAULT_OUTPUT / "top5_candidate_sets.csv"):
        if row["method"] == "word_5_shingle":
            candidates[row["child_id"]].append(row)
    available = []
    for child_id, rows in candidates.items():
        child = by_id[child_id]
        if (
            child_id in seen or child_id in explicit or child["analysis_scope_reason"]
            or not child["families"] or len(rows) != 5
        ):
            continue
        rows.sort(key=lambda row: int(row["candidate_rank"]))
        available.append({
            "document_id": child_id, "child_id": child_id,
            "primary_family": sorted(child["families"])[0], "document_type": child["document_type"],
        })
    selected = balanced_sample(available, 10, ("primary_family", "document_type"), "hc-top5-parent-review-v1")
    if len(selected) != 10:
        raise ValueError(f"expected 10 review children, found {len(selected)}")
    queue, key = [], []
    for number, item in enumerate(selected, 1):
        review_id = f"T{number:02d}"
        child = by_id[item["child_id"]]
        ranked = sorted(candidates[item["child_id"]], key=lambda row: int(row["candidate_rank"]))
        displayed = [ranked[index] for index in slot_order(review_id)]
        queue.append({
            "review_id": review_id, "child_id": child["document_id"], "child_title": child["title"],
            "child_date": child["date"], "child_type": child["document_type"], "child_url": child["url"],
            "child_non_vesting_text": child["primary_text"], "decision": "", "review_notes": "",
            **{
                f"candidate_{slot}_title": by_id[row["parent_id"]]["title"]
                for slot, row in zip("abcde", displayed)
            },
            **{
                f"candidate_{slot}_date": by_id[row["parent_id"]]["date"]
                for slot, row in zip("abcde", displayed)
            },
            **{
                f"candidate_{slot}_type": by_id[row["parent_id"]]["document_type"]
                for slot, row in zip("abcde", displayed)
            },
            **{
                f"candidate_{slot}_url": by_id[row["parent_id"]]["url"]
                for slot, row in zip("abcde", displayed)
            },
            **{
                f"candidate_{slot}_non_vesting_text": by_id[row["parent_id"]]["primary_text"]
                for slot, row in zip("abcde", displayed)
            },
        })
        key.append({
            "review_id": review_id, "child_id": child["document_id"],
            "primary_family": item["primary_family"],
            **{f"candidate_{slot}_parent_id": row["parent_id"] for slot, row in zip("abcde", displayed)},
            **{f"candidate_{slot}_word5_rank": row["candidate_rank"] for slot, row in zip("abcde", displayed)},
        })
    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT / "top5_review_queue.csv", queue)
    write_csv(OUTPUT / "top5_review_key.csv", key)
    (OUTPUT / "manifest.json").write_text(json.dumps({
        "kind": "hc_top5_drafting_template_review", "rows": len(queue),
        "method": "word_5_shingle", "candidate_set_size": 5,
        "blinding": "family, score, rank, and display order hidden",
        "seen_children_excluded": len(seen), "explicit_children_excluded": len(explicit),
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"rows": len(queue), "output": str(OUTPUT)}, sort_keys=True))


if __name__ == "__main__":
    from collections import defaultdict
    main()
