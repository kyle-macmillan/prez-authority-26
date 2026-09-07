"""Tests for the one-call-per-EO Sol population classifier."""
from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("sol_eo_population", HERE / "sol_eo_population.py")
population = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(population)


def test_population_is_nonceremonial_and_has_expected_segment_coverage():
    requests, no_segments = population.target_eos()
    assert len(requests) == 993
    assert len(no_segments) == 23
    assert sum(len(row["segments"]) for row in requests) == 5224
    assert all(row["segments"] for row in requests)


def test_prompt_contains_every_segment_once_and_no_labels():
    requests, _ = population.target_eos()
    prompt = population.render_prompt("PREFIX", requests[0])
    assert "FULL_DIRECTIVE_CONTEXT" in prompt and "OPERATIVE_SEGMENTS" in prompt
    assert "gold_code" not in prompt
    for segment in requests[0]["segments"]:
        assert prompt.count(segment["segment_id"]) == 1


def test_multi_segment_answer_validation():
    request = {"segments": [
        {"segment_id": "1:oa:001", "text": "The Secretary shall review the program."},
        {"segment_id": "1:oa:002", "text": "I hereby waive section 7."},
    ]}
    answer = {"classifications": [
        {"segment_id": "1:oa:001", "code": 1, "rationale": "Review.", "evidence": "shall review the program"},
        {"segment_id": "1:oa:002", "code": 3, "rationale": "Waiver.", "evidence": "I hereby waive section 7"},
    ]}
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "answer.json"
        path.write_text(json.dumps(answer))
        parsed, errors = population.parse_answer(path, request)
        assert parsed == answer and not errors
        answer["classifications"].reverse()
        path.write_text(json.dumps(answer))
        parsed, errors = population.parse_answer(path, request)
        assert parsed is None and errors


def test_population_calls_are_time_bounded():
    assert population.CALL_TIMEOUT_SECONDS == 90


def test_progress_tracks_failures_without_treating_them_as_success(tmp_path=None):
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "responses.jsonl"
        population.append_jsonl(path, {"document_id": "1", "prompt_hash": "p", "ok": True})
        population.append_jsonl(path, {"document_id": "2", "prompt_hash": "p", "ok": False})
        assert population.response_progress(path, "p") == {"processed": 2, "successful": 1, "failed": 1}


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test(); print(f"PASS {test.__name__}")
    print(f"{len(tests)} tests passed")
