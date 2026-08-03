#!/usr/bin/env python3
"""Build Round 2 of the 139-document annotation sample."""

from __future__ import annotations

import csv
import json
import random
from collections import Counter
from pathlib import Path

from view_segments import DOC_TYPES, DATA_FILE, HOLDOUT_IDS, build_html


ROOT = Path(__file__).resolve().parents[1]
ANNOTATIONS_DIR = ROOT / "data" / "Annotations"
OUT_DIR = ANNOTATIONS_DIR / "Round 2"
OUT_VIEWER = OUT_DIR / "round_2.html"
OUT_MAP = OUT_DIR / "doc_id_map_viewer.json"
OUT_MANIFEST = OUT_DIR / "sample_manifest.json"

SAMPLE_SIZE = 139
SEED = 20260731
VIEWER_NUM = 2
SEGMENTATION = "extended_woolley_and_peters_only"


def _ids_from_json(path: Path) -> set[int]:
    data = json.loads(path.read_text())
    values = data.values() if isinstance(data, dict) else data
    if not isinstance(values, (list, tuple, set)) and not isinstance(data, dict):
        raise ValueError(f"Expected ID list or map in {path}")
    ids: set[int] = set()
    for value in values:
        try:
            ids.add(int(value))
        except (TypeError, ValueError):
            pass
    return ids


def collect_exclusions() -> dict[str, object]:
    output_dir = OUT_DIR.resolve()
    prior_maps = [
        path for path in sorted((ROOT / "data").glob("**/doc_id_map*.json"))
        if output_dir not in path.resolve().parents
    ]
    test_id_files = sorted((ROOT / "data").glob("test_sample_ids*.json"))
    prior_ids_by_file = {
        str(path.relative_to(ROOT)): sorted(_ids_from_json(path))
        for path in prior_maps
    }
    prior_ids = {doc_id for ids in prior_ids_by_file.values() for doc_id in ids}
    test_ids_by_file = {
        str(path.relative_to(ROOT)): sorted(_ids_from_json(path))
        for path in test_id_files
    }
    test_ids = {doc_id for ids in test_ids_by_file.values() for doc_id in ids}
    excluded_ids = set(HOLDOUT_IDS) | prior_ids | test_ids
    return {
        "sources": {
            "prior_maps": list(prior_ids_by_file),
            "test_id_files": list(test_ids_by_file),
            "holdout_file": "data/holdout_ids.json",
        },
        "counts": {
            "prior_sample_ids": len(prior_ids),
            "test_sample_ids": len(test_ids),
            "holdout_ids": len(HOLDOUT_IDS),
            "all_excluded_ids": len(excluded_ids),
        },
        "prior_ids_by_file": prior_ids_by_file,
        "test_ids_by_file": test_ids_by_file,
        "holdout_ids": sorted(HOLDOUT_IDS),
        "excluded_ids": sorted(excluded_ids),
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    exclusions = collect_exclusions()
    exclude_ids = set(exclusions["excluded_ids"])

    with DATA_FILE.open(newline="") as f:
        eligible_rows = [
            row for row in csv.DictReader(f) if int(row[""]) not in exclude_ids
        ]

    sampled_rows = random.Random(SEED).sample(eligible_rows, SAMPLE_SIZE)
    sampled_ids = [int(row[""]) for row in sampled_rows]
    if len(sampled_ids) != len(set(sampled_ids)):
        raise RuntimeError("Round 2 sample contains duplicate source IDs")
    overlap = set(sampled_ids) & exclude_ids
    if overlap:
        raise RuntimeError(f"Round 2 sample overlaps excluded IDs: {sorted(overlap)}")

    sampled_by_type: dict[str, list[dict]] = {}
    for row in sampled_rows:
        sampled_by_type.setdefault(row["doc_type"], []).append(row)
    rows_by_type = [
        (doc_type, prefix, label, sampled_by_type[doc_type])
        for doc_type, prefix, label in DOC_TYPES
        if doc_type in sampled_by_type
    ]

    doc_id_map = {
        f"{prefix}{index}": int(row[""])
        for _, prefix, _, rows in rows_by_type
        for index, row in enumerate(rows, start=1)
    }
    manifest = {
        "round": "Round 2",
        "source_csv": str(DATA_FILE.relative_to(ROOT)),
        "sample_size": SAMPLE_SIZE,
        "seed": SEED,
        "viewer_num": VIEWER_NUM,
        "segmentation_strategy": SEGMENTATION,
        "segmentation_note": (
            "Strategy changed for Round 2: sections are no longer used; only the "
            "extended Woolley and Peters ordering-phrase segmentation is shown."
        ),
        "exclusions": exclusions,
        "eligible_dev_rows": len(eligible_rows),
        "sample_counts_by_type": dict(Counter(row["doc_type"] for row in sampled_rows)),
        "sampled_ids": sampled_ids,
        "doc_id_map": doc_id_map,
    }

    OUT_VIEWER.write_text(
        build_html(rows_by_type, seed=SEED, viewer_num=VIEWER_NUM, wp_only=True)
    )
    OUT_MAP.write_text(json.dumps(doc_id_map, indent=2) + "\n")
    OUT_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote {OUT_VIEWER} ({len(doc_id_map)} docs)")
    print(f"Wrote {OUT_MAP}")
    print(f"Wrote {OUT_MANIFEST}")


if __name__ == "__main__":
    main()
