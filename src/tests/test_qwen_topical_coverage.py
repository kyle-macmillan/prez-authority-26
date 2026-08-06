import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from analysis.qwen_topical_coverage import (
    percentile,
    quantile_summary,
    similarity_distribution,
    top_rows_by_variant,
)


def _row(child, parent, full_rank, matched_rank, document, operative):
    return {
        "child_id": child,
        "parent_id": parent,
        "qwen_full_operative_rank": str(full_rank),
        "qwen_full_operative_score": str(0.9 - full_rank / 100),
        "qwen_matched_pairs_rank": str(matched_rank),
        "qwen_matched_pairs_score": str(0.8 - matched_rank / 100),
        "document_embedding_score": str(document),
        "operative_embedding_score": str(operative),
    }


def test_top_rows_are_selected_independently_for_each_qwen_variant():
    rows = [_row("c", "p1", 2, 1, 0.4, 0.5), _row("c", "p2", 1, 2, 0.6, 0.7)]
    selected = top_rows_by_variant(rows)
    assert selected["full"]["c"]["parent_id"] == "p2"
    assert selected["matched"]["c"]["parent_id"] == "p1"


def test_percentiles_and_similarity_distribution():
    assert percentile([0.0, 1.0], 0.5) == 0.5
    summary = quantile_summary([0.2, 0.4, 0.6, 0.8])
    assert summary["50"] == 0.5
    distribution = similarity_distribution([_row("c", "p", 1, 1, 0.6, 0.7)])
    assert distribution["document_embedding_similarity"]["50"] == 0.6
    assert distribution["operative_embedding_similarity"]["50"] == 0.7
