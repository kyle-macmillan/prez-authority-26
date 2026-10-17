import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from build_combined_subdirective_labels import build_dataset


def annotator(name, codes):
    return {"annotator": name, "EO1": {"wp_chunks": {
        chunk: {"code": code} for chunk, code in codes.items()
    }}}


def test_combines_finalized_reviewed_and_unanimous_codes():
    round2 = {"subdirective_records": [{
        "global_dev_id": "10", "round_id": "M1", "chunk_number": "1",
        "text": "Round 2 text", "labels": {"code": "2"},
    }]}
    chunks = {"EO1": {"1": "agreed", "2": "reviewed", "3": "incomplete"}}
    results = [
        annotator("Claire", {"1": "1", "2": "0", "3": "3"}),
        annotator("Kyle", {"1": "1", "2": "1", "3": "3"}),
        annotator("Thomas", {"1": "1", "2": "2", "3": None}),
    ]
    review = {"records": [{"round_id": "EO1", "chunk_number": "2",
                           "ground_truth_code": "3"}]}

    data = build_dataset(round2, chunks, results, {"EO1": 20}, review)

    assert data["counts"] == {"round_2_finalized": 1, "round_3_reviewed": 1,
                              "round_3_unanimous": 1}
    assert [(row["global_dev_id"], row["chunk_number"], row["labels"]["code"])
            for row in data["records"]] == [("10", "1", "2"), ("20", "1", "1"),
                                            ("20", "2", "3")]
    assert [(row["round_id"], row["chunk_number"])
            for row in data["excluded_round_3"]] == [("EO1", "3")]


def test_disagreement_without_ground_truth_is_rejected():
    chunks = {"EO1": {"1": "review needed"}}
    results = [annotator("Claire", {"1": "0"}),
               annotator("Kyle", {"1": "1"}),
               annotator("Thomas", {"1": "1"})]

    try:
        build_dataset({"subdirective_records": []}, chunks, results, {"EO1": 20},
                      {"records": []})
    except ValueError as error:
        assert "Missing Round 3 review record" in str(error)
    else:
        raise AssertionError("Missing disagreement label was accepted")
