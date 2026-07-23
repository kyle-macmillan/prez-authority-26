#!/usr/bin/env python3
"""Build the second 100-document annotation viewer.

The sample is drawn from the development CSV using the same per-type,
round-robin-by-president method as the first sample-100 viewer.  It excludes
all source row IDs already present in prior sample maps, test ID files, and
holdout IDs.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from view_segments import DOC_TYPES, DATA_FILE, HOLDOUT_IDS, build_html, load_rows


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
ANNOTATIONS_DIR = DATA_DIR / "Annotations"
OUT_DIR = ANNOTATIONS_DIR / "Sandbox 2"
OUT_VIEWER = OUT_DIR / "sample_100_v2.html"
OUT_MAP = OUT_DIR / "doc_id_map_viewer.json"
OUT_EXCLUDED = OUT_DIR / "excluded_prior_ids.json"

PER_TYPE = 25
SEED = 42


def _int_values_from_json(path: Path) -> set[int]:
    data = json.loads(path.read_text())
    if isinstance(data, dict):
        values = data.values()
    elif isinstance(data, list):
        values = data
    else:
        return set()

    ids: set[int] = set()
    for value in values:
        try:
            ids.add(int(value))
        except (TypeError, ValueError):
            pass
    return ids


def _dev_ids() -> set[int]:
    with DATA_FILE.open(newline="") as f:
        return {int(row[""]) for row in csv.DictReader(f)}


def collect_exclusions() -> dict[str, object]:
    """Return the prior/test/holdout ID sets used to avoid resampling."""
    output_dir = OUT_DIR.resolve()

    doc_id_map_ids: set[int] = set()
    doc_id_map_files: list[str] = []
    for path in sorted(DATA_DIR.glob("**/doc_id_map*.json")):
        if output_dir in path.resolve().parents:
            continue
        doc_id_map_ids.update(_int_values_from_json(path))
        doc_id_map_files.append(str(path.relative_to(ROOT)))

    test_ids: set[int] = set()
    test_id_files: list[str] = []
    for path in sorted(DATA_DIR.glob("test_sample_ids*.json")):
        test_ids.update(_int_values_from_json(path))
        test_id_files.append(str(path.relative_to(ROOT)))

    dev_ids = _dev_ids()
    all_prior_ids = set(HOLDOUT_IDS) | doc_id_map_ids | test_ids

    return {
        "sources": {
            "doc_id_map_files": doc_id_map_files,
            "test_id_files": test_id_files,
            "holdout_file": "data/holdout_ids.json",
        },
        "counts": {
            "doc_id_map_ids": len(doc_id_map_ids),
            "test_ids": len(test_ids),
            "holdout_ids": len(HOLDOUT_IDS),
            "all_prior_ids": len(all_prior_ids),
            "all_prior_ids_in_dev": len(all_prior_ids & dev_ids),
        },
        "ids": sorted(all_prior_ids),
        "ids_in_dev": sorted(all_prior_ids & dev_ids),
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    exclusions = collect_exclusions()
    exclude_ids = frozenset(exclusions["ids"])

    rows_by_type = []
    for doc_type_key, prefix, tab_label in DOC_TYPES:
        rows = load_rows(
            doc_type_key,
            PER_TYPE,
            seed=SEED,
            exclude_ceremonial=False,
            exclude_ids=exclude_ids,
        )
        if len(rows) != PER_TYPE:
            raise RuntimeError(
                f"Expected {PER_TYPE} {doc_type_key} rows, found {len(rows)}"
            )
        rows_by_type.append((doc_type_key, prefix, tab_label, rows))

    doc_id_map: dict[str, int] = {}
    for _, prefix, _, rows in rows_by_type:
        for j, row in enumerate(rows, start=1):
            doc_id_map[f"{prefix}{j}"] = int(row[""])

    sampled_ids = set(doc_id_map.values())
    overlap = sampled_ids & exclude_ids
    if overlap:
        raise RuntimeError(f"Sample overlaps excluded prior/test IDs: {sorted(overlap)}")

    OUT_VIEWER.write_text(build_html(rows_by_type, seed=SEED, viewer_num=2))
    OUT_MAP.write_text(json.dumps(doc_id_map, indent=2) + "\n")
    OUT_EXCLUDED.write_text(json.dumps(exclusions, indent=2) + "\n")

    print(f"Wrote {OUT_VIEWER} ({len(doc_id_map)} docs)")
    print(f"Wrote {OUT_MAP}")
    print(f"Wrote {OUT_EXCLUDED}")


if __name__ == "__main__":
    main()
