from collections import Counter

import numpy as np
import pytest

from build_function_candidate_pool import (
    bm25_scores,
    indexed_bm25_scores,
    indexed_reuse_scores,
    reuse_score,
)


def test_indexed_lexical_scores_match_reference_implementations():
    corpus = {
        "1": "a b a c d e f g h i j k".split(),
        "2": "a z z c d e f g h i j k".split(),
        "3": "q r s".split(),
    }
    query = "a c d e f g h i j k a".split()
    eligible = list(corpus)
    postings = {}
    for document_id, tokens in corpus.items():
        for token, frequency in Counter(tokens).items():
            postings.setdefault(token, {})[document_id] = frequency
    expected_bm25 = bm25_scores(query, corpus)
    actual_bm25 = indexed_bm25_scores(
        query, eligible, {key: len(value) for key, value in corpus.items()}, postings
    )
    assert actual_bm25 == pytest.approx(expected_bm25)

    shingle_postings = {}
    for document_id, tokens in corpus.items():
        for gram in {
            tuple(tokens[index:index + 10])
            for index in range(len(tokens) - 10 + 1)
        }:
            shingle_postings.setdefault(gram, []).append(document_id)
    actual_reuse = indexed_reuse_scores(query, eligible, shingle_postings)
    assert actual_reuse == {
        document_id: float(reuse_score(query, tokens))
        for document_id, tokens in corpus.items()
    }


def test_grouped_vector_reduction_matches_per_document_scoring():
    child = np.asarray([[1.0, 0.0], [0.5, 0.5]])
    parents = np.asarray([[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]])
    starts = np.asarray([0, 2])
    grouped = np.maximum.reduceat(child @ parents.T, starts, axis=1).mean(axis=0)
    expected = np.asarray([
        np.max(child @ parents[:2].T, axis=1).mean(),
        np.max(child @ parents[2:].T, axis=1).mean(),
    ])
    np.testing.assert_allclose(grouped, expected)
