import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from build_parent_candidate_viewer import (
    _reveal_authorities, _unique_authorities, build_html, build_payload, select_sample,
)


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
        "same_ordering_phrase": "True", "same_ordering_phrase_rank": "1",
        "segment_word_trigram_tfidf_score": "0.4", "segment_word_trigram_rank": "4",
        "segment_text_reuse_words": "18", "segment_text_reuse_rank": "5",
        "rrf_score": "0.17", "rrf_rank": "1", "rrf_k": "20",
    }]}
    payload = build_payload(sampled, documents, segments, candidates)
    candidate = payload["children"][0]["candidates"][0]
    assert candidate["scores"]["document_embedding"] == {"score": 0.8, "rank": 2}
    assert candidate["scores"]["rrf"] == {"score": 0.17, "rank": 1, "k": 20}
    assert candidate["evidence"][0]["child_segment_id"] == "2:oa:001"
    assert candidate["evidence"][0]["parent_segment_id"] == "1:oa:001"
    assert payload["children"][0]["child"]["ordering_spans"] == [[0, 13]]


def test_payload_displays_candidates_in_fused_rank_order():
    sampled = [{"document_id": "3", "document_type": "letter"}]
    documents = [
        {"document_id": value, "document_type": "letter", "identifier": "", "title": value,
         "date": "date", "url": "url", "cleaned_masked_text": "text"}
        for value in ("1", "2", "3")
    ]
    base = {
        "child_id": "3", "operative_alignments": "[]",
        "document_embedding_score": "0.8", "document_embedding_rank": "1",
        "operative_embedding_score": "0.8", "operative_embedding_rank": "1",
        "same_ordering_phrase": "False", "same_ordering_phrase_rank": "2",
        "segment_word_trigram_tfidf_score": "0.8", "segment_word_trigram_rank": "1",
        "segment_text_reuse_words": "1", "segment_text_reuse_rank": "1",
        "rrf_score": "0.1", "rrf_k": "20",
    }
    candidates = {"3": [
        {**base, "parent_id": "1", "rrf_rank": "2"},
        {**base, "parent_id": "2", "rrf_rank": "1"},
    ]}
    payload = build_payload(sampled, documents, [], candidates)
    assert [
        row["parent"]["document_id"] for row in payload["children"][0]["candidates"]
    ] == ["2", "1"]
    assert payload["candidate_order"] == "ascending fused RRF rank"


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


def test_payload_restores_masked_authorities_for_optional_inline_display():
    sampled = [{"document_id": "2", "document_type": "executive_order"}]
    documents = [{
        "document_id": "2", "document_type": "executive_order", "identifier": "14000",
        "title": "child", "date": "date", "url": "url",
        "cleaned_masked_text": "By [AUTHORITY], entry is suspended.",
        "masked_authorities": [
            {"start": 3, "end": 15, "text": "50 U.S.C. 1701", "kind": "usc_section"},
        ],
    }]
    payload = build_payload(sampled, documents, [], {})
    child = payload["children"][0]["child"]
    assert child["text"] == "By [AUTHORITY], entry is suspended."
    assert child["revealed_text"] == "By 50 U.S.C. 1701, entry is suspended."
    viewer = build_html(payload)
    assert "authority-toggle" in viewer
    assert "50 U.S.C. 1701" in viewer


def test_revealing_authorities_rejects_mismatched_artifacts():
    try:
        _reveal_authorities("By [AUTHORITY]", [])
    except ValueError as error:
        assert "count does not match" in str(error)
    else:
        raise AssertionError("mismatched authority artifacts should fail")


def test_authority_list_is_deduplicated_case_and_whitespace_insensitively():
    authorities = [
        {"text": "50 U.S.C. 1701", "kind": "usc_section"},
        {"text": "  50 u.s.c.   1701 ", "kind": "usc_section"},
        {"text": "Executive Order 14000", "kind": "executive_order"},
    ]
    assert _unique_authorities(authorities) == [authorities[0], authorities[2]]
