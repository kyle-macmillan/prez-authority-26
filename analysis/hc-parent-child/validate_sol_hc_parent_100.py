#!/usr/bin/env python3
"""Validate the frozen Sol HC parent-identification package without model calls."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path


HERE = Path(__file__).resolve().parent
PACKAGE = HERE / "outputs/sol_hc_parent_100"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%B %d, %Y")


def main() -> None:
    manifest = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
    sample = list(csv.DictReader((PACKAGE / "sampled_children.csv").open(newline="", encoding="utf-8")))
    key_rows = list(csv.DictReader((PACKAGE / "candidate_pool_key.csv").open(newline="", encoding="utf-8")))
    requests = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((PACKAGE / "requests").glob("SHC*.json"))]
    assert len(sample) == len(requests) == manifest["rows"] == 100
    assert len({row["document_id"] for row in sample}) == 100
    assert Counter(row["assigned_family"] for row in sample) == Counter({family: 20 for family in manifest["per_assigned_family"]})
    assert digest(PACKAGE / "sampled_children.csv") == manifest["outputs"]["sampled_children.csv"]
    assert digest(PACKAGE / "candidate_pool_key.csv") == manifest["outputs"]["candidate_pool_key.csv"]
    sample_by_case = {row["case_id"]: row for row in sample}
    key_by_case: dict[str, list[dict]] = {}
    for row in key_rows:
        key_by_case.setdefault(row["case_id"], []).append(row)
    for request in requests:
        case_id = request["case_id"]
        assert case_id in sample_by_case
        assert "assigned_family" not in json.dumps(request)
        assert "document_id" not in json.dumps(request)
        labels = [row["candidate_label"] for row in request["candidates"]]
        assert len(labels) == len(set(labels)) == len(key_by_case[case_id])
        assert set(labels) == {row["candidate_label"] for row in key_by_case[case_id]}
        child_date = parse_date(request["child"]["date"])
        assert all(parse_date(row["date"]) < child_date for row in request["candidates"])
    json.loads((HERE / "sol_parent_response.schema.json").read_text(encoding="utf-8"))
    print(json.dumps({
        "status": "valid", "cases": len(requests), "candidate_pairs": len(key_rows),
        "candidate_count_min": min(len(row["candidates"]) for row in requests),
        "candidate_count_max": max(len(row["candidates"]) for row in requests),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
