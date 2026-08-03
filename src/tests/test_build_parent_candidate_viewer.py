import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from build_parent_candidate_viewer import build_payload, select_sample


def test_sample_is_balanced_deterministic_and_excludes_holdout():
    rows = [
        {"document_id": str(i), "document_type": kind}
        for kind_index, kind in enumerate(
            ("executive_order", "memorandum", "proclamation", "letter")
        )
        for i in range(kind_index * 10, kind_index * 10 + 8)
    ]
    first = select_sample(rows, {"0", "10", "20", "30"}, seed=7, per_type=3)
    second = select_sample(rows, {"0", "10", "20", "30"}, seed=7, per_type=3)
    assert first == second
    assert len(first) == 12
    assert not ({row["document_id"] for row in first} & {"0", "10", "20", "30"})


def test_payload_blinds_rank_and_preserves_alignment_ids():
    sampled = [{"document_id": "2", "document_type": "letter"}]
    documents = [
        {"document_id": value, "document_type": "letter", "identifier": "", "title": value,
         "date": "date", "url": "url", "cleaned_masked_text": text}
        for value, text in (("1", "parent action"), ("2", "child action"))
    ]
    segments = [
        {"document_id": "1", "segment_index": 1, "segment_id": "1:oa:001", "text": "parent action"},
        {"document_id": "2", "segment_index": 1, "segment_id": "2:oa:001", "text": "child action"},
    ]
    candidates = {"2": [{"child_id": "2", "parent_id": "1", "rrf_rank": "1",
                           "operative_alignments": "[[0, 0, 0.9]]"}]}
    payload = build_payload(sampled, documents, segments, candidates)
    candidate = payload["children"][0]["candidates"][0]
    assert "rrf_rank" not in candidate
    assert "score" not in candidate
    assert candidate["evidence"][0]["child_segment_id"] == "2:oa:001"
    assert candidate["evidence"][0]["parent_segment_id"] == "1:oa:001"
