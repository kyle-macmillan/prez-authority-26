"""Focused tests for the staged parent-method workflow."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from build_parent_method_pilot import build_pilot
from build_parent_method_viewer import build_payload, build_html
from evaluate_parent_retrieval import metrics_for_rankings
from parent_reranker_protocol import no_llm_baseline, normalize_responses, requests_for_candidates
from synthesize_directives import build_requests, import_responses


def source_rows():
    documents = [
        {
            "document_id": "1", "document_type": "letter", "date": "January 1, 2020",
            "title": "Earlier", "cleaned_masked_text": "The agency shall act.",
        },
        {
            "document_id": "2", "document_type": "executive_order", "date": "January 2, 2020",
            "title": "Later", "cleaned_masked_text": "Under [AUTHORITY], the agency shall act.",
            "masked_authorities": [{"text": "SECRET LAW", "kind": "named_act"}],
        },
    ]
    segments = [
        {"document_id": "1", "segment_id": "1:oa:001", "segment_index": 1,
         "text": "The agency shall act."},
        {"document_id": "2", "segment_id": "2:oa:001", "segment_index": 1,
         "text": "The agency shall act."},
    ]
    return documents, segments


def test_synthesis_request_and_import_are_grounded():
    documents, segments = source_rows()
    requests = build_requests(documents, segments, {"2"})
    response = {
        "request_id": requests[0]["request_id"], "model": "frontier-test",
        "output": {
            "policy": {
                "problem": "agency inaction", "subject_matter": "administration",
                "affected_entities": ["agency"], "geographic_scope": [], "triggers": [],
                "programs": [], "institutional_actors": ["agency"],
                "evidence_segment_ids": ["2:oa:001"],
            },
            "actions": [{
                "actor": "agency", "action": "act", "object": "policy",
                "mechanism": "direction", "conditions": "", "intended_effect": "action",
                "evidence_segment_ids": ["2:oa:001"],
            }],
        },
    }
    result = import_responses(requests, [response])[0]
    assert result["model"] == "frontier-test"
    assert result["actions"][0]["action_id"] == "2:action:001"
    assert "agency inaction" in result["embedding_text"]


def test_reranker_protocol_uses_conjunctive_score_and_baseline():
    documents, segments = source_rows()
    candidates = [{
        "child_id": "2", "parent_id": "1", "cleaned_embedding_rank": "1",
        "lexical_tfidf_rank": "2", "synthesis_embedding_rank": "",
    }]
    requests = requests_for_candidates(candidates, documents, segments)
    outputs = normalize_responses(requests, [{
        "request_id": requests[0]["request_id"],
        "output": {"policy_problem_match": 3, "operative_mechanism_match": 1,
                   "expected_precedent": 2, "evidence_segment_ids": ["2:oa:001"],
                   "rationale": "policy is closer than mechanism"},
    }], "frontier-test")
    assert outputs[0]["score"] == 1
    assert no_llm_baseline(candidates)[0]["rank"] == 1


def test_viewer_never_serializes_recoverable_authority():
    documents, segments = source_rows()
    payload = build_payload(
        [{"document_id": "2", "sample_id": "DEV001"}],
        [{"child_id": "2", "parent_id": "1"}], documents, segments, 7,
    )
    serialized = json.dumps(payload)
    assert "SECRET LAW" not in serialized
    assert "masked_authorities" not in serialized
    assert "plausible" in build_html(payload)


def test_graded_metrics_reward_first_rank_relevance():
    relevance = {("c", "p1"): 2, ("c", "p2"): 0}
    result = metrics_for_rankings({"c": ["p1", "p2"]}, relevance)
    assert result["mrr"] == 1
    assert result["success5"] == 1
    assert result["ndcg10"] == 1


def test_pilot_is_disjoint_and_stratifies_trade():
    # Use an explicit classifier marker to keep this test compact.
    documents, eligible, holdout = [], [], set()
    counter = 0
    for phase in ("development", "evaluation"):
        for kind in ("executive_order", "memorandum", "proclamation", "letter"):
            count = 16 if kind == "proclamation" else 10
            for index in range(count):
                counter += 1; document_id = str(counter)
                text = "tariff imports customs" if kind == "proclamation" else "ordinary policy"
                row = {"document_id": document_id, "document_type": kind, "title": ""}
                eligible.append(row)
                documents.append({**row, "cleaned_masked_text": text})
                if phase == "evaluation":
                    holdout.add(document_id)
    pilot = build_pilot(eligible, documents, holdout, 9)
    assert len(pilot["development"]) == 20
    assert len(pilot["evaluation"]) == 40
    assert not ({row["document_id"] for row in pilot["development"]} & holdout)
    assert sum(row["known_parent_genre"] == "trade_proclamation"
               for row in pilot["evaluation"]) >= 8


if __name__ == "__main__":
    for name, test in sorted(globals().items()):
        if name.startswith("test_"):
            test(); print("  PASS ", name)
