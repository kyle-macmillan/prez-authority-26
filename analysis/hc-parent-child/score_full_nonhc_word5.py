#!/usr/bin/env python3
"""Compute exact best-earlier 5-word reuse for all eligible non-HC directives."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from build import (
    AUTOMATIC_EDGES,
    DEFAULT_OUTPUT,
    assign_families,
    build_lexical_scores,
    explicit_parent_child_ids,
    load_documents,
    load_profiles,
    write_csv,
)


HC_MEDIAN_WORD5 = 0.2206716686487198


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=400)
    parser.add_argument("--threshold", type=float, default=HC_MEDIAN_WORD5)
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")

    documents, _ = load_documents()
    assign_families(documents, load_profiles())
    explicit = explicit_parent_child_ids(
        list(csv.DictReader(AUTOMATIC_EDGES.open(newline="", encoding="utf-8")))
    )
    target_ids = [
        row["document_id"] for row in documents
        if not row["analysis_scope_reason"] and not row["families"]
        and row["document_id"] not in explicit
    ]
    target_ids.sort(key=int)
    dates = np.asarray([row["parsed_date"].timestamp() for row in documents])
    ids = np.asarray([row["document_id"] for row in documents])
    parent_scope = np.asarray([not row["analysis_scope_reason"] for row in documents])
    by_id = {row["document_id"]: row for row in documents}
    results = []
    for start in range(0, len(target_ids), args.batch_size):
        batch = target_ids[start : start + args.batch_size]
        scores = build_lexical_scores(documents, batch, "primary_text", size=5)
        for child_id in batch:
            child = by_id[child_id]
            eligible = (dates < child["parsed_date"].timestamp()) & parent_scope
            positions = np.flatnonzero(eligible)
            if not len(positions):
                results.append({
                    "child_id": child_id, "child_date": child["date"],
                    "child_title": child["title"], "parent_id": "", "parent_date": "",
                    "parent_title": "", "word5_reuse_score": "", "above_hc_median": "",
                    "status": "no_strictly_earlier_scoped_parent",
                })
                continue
            values = scores[child_id][eligible]
            order = np.lexsort((ids[positions].astype(int), -values))
            parent = by_id[str(ids[positions[int(order[0])]])]
            top = float(values[int(order[0])])
            results.append({
                "child_id": child_id, "child_date": child["date"],
                "child_title": child["title"], "parent_id": parent["document_id"],
                "parent_date": parent["date"], "parent_title": parent["title"],
                "word5_reuse_score": top, "above_hc_median": top > args.threshold,
                "status": "scored",
            })
        print(json.dumps({"completed": min(start + len(batch), len(target_ids)), "total": len(target_ids)}, sort_keys=True), flush=True)

    output_path = DEFAULT_OUTPUT / "full_nonhc_word5_reuse.csv"
    summary_path = DEFAULT_OUTPUT / "full_nonhc_word5_reuse_summary.csv"
    write_csv(output_path, results)
    scored = [row for row in results if row["status"] == "scored"]
    above = [row for row in scored if row["above_hc_median"] is True]
    write_csv(summary_path, [{
        "population": "scoped_no_explicit_link_nonhc_directives",
        "threshold_name": "hc_pilot_median_best_earlier_word5_reuse",
        "threshold": args.threshold,
        "eligible_nonhc_directives": len(target_ids),
        "scored": len(scored),
        "unscored": len(target_ids) - len(scored),
        "above_threshold": len(above),
        "proportion_above_threshold": len(above) / len(scored) if scored else "",
        "interpretation": (
            "Exact descriptive full-corpus reuse count. Exceeding the HC median is "
            "not a validated path-dependency classification."
        ),
    }])
    print(json.dumps({"output": str(output_path), "above_threshold": len(above)}, sort_keys=True))


if __name__ == "__main__":
    main()
