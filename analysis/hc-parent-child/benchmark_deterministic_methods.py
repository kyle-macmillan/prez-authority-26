#!/usr/bin/env python3
"""Benchmark deterministic parent rankings on masked known explicit edges."""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from build import (
    AUTOMATIC_EDGES,
    DOCUMENT_EMBEDDINGS,
    FUNCTION_EMBEDDINGS,
    TOKEN_RE,
    DocumentSimilarity,
    FunctionSimilarity,
    documents_by_id,
    load_documents,
    midrank_percentiles,
    read_csv,
    semantic_array,
    stable_key,
    write_csv,
)


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "outputs"
REFERENCE_RE = re.compile(
    r"\b(?:Executive\s+Order|Presidential\s+Proclamation|Proclamation|Memorandum)"
    r"(?:\s+No\.?|\s+Number)?\s+\d[\d-]*\b|"
    r"\b(?:Executive\s+Orders?|Proclamations?)\s+\d[\d,\s-]*(?=\b|$)",
    re.I,
)
HEADING_RE = re.compile(
    r"\b(?:Sec\.|Section)\s+\d+[A-Za-z]?(?:\([a-z0-9]+\))?\.?\s*"
    r"([^.;]{0,100})",
    re.I,
)


def masked(text: str) -> str:
    return REFERENCE_RE.sub("[DIRECTIVE_REFERENCE]", text)


def grams(text: str, n: int) -> set[tuple[str, ...]]:
    tokens = [token.casefold() for token in TOKEN_RE.findall(text)]
    return {tuple(tokens[i:i+n]) for i in range(max(0, len(tokens) - n + 1))}


def lexical_arrays(documents: list[dict], child_ids: list[str], n: int) -> dict[str, np.ndarray]:
    by_id = documents_by_id(documents)
    child_sets = {did: grams(masked(by_id[did]["primary_text"]), n) for did in child_ids}
    wanted: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for did, items in child_sets.items():
        for item in items:
            wanted[item].append(did)
    df = Counter()
    document_sets = []
    for document in documents:
        items = grams(masked(document["primary_text"]), n)
        document_sets.append(items)
        for item in items:
            if item in wanted:
                df[item] += 1
    total = len(documents)
    weights = {item: math.log((total + 1) / (count + 1)) + 1 for item, count in df.items()}
    denominators = {did: sum(weights[item] for item in items) for did, items in child_sets.items()}
    arrays = {did: np.zeros(total, dtype=np.float32) for did in child_ids}
    for position, items in enumerate(document_sets):
        totals = defaultdict(float)
        for item in items:
            if item not in wanted:
                continue
            for did in wanted[item]:
                totals[did] += weights[item]
        for did, value in totals.items():
            if denominators[did]:
                arrays[did][position] = value / denominators[did]
    return arrays


def heading_sets(documents: list[dict]) -> list[set[str]]:
    return [{" ".join(TOKEN_RE.findall(match.casefold())[:8]) for match in HEADING_RE.findall(row["primary_text"])} for row in documents]


def main() -> None:
    documents, _ = load_documents()
    by_id = documents_by_id(documents)
    position = {row["document_id"]: i for i, row in enumerate(documents)}
    targets: dict[str, set[str]] = defaultdict(set)
    relations: dict[str, set[str]] = defaultdict(set)
    for edge in read_csv(AUTOMATIC_EDGES):
        child, parent = edge["child_id"], edge["parent_id"]
        if child in by_id and parent in by_id and by_id[parent]["parsed_date"] < by_id[child]["parsed_date"]:
            targets[child].add(parent); relations[child].add(edge["relation"])

    function, document = FunctionSimilarity(FUNCTION_EMBEDDINGS), DocumentSimilarity(DOCUMENT_EMBEDDINGS)
    candidates = []
    for child_id in targets:
        scorer = function if child_id in function.child_indices else document
        semantic = semantic_array(child_id, documents, scorer)
        if semantic is None or not any(np.isfinite(semantic[position[parent]]) for parent in targets[child_id]):
            continue
        candidates.append(child_id)
    candidates.sort(key=lambda did: stable_key(f"explicit-method-benchmark:{did}"))
    child_ids = candidates[:200]
    split_by_child = {
        child_id: "development" if index < 100 else "holdout"
        for index, child_id in enumerate(child_ids)
    }
    lex5 = lexical_arrays(documents, child_ids, 5)
    lex10 = lexical_arrays(documents, child_ids, 10)
    headings = heading_sets(documents)
    dates = np.asarray([row["parsed_date"].timestamp() for row in documents])
    ids = np.asarray([row["document_id"] for row in documents])
    scope = np.asarray([not row["analysis_scope_reason"] for row in documents])
    case_rows, ranks_by_method, confidence_rows = [], defaultdict(list), []

    for child_id in child_ids:
        child = by_id[child_id]
        scorer = function if child_id in function.child_indices else document
        stratum = "operative_profile" if scorer is function else "document_semantic"
        semantic = semantic_array(child_id, documents, scorer)
        eligible = (dates < child["parsed_date"].timestamp()) & np.isfinite(semantic) & scope
        positions = np.flatnonzero(eligible)
        child_heading = headings[position[child_id]]
        structure = np.asarray([
            len(child_heading & headings[int(pos)]) / len(child_heading | headings[int(pos)])
            if child_heading | headings[int(pos)] else 0.0
            for pos in positions
        ])
        raw = {
            "word_5_shingle": lex5[child_id][eligible],
            "word_10_shingle": lex10[child_id][eligible],
            "semantic": semantic[eligible],
            "section_heading": structure,
        }
        pct = {name: midrank_percentiles(values) for name, values in raw.items()}
        scores = {
            **raw,
            "hybrid_5_semantic": 0.5 * pct["word_5_shingle"] + 0.5 * pct["semantic"],
            "hybrid_10_semantic": 0.5 * pct["word_10_shingle"] + 0.5 * pct["semantic"],
            "hybrid_10_semantic_structure": (
                0.45 * pct["word_10_shingle"] + 0.45 * pct["semantic"]
                + 0.10 * pct["section_heading"]
            ),
        }
        gold = targets[child_id]
        method_details = {}
        for method, values in scores.items():
            order = np.lexsort((ids[positions].astype(int), -values))
            rank = min(
                (rank for rank, local in enumerate(order, 1) if ids[positions[int(local)]] in gold),
                default=len(order) + 1,
            )
            winner = documents[int(positions[int(order[0])])]
            second_score = float(values[int(order[1])]) if len(order) > 1 else float(values[int(order[0])])
            method_details[method] = {
                "selected_parent_id": winner["document_id"],
                "selected_is_known": winner["document_id"] in gold,
                "top_score": float(values[int(order[0])]),
                "top_margin": float(values[int(order[0])]) - second_score,
            }
            ranks_by_method[method].append(rank)
            case_rows.append({
                "child_id": child_id, "child_title": child["title"], "child_date": child["date"],
                "benchmark_split": split_by_child[child_id],
                "relations": "|".join(sorted(relations[child_id])), "score_stratum": stratum,
                "method": method, "known_parent_rank": rank,
                "known_parent_ids": "|".join(sorted(gold, key=int)),
                "selected_parent_id": winner["document_id"], "selected_parent_title": winner["title"],
                "selected_parent_is_known": winner["document_id"] in gold,
                "eligible_parent_count": len(order),
            })
        word5_parent = method_details["word_5_shingle"]["selected_parent_id"]
        confidence_rows.append({
            "child_id": child_id, "child_title": child["title"],
            "benchmark_split": split_by_child[child_id], "score_stratum": stratum,
            "word5_selected_parent_id": word5_parent,
            "word5_selected_is_known": method_details["word_5_shingle"]["selected_is_known"],
            "word5_score": method_details["word_5_shingle"]["top_score"],
            "word5_margin": method_details["word_5_shingle"]["top_margin"],
            "method_consensus_count": sum(
                method_details[method]["selected_parent_id"] == word5_parent
                for method in ("word_5_shingle", "hybrid_10_semantic", "hybrid_5_semantic")
            ),
            "hybrid10_agrees": (
                method_details["hybrid_10_semantic"]["selected_parent_id"] == word5_parent
            ),
            "hybrid5_agrees": (
                method_details["hybrid_5_semantic"]["selected_parent_id"] == word5_parent
            ),
            "known_parent_ids": "|".join(sorted(gold, key=int)),
        })

    summary = []
    for method, ranks in sorted(ranks_by_method.items()):
        summary.append({
            "method": method, "benchmark_children": len(ranks),
            "recall_at_1": sum(rank <= 1 for rank in ranks) / len(ranks),
            "recall_at_5": sum(rank <= 5 for rank in ranks) / len(ranks),
            "recall_at_10": sum(rank <= 10 for rank in ranks) / len(ranks),
            "mean_reciprocal_rank": sum(1 / rank for rank in ranks) / len(ranks),
            "benchmark_scope": "known_explicit_edges_with_directive_identifiers_masked",
            "interpretation": "method_diagnostic_not_implicit_parent_accuracy",
        })
    cases_path = OUTPUT / "deterministic_method_benchmark_cases.csv"
    summary_path = OUTPUT / "deterministic_method_benchmark_summary.csv"
    confidence_path = OUTPUT / "deterministic_confidence_benchmark.csv"
    write_csv(cases_path, case_rows); write_csv(summary_path, summary)
    write_csv(confidence_path, confidence_rows)
    print(json.dumps({"children": len(child_ids), "methods": len(summary), "summary": str(summary_path)}, sort_keys=True))


if __name__ == "__main__":
    main()
