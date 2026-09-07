#!/usr/bin/env python3
"""Freeze a reproducible random child subset and its complete candidate rows."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import Counter
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""): digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--population", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--sample-size", type=int, default=1000)
    parser.add_argument("--offset", type=int, default=0, help="number of shuffled children to skip")
    parser.add_argument("--seed", type=int, default=20260814)
    args = parser.parse_args()

    with args.population.open(newline="", encoding="utf-8") as handle:
        population = list(csv.DictReader(handle))
    if len({row["document_id"] for row in population}) != len(population):
        raise ValueError("population contains duplicate child IDs")
    if args.offset < 0: parser.error("offset must be nonnegative")
    if args.offset + args.sample_size > len(population): parser.error("requested slice exceeds population")
    ordered = sorted(population, key=lambda row: int(row["document_id"]))
    random.Random(args.seed).shuffle(ordered)
    selected = ordered[args.offset:args.offset + args.sample_size]
    selected_ids = {row["document_id"] for row in selected}

    with args.candidates.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle); fields = reader.fieldnames
        candidate_rows = [row for row in reader if row["child_id"] in selected_ids]
    counts = Counter(row["child_id"] for row in candidate_rows)
    if set(counts) != selected_ids or set(counts.values()) != {25}:
        raise ValueError("selected children do not each have exactly 25 candidate rows")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    children_path = args.output_dir / "sampled_children.csv"
    with children_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(selected[0])); writer.writeheader(); writer.writerows(selected)
    candidates_path = args.output_dir / "candidate_pool.csv"
    with candidates_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(candidate_rows)
    manifest = {
        "schema_version": 1, "purpose": "Gemini ranking and rank-1 acceptance batch",
        "seed": args.seed, "offset": args.offset,
        "selection": "shuffle numeric-ID-sorted full population and take the requested offset/size slice",
        "population_size": len(population), "sample_size": len(selected),
        "candidate_rows": len(candidate_rows), "candidates_per_child": 25,
        "document_type_counts": dict(Counter(row["document_type"] for row in selected)),
        "population_sha256": sha256(args.population), "candidate_pool_sha256": sha256(candidates_path),
        "sampled_ids": [row["document_id"] for row in selected],
    }
    (args.output_dir / "sample_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key:value for key,value in manifest.items() if key != "sampled_ids"},sort_keys=True))


if __name__ == "__main__": main()
