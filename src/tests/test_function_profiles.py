import json

from build_function_profile_requests import build_requests, read_document_ids
from consolidate_function_profiles import consolidate_runs
from function_profiles import parse_json_response, validate_profile
from validate_function_profiles import normalize_profile_response, validate_responses


def _document():
    return {
        "document_id": "1",
        "document_type": "executive_order",
        "title": "test directive",
        "date": "January 01, 2020",
        "cleaned_masked_text": "The Secretary shall establish a review process.",
    }


def test_document_id_allowlist_is_read_from_csv(tmp_path):
    children = tmp_path / "unresolved_children.csv"
    children.write_text("document_id,title\n1,one\n2,two\n", encoding="utf-8")
    assert read_document_ids(children) == {"1", "2"}


def test_validated_profile_cache_is_authoritative_consumed_id_source(tmp_path):
    cache = tmp_path / "function_profiles.jsonl"
    cache.write_text(
        '{"document_id":"1","prompt_version":"function-profile-v1","profile":{}}\n',
        encoding="utf-8",
    )
    assert read_document_ids(cache) == {"1"}
    assert read_document_ids(tmp_path / "missing.jsonl") == set()


def test_status_inventory_consumes_only_ids_with_saved_responses(tmp_path):
    inventory = tmp_path / "inventory.csv"
    inventory.write_text(
        "document_id,response_saved,validation_status\n1,true,validated\n2,false,not_submitted\n",
        encoding="utf-8",
    )
    assert read_document_ids(inventory) == {"1"}


def test_request_builder_intersects_explicit_ids_with_allowlist(tmp_path):
    children = tmp_path / "unresolved_children.csv"
    children.write_text("document_id\n1\n", encoding="utf-8")
    requests = build_requests(
        [_document(), {**_document(), "document_id": "2"}], [], ids=read_document_ids(children)
    )
    assert [row["metadata"]["document_id"] for row in requests] == ["1"]


def test_request_is_authority_masked_and_metadata_does_not_contain_text():
    requests = build_requests([_document()], [{
        "document_id": "1", "segment_id": "1:oa:001", "segment_index": 1,
        "text": "The Secretary shall establish a review process.",
    }])
    assert len(requests) == 1
    assert "[AUTHORITY]" not in requests[0]["metadata"]
    assert "The Secretary shall establish" in requests[0]["contents"]
    assert requests[0]["request_id"] == "function-profile-v1:1"


def test_pilot_can_exclude_documents_without_operative_segments():
    documents = [_document(), {**_document(), "document_id": "2"}]
    segments = [{
        "document_id": "1", "segment_id": "1:oa:001", "segment_index": 1,
        "text": "The Secretary shall establish a review process.",
    }]
    requests = build_requests(documents, segments, require_operative_segments=True)
    assert [row["metadata"]["document_id"] for row in requests] == ["1"]


def test_profile_requires_exact_evidence_and_offsets():
    raw = {
        "document_id": "1",
        "policy_functions": [{
            "function_id": "p1", "label": "establish review process", "actor": "Secretary",
            "action": "establish", "target": "review process", "mechanism": "",
            "effect": "", "condition": "", "timing": "", "evidence": "The Secretary shall establish",
            "evidence_start": 0, "evidence_end": 29, "confidence": "high",
        }],
        "operative_functions": [], "notes": "",
    }
    result = validate_profile(raw, document_id="1", full_text=_document()["cleaned_masked_text"], segment_texts={})
    assert result.errors == ()
    assert result.profile["policy_functions"][0]["function_id"] == "p1"


def test_fenced_json_is_supported():
    value = parse_json_response("```json\n{\"document_id\": \"1\"}\n```")
    assert value == {"document_id": "1"}


def test_response_validator_keeps_invalid_profiles_out():
    responses = [{"request_id": "x", "metadata": {"document_id": "1"}, "text": "not json"}]
    profiles, errors = validate_responses(responses, [_document()], [])
    assert profiles == []
    assert errors[0]["request_id"] == "x"


def test_normalization_recovers_whitespace_only_evidence_difference():
    raw = {
        "document_id": "1",
        "policy_functions": [{
            "function_id": "p1", "label": "review", "actor": "Secretary",
            "action": "establish", "target": "review", "mechanism": "", "effect": "",
            "condition": "", "timing": "", "evidence": "Secretary shall  establish",
            "evidence_start": 4, "evidence_end": 31, "confidence": "high",
        }],
        "operative_functions": [], "notes": "",
    }
    normalized, changes = normalize_profile_response(
        raw, full_text="The Secretary shall establish a review process.", segment_texts={}
    )
    function = normalized["policy_functions"][0]
    assert function["evidence"] == "Secretary shall establish"
    assert function["evidence_start"] == 4
    assert changes


def test_normalization_recovers_unique_token_equivalent_evidence():
    raw = {
        "document_id": "1",
        "policy_functions": [{
            "function_id": "p1", "label": "review", "actor": "Secretary",
            "action": "establish", "target": "review", "mechanism": "", "effect": "",
            "condition": "", "timing": "", "evidence": "the secretary—shall establish",
            "evidence_start": 0, "evidence_end": 30, "confidence": "high",
        }],
        "operative_functions": [], "notes": "",
    }
    normalized, changes = normalize_profile_response(
        raw, full_text="The Secretary shall establish a review process.", segment_texts={}
    )
    function = normalized["policy_functions"][0]
    assert function["evidence"] == "The Secretary shall establish"
    assert function["evidence_start"] == 0
    assert any("unique token-equivalent" in change for change in changes)


def test_normalization_does_not_guess_ambiguous_token_equivalent_evidence():
    evidence = "the secretary—shall establish"
    raw = {
        "document_id": "1",
        "policy_functions": [{
            "function_id": "p1", "label": "review", "actor": "Secretary",
            "action": "establish", "target": "review", "mechanism": "", "effect": "",
            "condition": "", "timing": "", "evidence": evidence,
            "evidence_start": 0, "evidence_end": 30, "confidence": "high",
        }],
        "operative_functions": [], "notes": "",
    }
    normalized, changes = normalize_profile_response(
        raw,
        full_text="The Secretary shall establish one. The Secretary shall establish two.",
        segment_texts={},
    )
    assert normalized["policy_functions"][0]["evidence"] == evidence
    assert not changes


def test_normalization_reassigns_only_unique_matching_segment():
    evidence = "The Secretary shall establish a review process."
    raw = {
        "document_id": "1", "policy_functions": [], "notes": "",
        "operative_functions": [{
            "function_id": "o1", "label": "review", "actor": "Secretary",
            "action": "establish", "target": "review", "mechanism": "", "effect": "",
            "condition": "", "timing": "", "evidence": evidence,
            "evidence_start": 0, "evidence_end": len(evidence), "confidence": "high",
            "segment_id": "1:oa:999",
        }],
    }
    normalized, changes = normalize_profile_response(
        raw, full_text=evidence,
        segment_texts={"1:oa:001": evidence, "1:oa:002": "Different action."},
    )
    assert normalized["operative_functions"][0]["segment_id"] == "1:oa:001"
    assert any("reassigned" in change for change in changes)


def test_numeric_confidence_is_normalized():
    raw = {
        "document_id": "1",
        "policy_functions": [{
            "function_id": "p1", "label": "establish review process", "actor": "Secretary",
            "action": "establish", "target": "review process", "mechanism": "",
            "effect": "", "condition": "", "timing": "", "evidence": "The Secretary shall establish",
            "evidence_start": 0, "evidence_end": 29, "confidence": 1.0,
        }],
        "operative_functions": [], "notes": "",
    }
    result = validate_profile(raw, document_id="1", full_text=_document()["cleaned_masked_text"], segment_texts={})
    assert result.errors == ()
    assert result.profile["policy_functions"][0]["confidence"] == "high"


def test_evidence_offsets_allow_boundary_whitespace():
    raw = {
        "document_id": "1",
        "policy_functions": [{
            "function_id": "p1", "label": "establish review process", "actor": "Secretary",
            "action": "establish", "target": "review process", "mechanism": "",
            "effect": "", "condition": "", "timing": "", "evidence": "The Secretary shall establish",
            "evidence_start": 0, "evidence_end": 30, "confidence": "high",
        }],
        "operative_functions": [], "notes": "",
    }
    result = validate_profile(raw, document_id="1", full_text=_document()["cleaned_masked_text"], segment_texts={})
    assert result.errors == ()


def test_exact_evidence_recomputes_approximate_offsets():
    raw = {
        "document_id": "1",
        "policy_functions": [{
            "function_id": "p1", "label": "establish review process", "actor": "Secretary",
            "action": "establish", "target": "review process", "mechanism": "",
            "effect": "", "condition": "", "timing": "", "evidence": "The Secretary shall establish",
            "evidence_start": 5, "evidence_end": 34, "confidence": "high",
        }],
        "operative_functions": [], "notes": "",
    }
    result = validate_profile(raw, document_id="1", full_text=_document()["cleaned_masked_text"], segment_texts={})
    assert result.errors == ()
    assert result.profile["policy_functions"][0]["evidence_start"] == 0


def test_consolidation_builds_validated_cache_and_inventory(tmp_path):
    run = tmp_path / "run_001"
    run.mkdir()
    request = {
        "request_id": "function-profile-v1:1",
        "contents": "reviewed prompt",
        "metadata": {"document_id": "1", "prompt_version": "function-profile-v1"},
    }
    profile = {"document_id": "1", "policy_functions": [], "operative_functions": [], "notes": ""}
    (run / "function_profile_requests.jsonl").write_text(json.dumps(request) + "\n")
    (run / "function_profile_responses.jsonl").write_text(json.dumps({
        "request_id": request["request_id"], "metadata": request["metadata"],
        "model": "flash", "model_version": "test", "text": json.dumps(profile),
        "created_at": "2026-01-01T00:00:00+00:00", "usage_metadata": {"total": 10},
    }) + "\n")
    (run / "function_profile_responses.jsonl.attempts.jsonl").write_text(
        json.dumps({"request_id": request["request_id"], "status": "completed"}) + "\n"
    )
    cache, inventory, validation = consolidate_runs([run], [_document()], [])
    assert len(cache) == 1
    assert cache[0]["document_id"] == "1"
    assert cache[0]["run_id"] == "run_001"
    assert cache[0]["usage_metadata"] == {"total": 10}
    assert inventory[0]["validation_status"] == "validated"
    assert len(validation["run_001"][0]) == 1
