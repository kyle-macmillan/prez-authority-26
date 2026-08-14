#!/usr/bin/env python3
"""Build balanced, disjoint Gemini request shards without resubmitting known work."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("requests", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--shards", type=int, default=6)
    parser.add_argument("--responses", type=Path, action="append", default=[])
    parser.add_argument("--attempt-log", type=Path, action="append", default=[])
    parser.add_argument("--include-unknown", action="store_true")
    args = parser.parse_args()
    if args.shards < 1:
        parser.error("--shards must be positive")

    requests = rows(args.requests)
    completed = {
        str(row["request_id"])
        for path in args.responses
        for row in rows(path)
    }
    states = {}
    for path in args.attempt_log:
        for row in rows(path):
            states[str(row["request_id"])] = str(row["status"])
    unknown = {
        request_id for request_id, status in states.items()
        if status in {"submitted", "unknown_outcome"} and request_id not in completed
    }
    pending = [
        row for row in requests
        if str(row["request_id"]) not in completed
        and (args.include_unknown or str(row["request_id"]) not in unknown)
    ]

    # Longest-prompt-first greedy assignment balances expected token work while
    # remaining deterministic under request_id ties.
    pending.sort(key=lambda row: (-len(row["contents"]), str(row["request_id"])))
    shards: list[list[dict]] = [[] for _ in range(args.shards)]
    characters = [0] * args.shards
    for row in pending:
        index = min(range(args.shards), key=lambda i: (characters[i], i))
        shards[index].append(row)
        characters[index] += len(row["contents"])

    args.output_dir.mkdir(parents=True, exist_ok=True)
    shard_manifest = []
    for index, shard in enumerate(shards, 1):
        shard.sort(key=lambda row: str(row["request_id"]))
        path = args.output_dir / f"requests_{index:02d}.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for row in shard:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        shard_manifest.append({
            "shard": index,
            "requests": len(shard),
            "prompt_characters": characters[index - 1],
            "request_file": str(path),
            "response_file": str(args.output_dir / f"responses_{index:02d}.jsonl"),
        })
    manifest = {
        "schema_version": 1,
        "source_requests": str(args.requests),
        "total_requests": len(requests),
        "already_completed": len(completed),
        "held_unknown": len(unknown) if not args.include_unknown else 0,
        "sharded_pending": len(pending),
        "shards": shard_manifest,
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "completed": len(completed), "unknown": len(unknown),
        "pending": len(pending), "shards": args.shards,
        "counts": [len(shard) for shard in shards],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
