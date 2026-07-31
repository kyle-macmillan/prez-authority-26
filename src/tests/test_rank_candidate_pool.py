import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[1]))

from rank_candidate_pool import bm25_scores, reused_word_count, top_pair_average


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


def test_bm25_is_case_sensitive():
    upper, lower = bm25_scores(["Agency"], [["Agency"], ["agency"]])
    assert upper > lower


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"  PASS  {test.__name__}")
    print(f"\n{len(tests)} passed")
