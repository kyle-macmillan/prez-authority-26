import json
from pathlib import Path

from build_canonical_function_profiles import current_profile, request_row


def function(function_id="P1", evidence="Policy text"):
    return {
        "function_id": function_id,
        "label": "policy",
        "actor": "President",
        "action": "direct",
        "target": "agency",
        "mechanism": "directive",
        "effect": "action",
        "condition": "",
        "timing": "",
        "evidence": evidence,
        "evidence_start": 0,
        "evidence_end": len(evidence),
        "confidence": "high",
    }


def profile(*, operative=True):
    policy = function()
    operative_rows = []
    if operative:
        operative = function("O1", "Do this")
        operative["segment_id"] = "1:oa:001"
        operative_rows.append(operative)
    return {
        "document_id": "1",
        "policy_functions": [policy],
        "operative_functions": operative_rows,
        "notes": "",
    }


def test_reuses_one_current_profile(tmp_path: Path):
    source = tmp_path / "profiles.jsonl"
    row = {"document_id": "1", "profile": profile()}
    selected, status, errors = current_profile(
        "1", [(source, row)], {"cleaned_masked_text": "Policy text"},
        {"1:oa:001": "Do this"},
    )
    assert status == "reused"
    assert selected["profile"]["operative_functions"][0]["function_id"] == "O1"
    assert errors == []


def test_empty_operative_profile_requires_confirmation(tmp_path: Path):
    source = tmp_path / "profiles.jsonl"
    selected, status, _ = current_profile(
        "1", [(source, {"document_id": "1", "profile": profile(operative=False)})],
        {"cleaned_masked_text": "Policy text"}, {"1:oa:001": "Do this"},
    )
    assert selected is not None
    assert status == "zero_operative_functions"


def test_confirmation_request_has_unique_stage_id():
    document = {
        "document_id": "1", "document_type": "executive_order", "title": "Test",
        "cleaned_masked_text": "Policy text", "date": "January 1, 2000",
    }
    segments = [{"segment_id": "1:oa:001", "segment_index": 1, "text": "Do this"}]
    row = request_row(document, segments, build_hash="a" * 64, stage="zero_confirmation")
    assert row["request_id"].startswith("function-profile-v1-zero-confirmation:")
    assert row["metadata"]["repair_stage"] == "zero_confirmation"
    assert "do not invent" in row["contents"]
