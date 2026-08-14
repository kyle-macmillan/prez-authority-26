"""Compare preserved original authority spans after parentage is fixed."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _authority_key(value: dict[str, Any]) -> tuple[str, str]:
    return (str(value.get("kind", "")), " ".join(str(value.get("text", "")).casefold().split()))


def compare_authorities(child: dict[str, Any], parent: dict[str, Any]) -> dict[str, Any]:
    child_values = child.get("original_authorities", child.get("masked_authorities", []))
    parent_values = parent.get("original_authorities", parent.get("masked_authorities", []))
    child_counts = Counter(_authority_key(value) for value in child_values)
    parent_counts = Counter(_authority_key(value) for value in parent_values)

    def expand(counts: Counter) -> list[dict[str, str]]:
        result = []
        for (kind, text), count in sorted(counts.items()):
            result.extend({"kind": kind, "text": text} for _ in range(count))
        return result

    retained = child_counts & parent_counts
    added = child_counts - parent_counts
    removed = parent_counts - child_counts
    return {
        "child_id": child["document_id"],
        "parent_id": parent["document_id"],
        "retained": expand(retained),
        "child_added": expand(added),
        "parent_omitted": expand(removed),
        "diverged": bool(added or removed),
    }


def _read_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return {str(row["document_id"]): row for row in map(json.loads, handle) if row}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", type=Path, required=True)
    parser.add_argument("--edges", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    documents = _read_jsonl(args.documents)
    with args.edges.open(newline="", encoding="utf-8") as handle:
        edges = csv.DictReader(handle)
        rows = []
        for edge in edges:
            child = documents[str(edge["child_id"])]
            parent = documents[str(edge["parent_id"])]
            rows.append(compare_authorities(child, parent))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"comparisons": len(rows), "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
