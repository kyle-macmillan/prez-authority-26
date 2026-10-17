import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from build_round3_unique_category_review import all_three_units, minority_units, reviewed_units


def result(name, chunks):
    docs = {}
    for doc_id, chunk_number, code in chunks:
        docs.setdefault(doc_id, {"wp_chunks": {}})["wp_chunks"][chunk_number] = {"code": code}
    return {"annotator": name, **docs}


def test_groups_only_sub_directives_where_other_two_annotators_agree():
    chunks = {"EO1": {"1": "first", "2": "second", "3": "third"}}
    results = [
        result("Claire", [("EO1", "1", "1"), ("EO1", "2", "1"), ("EO1", "3", "1")]),
        result("Kyle", [("EO1", "1", "1"), ("EO1", "2", "2"), ("EO1", "3", "2")]),
        result("Thomas", [("EO1", "1", "3"), ("EO1", "2", "3"), ("EO1", "3", "2")]),
    ]

    groups = minority_units(chunks, results)
    assert [group["label"] for group in groups] == ["Claire", "Kyle", "Thomas"]
    assert [unit["chunkNumber"] for unit in groups[0]["units"]] == ["3"]
    assert groups[0]["units"][0]["originalCode"] == "1"
    assert groups[0]["units"][0]["majorityCode"] == "2"
    assert groups[1]["units"] == []
    assert [unit["chunkNumber"] for unit in groups[2]["units"]] == ["1"]


def test_all_different_and_missing_votes_are_excluded():
    chunks = {"EO1": {"1": "all different", "2": "missing"}}
    results = [
        result("Claire", [("EO1", "1", "1"), ("EO1", "2", "1")]),
        result("Kyle", [("EO1", "1", "2"), ("EO1", "2", None)]),
        result("Thomas", [("EO1", "1", "3"), ("EO1", "2", "3")]),
    ]

    assert all(not group["units"] for group in minority_units(chunks, results))


def test_ground_truth_contains_corrected_and_retained_minority_votes():
    chunks = {"EO1": {"1": "corrected", "2": "retained"}}
    results = [
        result("Claire", [("EO1", "1", "1"), ("EO1", "2", "1")]),
        result("Kyle", [("EO1", "1", "3"), ("EO1", "2", "3")]),
        result("Thomas", [("EO1", "1", "1"), ("EO1", "2", "1")]),
    ]
    groups = minority_units(chunks, results)
    reviews = [
        {"annotator": "Claire", "records": []},
        {"annotator": "Kyle", "records": [
            {"round_id": "EO1", "chunk_number": "1", "original_code": "3",
             "majority_code": "1", "reviewed_code": "1"},
            {"round_id": "EO1", "chunk_number": "2", "original_code": "3",
             "majority_code": "1", "reviewed_code": "3"},
        ]},
        {"annotator": "Thomas", "records": []},
    ]

    assert reviewed_units(groups, reviews) == [
        {"docId": "EO1", "chunkNumber": "1", "codes": ["1", "3", "1"],
         "originalCode": "3", "majorityCode": "1", "reviewedBy": "Kyle",
         "minorityIndex": 1, "groundTruthCode": "1"},
        {"docId": "EO1", "chunkNumber": "2", "codes": ["1", "3", "1"],
         "originalCode": "3", "majorityCode": "1", "reviewedBy": "Kyle",
         "minorityIndex": 1, "groundTruthCode": "3"},
    ]


def test_three_way_code_disagreements_are_added_with_provisional_codes():
    chunks = {"EO25": {"2": "three way", "3": "two way"}}
    results = [
        result("Claire", [("EO25", "2", "1"), ("EO25", "3", "1")]),
        result("Kyle", [("EO25", "2", "0"), ("EO25", "3", "1")]),
        result("Thomas", [("EO25", "2", "2"), ("EO25", "3", "3")]),
    ]

    assert all_three_units(chunks, results) == [{
        "docId": "EO25", "chunkNumber": "2", "codes": ["1", "0", "2"],
        "allThree": True, "groundTruthCode": "0",
    }]
