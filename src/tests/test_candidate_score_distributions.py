import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[1]))

from analysis.candidate_score_distributions import (
    _histogram_specs, build_plot_html, extract_candidate_scores, summarize_scores,
    write_analysis,
)


def _ranked_row(child: str, parent: str, rank: int, operative: str, trigram: str, reuse: str):
    return {
        "child_id": child,
        "parent_id": parent,
        "document_type": "letter",
        "rrf_rank": str(rank),
        "operative_embedding_score": operative,
        "segment_word_trigram_tfidf_score": trigram,
        "segment_text_reuse_words": reuse,
    }


def test_extracts_only_candidate_1_and_2_and_preserves_missing_and_zero():
    rows = [
        _ranked_row("c1", "p1", 1, "0.9", "0.4", "0"),
        _ranked_row("c1", "p2", 2, "0.8", "", "12"),
        _ranked_row("c1", "p3", 3, "0.7", "0.2", "8"),
        _ranked_row("c2", "p4", 1, "0.6", "0.1", "0"),
    ]
    extracted = extract_candidate_scores(rows)
    assert [(row["child_id"], row["candidate_rank"]) for row in extracted] == [
        ("c1", 1), ("c2", 1), ("c1", 2),
    ]
    assert extracted[0]["text_reuse_words"] == 0.0
    assert extracted[2]["trigram_tfidf_similarity"] is None

    summaries = summarize_scores(extracted, total_children=3)
    candidate_1_reuse = next(
        row for row in summaries
        if row["candidate_rank"] == 1 and row["score_channel"] == "text_reuse"
    )
    assert candidate_1_reuse["candidate_count"] == 2
    assert candidate_1_reuse["children_without_candidate"] == 1
    assert candidate_1_reuse["zero_count"] == 2
    assert candidate_1_reuse["zero_share"] == 1.0

    candidate_2_trigram = next(
        row for row in summaries
        if row["candidate_rank"] == 2 and row["score_channel"] == "trigram_tfidf"
    )
    assert candidate_2_trigram["candidate_count"] == 1
    assert candidate_2_trigram["score_count"] == 0
    assert candidate_2_trigram["score_missing_count"] == 1


def test_summary_statistics_and_plot_are_deterministic():
    extracted = extract_candidate_scores([
        _ranked_row("c1", "p1", 1, "0.2", "0.1", "0"),
        _ranked_row("c2", "p2", 1, "0.4", "0.3", "10"),
    ])
    operative = next(
        row for row in summarize_scores(extracted, total_children=2)
        if row["candidate_rank"] == 1 and row["score_channel"] == "operative_embedding"
    )
    assert np.isclose(operative["mean"], 0.3)
    assert np.isclose(operative["std_dev"], np.sqrt(0.02))
    assert np.isclose(operative["p50"], 0.3)
    plot = build_plot_html(extracted)
    assert plot.count('"title":') == 6
    assert "Thirty equal-width bins" in plot
    assert "How to read these metrics" in plot
    assert "Operative embedding similarity" in plot
    assert "Word-trigram TF-IDF similarity" in plot
    assert "Text reuse" in plot
    assert "Why this report starts with 16,397 rather than 20,232 directives" in plot
    assert "Why Candidate 2 has n = 11,716" in plot


def test_text_reuse_histogram_excludes_values_above_combined_p99():
    extracted = [
        {
            "candidate_rank": 1,
            "operative_embedding_similarity": 0.5,
            "trigram_tfidf_similarity": 0.5,
            "text_reuse_words": float(value),
        }
        for value in [*range(100), 1000]
    ]

    reuse = next(
        spec for spec in _histogram_specs(extracted)
        if spec["title"] == "Candidate 1: text reuse"
    )
    assert reuse["maximum"] == 99.0
    assert reuse["above_display_range"] == 1
    assert np.isclose(sum(reuse["shares"]), 100 / 101)


def test_write_analysis_creates_scores_summary_and_plot(tmp_path):
    ranked = tmp_path / "ranked.csv"
    children = tmp_path / "children.csv"
    output = tmp_path / "output"
    rows = [_ranked_row("c1", "p1", 1, "0.9", "0.4", "0")]
    with ranked.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with children.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["document_id"])
        writer.writeheader()
        writer.writerows([{"document_id": "c1"}, {"document_id": "c2"}])

    paths = write_analysis(ranked, children, output)
    assert set(paths) == {"scores", "summary", "plots"}
    assert all(path.is_file() and path.stat().st_size > 0 for path in paths.values())
