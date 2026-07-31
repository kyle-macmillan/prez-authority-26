"""Tests for the document-embedding candidate gate."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from generate_candidate_pool import top_candidates


def test_same_type_strictly_earlier_and_up_to_limit():
    documents = [
        {"document_id": "a", "document_type": "letter", "date": "January 1, 2020"},
        {"document_id": "b", "document_type": "letter", "date": "January 2, 2020"},
        {"document_id": "c", "document_type": "letter", "date": "January 2, 2020"},
        {"document_id": "d", "document_type": "memorandum", "date": "January 1, 2020"},
    ]
    embeddings = np.asarray([[1, 0], [0.8, 0.2], [1, 0], [1, 0]], dtype=np.float32)
    rows = top_candidates(
        documents, {"c"}, ["a", "b", "c", "d"], embeddings, embeddings, limit=25
    )
    assert [(row["parent_id"], row["document_embedding_rank"]) for row in rows] == [
        ("a", 1)
    ]


def test_ranks_by_cosine_score_and_limits_pool():
    documents = [
        {"document_id": "a", "document_type": "letter", "date": "January 1, 2020"},
        {"document_id": "b", "document_type": "letter", "date": "January 2, 2020"},
        {"document_id": "c", "document_type": "letter", "date": "January 3, 2020"},
    ]
    query = np.asarray([[1, 0], [1, 0], [1, 0]], dtype=np.float32)
    candidates = np.asarray([[0.5, 0], [0.9, 0], [1, 0]], dtype=np.float32)
    rows = top_candidates(documents, {"c"}, ["a", "b", "c"], query, candidates, limit=1)
    assert len(rows) == 1
    assert rows[0]["parent_id"] == "b"


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"  PASS  {test.__name__}")
    print(f"\n{len(tests)} passed")
