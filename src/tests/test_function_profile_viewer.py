from build_function_profile_viewer import build_html, build_payload


def test_viewer_payload_keeps_source_masked_and_groups_functions():
    documents = [{"document_id": "1", "document_type": "executive_order", "title": "Test",
                  "date": "January 01, 2020", "cleaned_masked_text": "The [AUTHORITY] Secretary shall act."}]
    segments = [{"document_id": "1", "segment_id": "1:oa:001", "segment_index": 1,
                 "text": "The Secretary shall act."}]
    profiles = [{"request_id": "r1", "document_id": "1", "model": "gemini-3.6-flash",
                 "profile": {"document_id": "1", "policy_functions": [], "operative_functions": [{
                     "function_id": "f1", "segment_id": "1:oa:001", "label": "act", "actor": "Secretary",
                     "action": "act", "target": "", "mechanism": "", "effect": "", "condition": "",
                     "timing": "", "evidence": "The Secretary shall act.", "evidence_start": 0,
                     "evidence_end": 24, "confidence": "high"}], "notes": ""}}]
    payload = build_payload(profiles, [{"request_id": "r1", "text": "{}"}], documents, segments)
    assert payload["documents"][0]["source_text"].count("[AUTHORITY]") == 1
    assert len(payload["documents"][0]["operative_functions"]) == 1
    output = build_html(payload)
    assert "Test" in output
    assert "Raw validated Flash JSON" in output
    assert "The [AUTHORITY] Secretary shall act." in output

