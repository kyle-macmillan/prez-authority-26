import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from analysis.ieepa_candidate_similarity import is_ieepa, score_band, stratified_examples


def test_ieepa_matching_requires_acronym_boundary_or_full_name():
    assert is_ieepa("pursuant to IEEPA, sanctions are imposed")
    assert is_ieepa("the international emergency economic powers act applies")
    assert not is_ieepa("the token XIEEPAX is unrelated")


def test_score_band_boundaries_and_missing_are_distinct():
    assert score_band("0.9") == "at_least_0.9"
    assert score_band("0.8") == "0.8_to_under_0.9"
    assert score_band("0.7") == "0.7_to_under_0.8"
    assert score_band("0.69999") == "under_0.7"
    assert score_band("") == "missing"


def test_examples_are_deterministic_stratified_and_limited():
    rows = [
        {"document_id": str(i), "document_type": kind, "keep": True}
        for kind in ("letter", "executive_order") for i in range(5)
    ]
    first = stratified_examples(rows, lambda row: row["keep"])
    second = stratified_examples(list(reversed(rows)), lambda row: row["keep"])
    assert [row["document_id"] for row in first] == [row["document_id"] for row in second]
    assert len(first) == 4
    assert sum(row["document_type"] == "letter" for row in first) == 2
    assert sum(row["document_type"] == "executive_order" for row in first) == 2


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"  PASS  {test.__name__}")
    print(f"\n{len(tests)} passed")
