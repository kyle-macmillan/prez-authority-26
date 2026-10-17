import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from build_round4_retained_minority_review import retained_units


def test_only_reviewers_who_kept_their_minority_code_are_selected():
    chunks = {"EO1": {"1": "retained", "2": "changed to majority", "3": "third code"}}
    results = [
        {"annotator": "Claire", "EO1": {"wp_chunks": {str(i): {"code": "1"} for i in (1, 2, 3)}}},
        {"annotator": "KyleM", "EO1": {"wp_chunks": {str(i): {"code": "2"} for i in (1, 2, 3)}}},
        {"annotator": "Thomas Weil", "EO1": {"wp_chunks": {str(i): {"code": "1"} for i in (1, 2, 3)}}},
    ]
    reviews = [
        {"annotator": "Claire", "schema": "round4-minority-subdirective-review", "records": []},
        {"annotator": "KyleM", "schema": "round4-minority-subdirective-review", "records": [
            {"round_id": "EO1", "chunk_number": str(i), "original_code": "2",
             "majority_code": "1", "reviewed_code": code}
            for i, code in ((1, "2"), (2, "1"), (3, "3"))
        ]},
        {"annotator": "Thomas Weil", "schema": "round4-minority-subdirective-review", "records": []},
    ]

    assert [(unit["docId"], unit["chunkNumber"]) for unit in retained_units(chunks, results, reviews)] == [("EO1", "1")]
    reviews[1]["records"].pop()
    with pytest.raises(ValueError, match="Incomplete"):
        retained_units(chunks, results, reviews)
