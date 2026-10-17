"""Selection and blinding invariants for the enriched annotation round."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
import build_annotation_round4 as round4
from build_disagreement_review import extract_source_data
from view_segments import build_html


def row(doc_id, text):
    return {"": str(doc_id), "doc_text": text, "doc_type": "executive_order",
            "president": "Test President", "date": "January 01, 2020", "url": "https://example.com"}


def test_retrieval_does_not_hide_later_legal_outcome_behind_immediate_effect():
    hits = round4.signals("I hereby waive the restriction. The Secretary shall issue regulations requiring disclosure.")
    assert "2_rules" in hits and "3_waivers" in hits
    assert "2_rules" not in round4.signals("The Secretary shall review existing regulations.")


def test_screened_segments_match_viewer_including_inline_vesting():
    source = row(1, "In accordance with section 6(b) of the Act, I hereby designate all funding "
                 "so designated by Congress pursuant to section 251 of the Act, as outlined herein. "
                 "The Secretary shall implement the plan.")
    page = build_html([("executive_order", "EO", "Executive Orders", [source])],
                      seed=round4.SEED, viewer_num=4, wp_only=True)
    _, chunks, _ = extract_source_data(page)
    assert chunks["EO1"] == {s["segment_id"]: s["text"] for s in round4.segments(source)}
    assert "seg-annotations-v3-viewer4-20260925" in page
    assert "var VIEWER_NUM = 4" in page
    assert "triggers" not in page and "request_hash" not in page


def test_dual_positive_documents_fill_two_first_without_duplicate(monkeypatch):
    monkeypatch.setattr(round4, "QUOTAS", {"2": 1, "3": 1, "random": 1})
    candidates = [{"document_id": str(i), "doc_type": "executive_order", "president": "Test",
                   "signals": {"2_rules": {}, "3_waivers": {}}} for i in (1, 2)]
    responses = [{"document_id": str(i), "ok": True,
                  "answer": {"classifications": [{"code": 2}, {"code": 3}]}} for i in (1, 2)]
    rows = {str(i): row(i, "A distinct short document " + str(i)) for i in (1, 2)}
    selected, summary = round4.select_targeted(candidates, responses, rows)
    assert [x["pool"] for x in selected] == ["2", "3"]
    assert len({x["document_id"] for x in selected}) == 2
    assert summary["selected"] == {"2": 1, "3": 1}
    assert selected == round4.select_targeted(candidates[::-1], responses[::-1], rows)[0]


def test_template_cap_and_failed_results_cannot_fill_quota(monkeypatch):
    monkeypatch.setattr(round4, "QUOTAS", {"2": 5, "3": 0})
    candidates = [{"document_id": str(i), "doc_type": "memorandum", "president": "Test",
                   "signals": {"2_rules": {}}} for i in range(6)]
    responses = [{"document_id": str(i), "ok": i != 5,
                  "answer": {"classifications": [{"code": 2}]}} for i in range(6)]
    rows = {str(i): row(i, "The Secretary shall issue specified regulations under section " + str(i)) for i in range(6)}
    selected, summary = round4.select_targeted(candidates, responses, rows)
    assert len(selected) == 3
    assert len(summary["rejected"]) == 2
    assert summary["available"]["2"] == 5


def test_completed_requests_reused_and_changed_requests_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(round4, "AUDIT", tmp_path)
    prompt = {"text": "Fixed prompt", "model": "test", "reasoning_effort": "low"}
    round4.write(tmp_path / "prompt.json", prompt)
    req = {"document_id": "1", "full_context": "Context", "segments": [{"segment_id": "1", "text": "Text"}]}
    fingerprint = round4.digest({"prompt": round4.population.render_prompt(prompt["text"], req),
                                "model": "test", "effort": "low"})
    saved = {"request_hash": fingerprint, "ok": True}
    round4.write(tmp_path / "candidates/1/result.json", saved)
    assert round4.run_one(req, "candidates") == saved
    with pytest.raises(ValueError, match="Frozen request changed"):
        round4.run_one({**req, "full_context": "Changed"}, "candidates")


def test_unknown_attempt_is_not_repeated(tmp_path, monkeypatch):
    monkeypatch.setattr(round4, "AUDIT", tmp_path)
    round4.write(tmp_path / "prompt.json", {"text": "Fixed", "model": "test", "reasoning_effort": "low"})
    round4.write(tmp_path / "candidates/1/started.json", {})
    with pytest.raises(RuntimeError, match="Unknown prior outcome"):
        round4.run_one({"document_id": "1", "full_context": "Text", "segments": []}, "candidates")


def test_service_failure_stops_dispatch_before_rest_of_batch(monkeypatch):
    attempted = []
    def fail(req, phase):
        attempted.append(req)
        return {"returncode": 1, "ok": False}
    monkeypatch.setattr(round4, "run_one", fail)
    with pytest.raises(RuntimeError, match="Classifier process failed"):
        round4.run_requests(list(range(100)), "candidates", workers=1)
    assert attempted == [0]


def test_shorter_preference_within_comparable_cells():
    items = [{"document_id": str(i), "family": "2_rules", "doc_type": "executive_order",
              "president": "Test", "segment_count": n, "word_count": w}
             for i, n, w in [(1, 10, 1000), (2, 2, 500), (3, 2, 300)]]
    assert [x["document_id"] for x in round4.diverse_order(items, prefer_shorter=True)] == ["3", "2", "1"]
