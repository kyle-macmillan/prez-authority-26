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


def test_payload_preserves_scores_and_alignment_ids():
    sampled = [{"document_id": "2", "document_type": "letter"}]
    documents = [
        {"document_id": value, "document_type": "letter", "identifier": "", "title": value,
         "date": "date", "url": "url", "cleaned_masked_text": text}
        for value, text in (("1", "parent action"), ("2", "shall develop a plan"))
    ]
    segments = [
        {"document_id": "1", "segment_index": 1, "segment_id": "1:oa:001", "text": "parent action"},
        {"document_id": "2", "segment_index": 1, "segment_id": "2:oa:001", "text": "shall develop a plan"},
    ]
    candidates = {"2": [{
        "child_id": "2", "parent_id": "1", "operative_alignments": "[[0, 0, 0.9]]",
        "document_embedding_score": "0.8", "document_embedding_rank": "2",
        "operative_embedding_score": "0.9", "operative_embedding_rank": "1",
        "bm25_score": "12.5", "bm25_rank": "3",
        "word_trigram_tfidf_score": "0.4", "word_trigram_rank": "4",
        "text_reuse_words": "18", "text_reuse_rank": "5",
        "rrf_score": "0.17", "rrf_rank": "1", "rrf_k": "20",
    }]}
    payload = build_payload(sampled, documents, segments, candidates)
    candidate = payload["children"][0]["candidates"][0]
    assert candidate["scores"]["document_embedding"] == {"score": 0.8, "rank": 2}
    assert candidate["scores"]["rrf"] == {"score": 0.17, "rank": 1, "k": 20}
    assert candidate["evidence"][0]["child_segment_id"] == "2:oa:001"
    assert candidate["evidence"][0]["parent_segment_id"] == "1:oa:001"
    assert payload["children"][0]["child"]["ordering_spans"] == [[0, 13]]


def test_payload_keeps_operative_selection_and_separate_namespace():
    sampled = [{"document_id": "2", "document_type": "letter"}]
    documents = [{
        "document_id": "2", "document_type": "letter", "identifier": "",
        "title": "child", "date": "date", "url": "url",
        "cleaned_masked_text": "entry is hereby suspended",
    }]
    selection = {"2": {"selected_policy": "rule", "model_evidence": "entry is suspended"}}
    payload = build_payload(
        sampled, documents, [], {}, selections=selection, sample_prefix="OP",
        storage_namespace="path-dependency-operative-pilot-v1",
        sample_design="automated Code 3",
    )
    assert payload["children"][0]["sample_id"] == "OP001"
    assert payload["children"][0]["selection"] == selection["2"]
    assert payload["storage_namespace"] == "path-dependency-operative-pilot-v1"
    assert payload["sample_design"] == "automated Code 3"
