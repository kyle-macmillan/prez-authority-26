import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parents[1]))
from rerank_qwen_candidates import bidirectional_matrix_mean, ordinal_ranks


def test_bidirectional_chunk_aggregation():
    matrix = np.asarray([[.9, .2], [.3, .8], [.1, .4]])
    assert np.isclose(bidirectional_matrix_mean(matrix), ((.9 + .8 + .4) / 3 + (.9 + .8) / 2) / 2)


def test_reranker_ties_preserve_rrf_then_id():
    assert ordinal_ranks({"b": .5, "a": .5, "c": .4}, {"a": 2, "b": 1, "c": 3}) == {"b": 1, "a": 2, "c": 3}


if __name__ == "__main__":
    for test in (test_bidirectional_chunk_aggregation, test_reranker_ties_preserve_rrf_then_id):
        test(); print("PASS", test.__name__)
