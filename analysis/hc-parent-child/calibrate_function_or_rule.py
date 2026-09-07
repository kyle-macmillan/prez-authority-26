#!/usr/bin/env python3
"""Calibrate an exploratory text-OR-function signal on HC cases and controls.

This script does not label path dependency.  It measures whether an earlier
directive covers a child's operative Flash-profile functions, joins that signal
to the frozen five-word score, and exposes candidate OR-rule cutoffs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from build import (
    DEFAULT_OUTPUT,
    FUNCTION_EMBEDDINGS,
    FunctionSimilarity,
    load_documents,
    sha256,
    write_csv,
)


TEXT_THRESHOLD = 0.2206716686487198
CONTROL_QUANTILES = (0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90, 0.925, 0.95, 0.975)
MARGIN_QUANTILES = (0.0, 0.50, 0.75, 0.90)


def auc(positive: list[float], negative: list[float]) -> float | str:
    if not positive or not negative:
        return ""
    wins = sum(a > b for a in positive for b in negative)
    ties = sum(a == b for a in positive for b in negative)
    return (wins + 0.5 * ties) / (len(positive) * len(negative))


def stratified_split(rows: list[dict]) -> None:
    """Assign unique documents evenly to deterministic development/holdout sets."""
    by_group: dict[str, list[dict]] = {"hc": [], "control": []}
    for row in rows:
        by_group[row["group"]].append(row)
    for group, items in by_group.items():
        items.sort(key=lambda row: hashlib.sha256(
            f"hc-function-or-v1:{group}:{row['child_id']}".encode()
        ).hexdigest())
        midpoint = (len(items) + 1) // 2
        for index, row in enumerate(items):
            row["split"] = "development" if index < midpoint else "holdout"


def best_function_match(
    child_id: str,
    documents_by_id: dict[str, dict],
    scorer: FunctionSimilarity,
) -> dict:
    child = documents_by_id[child_id]
    result = scorer.scores(child_id)
    if result is None:
        return {"status": "unscored_no_operative_profile"}
    parent_ids, values = result
    eligible = [
        index for index, parent_id in enumerate(parent_ids)
        if parent_id in documents_by_id
        and not documents_by_id[parent_id]["analysis_scope_reason"]
        and documents_by_id[parent_id]["parsed_date"] < child["parsed_date"]
        and np.isfinite(values[index])
    ]
    if not eligible:
        return {"status": "unscored_no_earlier_profiled_parent"}
    order = sorted(eligible, key=lambda index: (-float(values[index]), int(parent_ids[index])))
    first = order[0]
    second = order[1] if len(order) > 1 else None
    top = float(values[first])
    runner_up = float(values[second]) if second is not None else top
    return {
        "status": "scored",
        "function_parent_id": parent_ids[first],
        "function_score": top,
        "function_margin": top - runner_up,
        "function_runner_up_id": parent_ids[second] if second is not None else "",
        "function_runner_up_score": runner_up,
        "eligible_function_parents": len(order),
    }


def unique_signal_rows(pair_rows: list[dict[str, str]]) -> list[dict]:
    """Collapse reused matched controls while retaining frozen text scores."""
    output: dict[tuple[str, str], dict] = {}
    for pair in pair_rows:
        for group, prefix in (("hc", "hc"), ("control", "control")):
            child_id = pair[f"{prefix}_child_id"]
            key = (group, child_id)
            row = {
                "group": group,
                "child_id": child_id,
                "text_score": float(pair[f"{prefix}_word5_score"]),
                "text_margin": float(pair[f"{prefix}_word5_margin"]),
            }
            if key in output and output[key] != row:
                raise ValueError(f"inconsistent reused signal row for {key}")
            output[key] = row
    rows = sorted(output.values(), key=lambda row: (row["group"], int(row["child_id"])))
    stratified_split(rows)
    return rows


def rate(rows: list[dict], key: str) -> float | str:
    return sum(bool(row[key]) for row in rows) / len(rows) if rows else ""


def cutoff_grid(
    rows: list[dict],
    text_threshold: float,
    max_incremental_control_rate: float,
) -> tuple[list[dict], dict | None]:
    scored = [row for row in rows if row["function_status"] == "scored"]
    development_controls = [
        row for row in scored if row["split"] == "development" and row["group"] == "control"
    ]
    if not development_controls:
        return [], None
    score_values = np.asarray([row["function_score"] for row in development_controls])
    margin_values = np.asarray([row["function_margin"] for row in development_controls])
    function_thresholds = sorted({float(np.quantile(score_values, q)) for q in CONTROL_QUANTILES})
    margin_thresholds = sorted({float(np.quantile(margin_values, q)) for q in MARGIN_QUANTILES})
    grid = []
    for function_threshold in function_thresholds:
        for margin_threshold in margin_thresholds:
            for split in ("development", "holdout"):
                subsets = {
                    group: [row for row in scored if row["split"] == split and row["group"] == group]
                    for group in ("hc", "control")
                }
                record = {
                    "split": split,
                    "text_threshold": text_threshold,
                    "function_threshold": function_threshold,
                    "margin_threshold": margin_threshold,
                }
                for group, items in subsets.items():
                    for row in items:
                        row["_text_positive"] = row["text_score"] > text_threshold
                        row["_function_positive"] = (
                            row["function_score"] >= function_threshold
                            and row["function_margin"] >= margin_threshold
                        )
                        row["_or_positive"] = row["_text_positive"] or row["_function_positive"]
                        row["_function_only"] = row["_function_positive"] and not row["_text_positive"]
                    record[f"{group}_n"] = len(items)
                    record[f"{group}_text_rate"] = rate(items, "_text_positive")
                    record[f"{group}_function_rate"] = rate(items, "_function_positive")
                    record[f"{group}_or_rate"] = rate(items, "_or_positive")
                    record[f"{group}_function_only_rate"] = rate(items, "_function_only")
                    record[f"{group}_function_only_n"] = sum(row["_function_only"] for row in items)
                grid.append(record)
    development = [
        row for row in grid
        if row["split"] == "development"
        and row["control_function_only_rate"] <= max_incremental_control_rate
    ]
    selected = max(
        development,
        key=lambda row: (
            row["hc_function_only_n"],
            -row["control_function_only_n"],
            row["function_threshold"],
            row["margin_threshold"],
        ),
        default=None,
    )
    return grid, selected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text-threshold", type=float, default=TEXT_THRESHOLD)
    parser.add_argument("--max-incremental-control-rate", type=float, default=0.05)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if not 0 <= args.text_threshold <= 1:
        parser.error("--text-threshold must be between zero and one")
    if not 0 <= args.max_incremental_control_rate <= 1:
        parser.error("--max-incremental-control-rate must be between zero and one")

    pair_path = args.output_dir / "hc_matched_signal_pairs.csv"
    with pair_path.open(newline="", encoding="utf-8") as handle:
        pair_rows = list(csv.DictReader(handle))
    rows = unique_signal_rows(pair_rows)
    documents, _ = load_documents()
    by_id = {row["document_id"]: row for row in documents}
    scorer = FunctionSimilarity(FUNCTION_EMBEDDINGS)
    for index, row in enumerate(rows, 1):
        result = best_function_match(row["child_id"], by_id, scorer)
        row["function_status"] = result.pop("status")
        row.update(result)
        if index % 50 == 0:
            print(json.dumps({"scored_children": index, "total": len(rows)}), flush=True)

    signal_path = args.output_dir / "hc_function_signal_children.csv"
    write_csv(signal_path, rows)
    scored = [row for row in rows if row["function_status"] == "scored"]
    summary = []
    for signal in ("function_score", "function_margin"):
        positives = [float(row[signal]) for row in scored if row["group"] == "hc"]
        negatives = [float(row[signal]) for row in scored if row["group"] == "control"]
        summary.append({
            "signal": signal,
            "hc_n": len(positives),
            "control_n": len(negatives),
            "hc_median": float(np.median(positives)) if positives else "",
            "control_median": float(np.median(negatives)) if negatives else "",
            "auc_hc_vs_control": auc(positives, negatives),
            "interpretation": "positive_control_enrichment_not_parent_ground_truth",
        })
    summary_path = args.output_dir / "hc_function_signal_summary.csv"
    write_csv(summary_path, summary)

    grid, selected = cutoff_grid(rows, args.text_threshold, args.max_incremental_control_rate)
    grid_path = args.output_dir / "function_or_cutoff_grid.csv"
    write_csv(grid_path, grid)
    selected_holdout = None
    if selected is not None:
        selected_holdout = next(
            row for row in grid
            if row["split"] == "holdout"
            and row["function_threshold"] == selected["function_threshold"]
            and row["margin_threshold"] == selected["margin_threshold"]
        )
    manifest = {
        "kind": "exploratory_hc_text_or_function_calibration",
        "status": "candidate_cutoff_not_frozen_or_parent_validated",
        "text_threshold": args.text_threshold,
        "function_score": "mean best operative-function embedding match for each child function",
        "function_margin": "best earlier directive score minus second-best earlier directive score",
        "selection_policy": (
            "maximize added HC development cases subject to function-only admission of at most "
            f"{args.max_incremental_control_rate:.1%} of development controls"
        ),
        "unique_hc_children": sum(row["group"] == "hc" for row in rows),
        "unique_control_children": sum(row["group"] == "control" for row in rows),
        "scored_hc_children": sum(row["group"] == "hc" and row["function_status"] == "scored" for row in rows),
        "scored_control_children": sum(row["group"] == "control" and row["function_status"] == "scored" for row in rows),
        "candidate_development_rule": selected,
        "candidate_holdout_result": selected_holdout,
        "caveat": (
            "HC/control discrimination calibrates an HC-like signal, not a parent relationship. "
            "Branch-specific blinded parent review is required before prevalence use."
        ),
        "inputs": {
            str(pair_path.relative_to(Path.cwd())): sha256(pair_path),
            str(FUNCTION_EMBEDDINGS.relative_to(Path.cwd())): sha256(FUNCTION_EMBEDDINGS),
        },
        "outputs": {
            str(signal_path.relative_to(Path.cwd())): sha256(signal_path),
            str(summary_path.relative_to(Path.cwd())): sha256(summary_path),
            str(grid_path.relative_to(Path.cwd())): sha256(grid_path),
        },
    }
    manifest_path = args.output_dir / "function_or_calibration_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "children": len(rows),
        "scored": len(scored),
        "candidate_development_rule": selected,
        "candidate_holdout_result": selected_holdout,
        "manifest": str(manifest_path),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
