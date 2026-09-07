#!/usr/bin/env python3
"""Export high-ranked alternative parents for reviewed nonparent children."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from build import (
    DOCUMENT_EMBEDDINGS,
    FUNCTION_EMBEDDINGS,
    DocumentSimilarity,
    FunctionSimilarity,
    assign_families,
    build_lexical_scores,
    documents_by_id,
    load_documents,
    load_profiles,
    midrank_percentiles,
    read_csv,
    semantic_array,
    write_csv,
)


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "outputs"


def main() -> None:
    decisions = {row["pair_id"]: row for row in read_csv(OUTPUT / "parent_pair_decisions.csv")}
    keys = read_csv(OUTPUT / "parent_pair_review_key.csv")
    child_ids = [row["child_id"] for row in keys if decisions[row["pair_id"]]["decision"] == "not_parent"]
    documents, _ = load_documents()
    assign_families(documents, load_profiles())
    by_id = documents_by_id(documents)
    function, document = FunctionSimilarity(FUNCTION_EMBEDDINGS), DocumentSimilarity(DOCUMENT_EMBEDDINGS)
    lexical = build_lexical_scores(documents, child_ids, "primary_text")
    dates = np.asarray([row["parsed_date"].timestamp() for row in documents])
    ids = np.asarray([row["document_id"] for row in documents])
    parent_scope = np.asarray([not row["analysis_scope_reason"] for row in documents])
    output = []
    for child_id in child_ids:
        child = by_id[child_id]
        scorer = function if child_id in function.child_indices else document
        stratum = "operative_profile" if scorer is function else "document_semantic"
        semantic = semantic_array(child_id, documents, scorer)
        eligible = (dates < child["parsed_date"].timestamp()) & np.isfinite(semantic) & parent_scope
        positions = np.flatnonzero(eligible)
        lexical_pct = midrank_percentiles(lexical[child_id][eligible])
        semantic_pct = midrank_percentiles(semantic[eligible])
        combined = 0.5 * lexical_pct + 0.5 * semantic_pct
        order = np.lexsort((ids[positions].astype(int), -combined))
        child_families = set(child["families"])
        emitted = set()
        selections = [
            ("top_overall", list(order[:15])),
            ("top_shared_family", [
                int(local) for local in order
                if child_families & set(documents[int(positions[int(local)])]["families"])
            ][:10]),
        ]
        overall_rank = {int(local): rank for rank, local in enumerate(order, 1)}
        for selection_type, locals_ in selections:
            for selection_rank, local in enumerate(locals_, 1):
                position = int(positions[local]); parent = documents[position]
                identity = (selection_type, parent["document_id"])
                if identity in emitted:
                    continue
                emitted.add(identity)
                output.append({
                    "child_id": child_id, "child_title": child["title"],
                    "child_date": child["date"], "child_families": "|".join(sorted(child_families)),
                    "score_stratum": stratum, "selection_type": selection_type,
                    "selection_rank": selection_rank, "overall_rank": overall_rank[local],
                    "candidate_parent_id": parent["document_id"],
                    "candidate_parent_title": parent["title"], "candidate_parent_date": parent["date"],
                    "candidate_parent_type": parent["document_type"],
                    "candidate_parent_families": "|".join(sorted(parent["families"])),
                    "shared_families": "|".join(sorted(child_families & set(parent["families"]))),
                    "combined_score": float(combined[local]),
                    "lexical_score": float(lexical[child_id][position]),
                    "semantic_score": float(semantic[position]),
                    "candidate_parent_url": parent["url"],
                })
    path = OUTPUT / "nonparent_alternative_rankings.csv"
    write_csv(path, output)
    print(json.dumps({"children": len(child_ids), "candidate_rows": len(output), "output": str(path)}, sort_keys=True))


if __name__ == "__main__":
    main()
