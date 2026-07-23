#!/usr/bin/env python3
"""Build the first real annotation-round viewer."""

from __future__ import annotations

import csv
import json
import random
from collections import Counter
from pathlib import Path

from view_segments import DOC_TYPES, DATA_FILE, HOLDOUT_IDS, build_html


ROOT = Path(__file__).resolve().parents[1]
ANNOTATIONS_DIR = ROOT / "data" / "Annotations"
OUT_DIR = ANNOTATIONS_DIR / "Round 1"
OUT_VIEWER = OUT_DIR / "round_1.html"
OUT_MAP = OUT_DIR / "doc_id_map_viewer.json"
OUT_MANIFEST = OUT_DIR / "sample_manifest.json"

SANDBOX_MAPS = (
    ANNOTATIONS_DIR / "Sandbox 1" / "doc_id_map_viewer.json",
    ANNOTATIONS_DIR / "Sandbox 2" / "doc_id_map_viewer.json",
)

SAMPLE_SIZE = 139
SEED = 20260721
VIEWER_NUM = 1


def _ids_from_map(path: Path) -> set[int]:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"Expected doc-id map object in {path}")
    return {int(value) for value in data.values()}


def collect_exclusions() -> dict[str, object]:
    sandbox_ids_by_file = {
        str(path.relative_to(ROOT)): sorted(_ids_from_map(path))
        for path in SANDBOX_MAPS
    }
    sandbox_ids = {
        doc_id
        for ids in sandbox_ids_by_file.values()
        for doc_id in ids
    }
    excluded_ids = set(HOLDOUT_IDS) | sandbox_ids

    return {
        "sources": {
            "sandbox_maps": list(sandbox_ids_by_file),
            "holdout_file": "data/holdout_ids.json",
        },
        "counts": {
            "sandbox_ids": len(sandbox_ids),
            "holdout_ids": len(HOLDOUT_IDS),
            "all_excluded_ids": len(excluded_ids),
        },
        "sandbox_ids_by_file": sandbox_ids_by_file,
        "holdout_ids": sorted(HOLDOUT_IDS),
        "excluded_ids": sorted(excluded_ids),
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    exclusions = collect_exclusions()
    exclude_ids = set(exclusions["excluded_ids"])

    with DATA_FILE.open(newline="") as f:
        eligible_rows = [
            row
            for row in csv.DictReader(f)
            if int(row[""]) not in exclude_ids
        ]

    if len(eligible_rows) < SAMPLE_SIZE:
        raise RuntimeError(
            f"Expected at least {SAMPLE_SIZE} eligible dev rows, found {len(eligible_rows)}"
        )

    sampled_rows = random.Random(SEED).sample(eligible_rows, SAMPLE_SIZE)
    sampled_ids = [int(row[""]) for row in sampled_rows]
    if len(sampled_ids) != len(set(sampled_ids)):
        raise RuntimeError("Round 1 sample contains duplicate source IDs")

    overlap = set(sampled_ids) & exclude_ids
    if overlap:
        raise RuntimeError(f"Round 1 sample overlaps excluded IDs: {sorted(overlap)}")

    sampled_by_type: dict[str, list[dict]] = {}
    for row in sampled_rows:
        sampled_by_type.setdefault(row["doc_type"], []).append(row)

    rows_by_type = [
        (doc_type_key, prefix, tab_label, sampled_by_type[doc_type_key])
        for doc_type_key, prefix, tab_label in DOC_TYPES
        if doc_type_key in sampled_by_type
    ]

    doc_id_map: dict[str, int] = {}
    for _, prefix, _, rows in rows_by_type:
        for j, row in enumerate(rows, start=1):
            doc_id_map[f"{prefix}{j}"] = int(row[""])

    manifest = {
        "round": "Round 1",
        "source_csv": str(DATA_FILE.relative_to(ROOT)),
        "sample_size": SAMPLE_SIZE,
        "seed": SEED,
        "viewer_num": VIEWER_NUM,
        "exclusions": exclusions,
        "eligible_dev_rows": len(eligible_rows),
        "sample_counts_by_type": dict(Counter(row["doc_type"] for row in sampled_rows)),
        "sampled_ids": sampled_ids,
        "doc_id_map": doc_id_map,
    }

    OUT_VIEWER.write_text(build_html(rows_by_type, seed=SEED, viewer_num=VIEWER_NUM))
    OUT_MAP.write_text(json.dumps(doc_id_map, indent=2) + "\n")
    OUT_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"Wrote {OUT_VIEWER} ({len(doc_id_map)} docs)")
    print(f"Wrote {OUT_MAP}")
    print(f"Wrote {OUT_MANIFEST}")


if __name__ == "__main__":
    main()
