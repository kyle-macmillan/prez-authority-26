#!/usr/bin/env python3
"""Evaluate graded parent retrieval and reranking outputs."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path


GRADE = {"": 0, "not_reviewed": 0, "no": 0, "plausible": 1, "strong": 2}


def dcg(grades: list[int], cutoff: int) -> float:
    return sum((2 ** grade - 1) / math.log2(rank + 1)
               for rank, grade in enumerate(grades[:cutoff], 1))


def metrics_for_rankings(
    rankings: dict[str, list[str]], relevance: dict[tuple[str, str], int],
) -> dict[str, float | int]:
    per_child = []
    for child_id, parents in rankings.items():
        grades = [relevance.get((child_id, parent_id), 0) for parent_id in parents]
        ideal = sorted(
            (grade for (child, _), grade in relevance.items() if child == child_id),
            reverse=True,
        )
        relevant_ranks = [rank for rank, grade in enumerate(grades, 1) if grade > 0]
        per_child.append({
            "ndcg10": dcg(grades, 10) / dcg(ideal, 10) if dcg(ideal, 10) else 0.0,
            "p5": sum(grade > 0 for grade in grades[:5]) / 5,
            "p10": sum(grade > 0 for grade in grades[:10]) / 10,
            "mrr": 1 / relevant_ranks[0] if relevant_ranks else 0.0,
            "success5": float(any(grade > 0 for grade in grades[:5])),
            "success10": float(any(grade > 0 for grade in grades[:10])),
            "success20": float(any(grade > 0 for grade in grades[:20])),
        })
    if not per_child:
        return {"children": 0}
    return {
        "children": len(per_child),
        **{field: sum(row[field] for row in per_child) / len(per_child)
           for field in per_child[0]},
    }


def load_manual(path: Path) -> dict[tuple[str, str], int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        (str(row["child_id"]), str(row["parent_id"])): GRADE[row.get("overall", "")]
        for row in payload["judgments"]
    }


def load_rankings(path: Path) -> dict[str, dict[str, list[str]]]:
    by_method_child: dict[str, dict[str, list[tuple[int, str]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            by_method_child[row["reranker"]][row["child_id"]].append(
                (int(row["rank"]), row["parent_id"])
            )
    return {
        method: {
            child: [parent for _, parent in sorted(rows)]
            for child, rows in children.items()
        }
        for method, children in by_method_child.items()
    }


def explicit_edge_relevance(path: Path) -> dict[tuple[str, str], int]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {
            (row["child_id"], row["parent_id"]): 2 for row in csv.DictReader(handle)
        }


def subset(
    rankings: dict[str, list[str]], child_ids: set[str],
) -> dict[str, list[str]]:
    # Missing rankings are retrieval failures and must contribute zeros rather
    # than disappearing from a method's denominator.
    return {child: rankings.get(child, []) for child in sorted(child_ids)}


def evaluate(
    rankings: dict[str, dict[str, list[str]]], relevance: dict[tuple[str, str], int],
    genre_ids: set[str] | None = None,
) -> dict:
    result = {}
    judged_children = {child for child, _ in relevance}
    for method, method_rankings in rankings.items():
        result[method] = {
            "all": metrics_for_rankings(subset(method_rankings, judged_children), relevance)
        }
        if genre_ids is not None:
            result[method]["trade_proclamation"] = metrics_for_rankings(
                subset(method_rankings, judged_children & genre_ids), relevance
            )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rankings", type=Path, required=True)
    parser.add_argument("--judgments", type=Path)
    parser.add_argument("--automatic-edges", type=Path)
    parser.add_argument("--pilot-manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.judgments and not args.automatic_edges:
        raise ValueError("provide --judgments or --automatic-edges")
    relevance = (
        load_manual(args.judgments) if args.judgments
        else explicit_edge_relevance(args.automatic_edges)
    )
    trade_ids = None
    if args.pilot_manifest:
        manifest = json.loads(args.pilot_manifest.read_text(encoding="utf-8"))
        rows = manifest.get("development", []) + manifest.get("evaluation", [])
        trade_ids = {
            str(row["document_id"]) for row in rows
            if row.get("known_parent_genre") == "trade_proclamation"
        }
    result = {
        "relevance_source": "manual_graded" if args.judgments else "explicit_edges_hidden_benchmark",
        "relevant_threshold": "plausible or strong",
        "metrics": evaluate(load_rankings(args.rankings), relevance, trade_ids),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
