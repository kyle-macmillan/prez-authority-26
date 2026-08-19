#!/usr/bin/env python3
"""Freeze the 20-child development and 40-child evaluation pilot samples."""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path


TYPE_ORDER = ("executive_order", "memorandum", "proclamation", "letter")
TRADE_RE = re.compile(
    r"\b(?:tariff|trade agreement|trade relations|import(?:s|ed|ation)?|export(?:s|ed)?|"
    r"customs|duti(?:y|es)|quota|harmonized tariff schedule|free[- ]trade|"
    r"most[- ]favored[- ]nation|generalized system of preferences)\b",
    re.I,
)


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def is_trade_proclamation(row: dict, document: dict) -> bool:
    return row["document_type"] == "proclamation" and bool(
        TRADE_RE.search(f"{row.get('title', '')} {document.get('cleaned_masked_text', '')}")
    )


def sample_partition(
    rows: list[dict], documents: dict[str, dict], rng: random.Random,
    random_per_type: int, trade_extra: int, excluded_ids: set[str] | None = None,
) -> list[dict]:
    excluded_ids = excluded_ids or set()
    pools: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if str(row["document_id"]) in excluded_ids:
            continue
        pools[row["document_type"]].append(row)
    selected = []
    for document_type in TYPE_ORDER:
        pool = sorted(pools[document_type], key=lambda row: str(row["document_id"]))
        if len(pool) < random_per_type:
            raise ValueError(f"{document_type} has only {len(pool)} eligible children")
        selected.extend(rng.sample(pool, random_per_type))
    selected_ids = {str(row["document_id"]) for row in selected}
    trade_pool = sorted(
        (
            row for row in rows
            if str(row["document_id"]) not in selected_ids
            and is_trade_proclamation(row, documents[str(row["document_id"])])
        ),
        key=lambda row: str(row["document_id"]),
    )
    if len(trade_pool) < trade_extra:
        raise ValueError(f"only {len(trade_pool)} additional trade proclamations available")
    selected.extend(rng.sample(trade_pool, trade_extra))
    rng.shuffle(selected)
    return [
        {
            **row,
            "known_parent_genre": (
                "trade_proclamation"
                if is_trade_proclamation(row, documents[str(row["document_id"])]) else ""
            ),
        }
        for row in selected
    ]


def build_pilot(
    eligible: list[dict], documents: list[dict], holdout_ids: set[str], seed: int,
) -> dict:
    documents_by_id = {str(row["document_id"]): row for row in documents}
    development_frame = [
        row for row in eligible if str(row["document_id"]) not in holdout_ids
    ]
    evaluation_frame = [
        row for row in eligible if str(row["document_id"]) in holdout_ids
    ]
    # The existing holdout contains too few proclamations to supply both eight
    # random proclamation cases and eight distinct trade cases. Reserve the trade
    # diagnostic cases from the non-holdout frame before drawing development; they
    # are henceforth evaluation-only and never used for tuning.
    reserve_pool = sorted(
        (row for row in development_frame
         if is_trade_proclamation(row, documents_by_id[str(row["document_id"])])),
        key=lambda row: str(row["document_id"]),
    )
    if len(reserve_pool) < 8:
        raise ValueError("fewer than eight trade proclamations are available to reserve")
    reserved_trade = random.Random(seed + 2).sample(reserve_pool, 8)
    reserved_ids = {str(row["document_id"]) for row in reserved_trade}
    development = sample_partition(
        development_frame, documents_by_id, random.Random(seed), 4, 4,
        excluded_ids=reserved_ids,
    )
    evaluation = sample_partition(
        evaluation_frame, documents_by_id, random.Random(seed + 1), 8, 0
    )
    evaluation.extend({**row, "known_parent_genre": "trade_proclamation"}
                      for row in reserved_trade)
    random.Random(seed + 3).shuffle(evaluation)
    for phase, rows in (("development", development), ("evaluation", evaluation)):
        for index, row in enumerate(rows, 1):
            row["phase"] = phase
            row["sample_id"] = f"{'DEV' if phase == 'development' else 'EVAL'}{index:03d}"
    return {
        "schema_version": 1,
        "seed": seed,
        "definition": (
            "An earlier directive addressing the same specific policy problem through a "
            "materially similar operative mechanism; this identifies expected drafting "
            "precedent, not proven consultation."
        ),
        "eligibility": "non-ceremonial children with no reference to another directive",
        "development_design": "4 random children per type plus 4 trade proclamations",
        "evaluation_design": (
            "8 random existing-holdout children per type plus 8 trade proclamations "
            "reserved from development before tuning"
        ),
        "evaluation_only_reserved_ids": sorted(reserved_ids),
        "development": development,
        "evaluation": evaluation,
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=Path("data/parent_analysis"))
    parser.add_argument("--holdout-ids", type=Path, default=Path("data/holdout_ids.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/parent_analysis/method_pilot"))
    parser.add_argument("--seed", type=int, default=20260810)
    args = parser.parse_args()
    target_path = args.input_dir / "similarity_target_children.csv"
    if not target_path.is_file():
        target_path = args.input_dir / "unresolved_children.csv"
    with target_path.open(newline="", encoding="utf-8") as handle:
        eligible = list(csv.DictReader(handle))
    documents = read_jsonl(args.input_dir / "directive_similarity_documents.jsonl")
    holdout_ids = {str(value) for value in json.loads(args.holdout_ids.read_text())}
    pilot = build_pilot(eligible, documents, holdout_ids, args.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "pilot_manifest.json").write_text(
        json.dumps(pilot, indent=2) + "\n", encoding="utf-8"
    )
    write_csv(args.output_dir / "development_children.csv", pilot["development"])
    write_csv(args.output_dir / "evaluation_children.csv", pilot["evaluation"])
    for phase in ("development", "evaluation"):
        rows = pilot[phase]
        print(phase, len(rows), dict(Counter(row["document_type"] for row in rows)))


if __name__ == "__main__":
    main()
