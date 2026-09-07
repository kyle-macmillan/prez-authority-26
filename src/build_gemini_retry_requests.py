#!/usr/bin/env python3
"""Select original Gemini requests corresponding to validator error records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--errors", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    errors = read(args.errors)
    child_ids = {str(row["child_id"]) for row in errors}
    selected = [row for row in read(args.requests) if str(row["metadata"]["child_id"]) in child_ids]
    if len(selected) != len(child_ids):
        raise ValueError(f"matched {len(selected)} requests for {len(child_ids)} error children")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for row in selected: handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"errors": len(errors), "unique_children": len(child_ids), "requests": len(selected),
                      "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__": main()
