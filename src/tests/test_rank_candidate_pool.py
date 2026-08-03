import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[1]))

from rank_candidate_pool import (
    FUSION_CHANNELS, dense_ranks, matching_phrase_pairs, reciprocal_rank_scores,
    reused_word_count, segment_reuse_score, top_pair_average,
)


def test_top_three_pair_average():
    child = np.asarray([[1, 0], [0, 1]], dtype=np.float32)
    parent = np.asarray([[1, 0], [0.6, 0.8]], dtype=np.float32)
    score, pairs = top_pair_average(child, parent)
    assert len(pairs) == 3
    assert np.isclose(score, (1.0 + 0.8 + 0.6) / 3)


def test_reuse_counts_only_blocks_of_ten_or_more_words():
    common = "one two three four five six seven eight nine ten".split()
    assert reused_word_count(["start", *common], [*common, "end"]) == 10
    assert reused_word_count(common[:9], common[:9]) == 0


def test_dense_ranks_preserve_ties():
    assert dense_ranks({"a": 1.0, "b": 1.0, "c": 0.0}) == {
        "a": 1, "b": 1, "c": 2,
    }


def test_rrf_uses_three_similarity_channels_and_excludes_wp_phrase():
    ranks = {
        "operative": {"a": 1, "b": 2},
        "ngram": {"a": 2, "b": 1},
        "text_reuse": {"a": 1, "b": 2},
    }
    assert FUSION_CHANNELS == tuple(ranks)
    scores = reciprocal_rank_scores(["a", "b"], ranks, k=20)
    assert np.isclose(scores["a"], 2 / 21 + 1 / 22)
    assert np.isclose(scores["b"], 1 / 21 + 2 / 22)

    # W&P can still change diagnostically without changing the supplied fusion ranks.
    for diagnostic_wp_ranks in ({"a": 1, "b": 2}, {"a": 2, "b": 1}):
        assert set(diagnostic_wp_ranks) == set(scores)
        assert reciprocal_rank_scores(["a", "b"], ranks, k=20) == scores


def test_matching_phrase_pairs_detect_exact_normalized_wp_phrase():
    child = [{"text": "I hereby order the agency to act."}]
    parent = [
        {"text": "I HEREBY ORDER a different agency to act."},
        {"text": "The Secretary shall develop a report."},
    ]
    assert matching_phrase_pairs(child, parent) == [(0, 0, ["i hereby"])]


def test_segment_reuse_does_not_cross_segment_boundaries():
    first = "one two three four five"; second = "six seven eight nine ten"
    child = [{"text": first}, {"text": second}]
    parent = [{"text": first + " " + second}]
    score, pairs = segment_reuse_score(child, parent)
    assert score == 0.0
    assert all(pair[2] == 0.0 for pair in pairs)


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"  PASS  {test.__name__}")
    print(f"\n{len(tests)} passed")
