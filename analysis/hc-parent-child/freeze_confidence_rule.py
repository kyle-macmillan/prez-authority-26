#!/usr/bin/env python3
"""Choose a high-confidence rule on development edges and evaluate it once on holdout."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from build import sha256, write_csv


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "outputs"
INPUT = OUTPUT / "deterministic_confidence_benchmark.csv"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def truth(row: dict[str, str]) -> bool:
    return row["word5_selected_is_known"].casefold() == "true"


def selected(row: dict[str, str], rule: dict) -> bool:
    return (
        int(row["method_consensus_count"]) >= rule["minimum_consensus"]
        and float(row["word5_score"]) >= rule["minimum_word5_score"]
        and float(row["word5_margin"]) >= rule["minimum_word5_margin"]
    )


def evaluate(rows: list[dict[str, str]], rule: dict) -> dict:
    chosen = [row for row in rows if selected(row, rule)]
    correct = sum(truth(row) for row in chosen)
    return {
        "eligible": len(rows), "selected": len(chosen), "correct": correct,
        "precision": correct / len(chosen) if chosen else None,
        "coverage": len(chosen) / len(rows) if rows else None,
    }


def main() -> None:
    rows = read_csv(INPUT)
    development = [row for row in rows if row["benchmark_split"] == "development"]
    holdout = [row for row in rows if row["benchmark_split"] == "holdout"]
    if len(development) != 100 or len(holdout) != 100:
        raise ValueError("expected frozen 100/100 benchmark split")

    score_values = np.asarray([float(row["word5_score"]) for row in development])
    margin_values = np.asarray([float(row["word5_margin"]) for row in development])
    score_cutoffs = sorted(set(float(np.quantile(score_values, q)) for q in np.linspace(0, .95, 20)))
    margin_cutoffs = sorted(set(float(np.quantile(margin_values, q)) for q in np.linspace(0, .95, 20)))
    candidates = []
    for consensus in (1, 2, 3):
        for score in score_cutoffs:
            for margin in margin_cutoffs:
                rule = {
                    "minimum_consensus": consensus,
                    "minimum_word5_score": score,
                    "minimum_word5_margin": margin,
                }
                result = evaluate(development, rule)
                if result["selected"] >= 20 and result["precision"] >= .90:
                    candidates.append((rule, result))
    if not candidates:
        frozen = None
        status = "no_development_rule_met_90pct_with_20_cases"
        development_result = holdout_result = None
    else:
        # Most inclusive qualifying rule; ties prefer higher precision then simpler consensus.
        frozen, development_result = max(
            candidates,
            key=lambda item: (
                item[1]["selected"], item[1]["precision"],
                -item[0]["minimum_consensus"],
            ),
        )
        # This is the only point at which holdout outcomes are evaluated.
        holdout_result = evaluate(holdout, frozen)
        status = (
            "holdout_confirmed" if holdout_result["selected"] >= 20
            and holdout_result["precision"] >= .90
            else "holdout_failed_no_defensible_high_confidence_rule"
        )

    rows_out = [{
        "status": status,
        **(frozen or {
            "minimum_consensus": "", "minimum_word5_score": "", "minimum_word5_margin": ""
        }),
        **{f"development_{key}": value for key, value in (development_result or {}).items()},
        **{f"holdout_{key}": value for key, value in (holdout_result or {}).items()},
    }]
    rule_path = OUTPUT / "frozen_confidence_rule.csv"
    write_csv(rule_path, rows_out)
    manifest = {
        "kind": "masked_explicit_edge_confidence_rule",
        "status": status, "development_rows": 100, "holdout_rows": 100,
        "target": "at_least_90pct_precision_with_at_least_20_selected_cases",
        "selection_policy": "most inclusive qualifying development rule",
        "input": {INPUT.name: sha256(INPUT)}, "output": {rule_path.name: sha256(rule_path)},
    }
    (OUTPUT / "frozen_confidence_rule_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(rows_out[0], sort_keys=True))


if __name__ == "__main__":
    main()
