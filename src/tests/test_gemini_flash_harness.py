import json
from pathlib import Path

import pytest

from gemini_flash_harness import _search_config, _usage_metadata, load_requests, run_requests


def test_dry_run_never_constructs_client(tmp_path: Path):
    requests_path = tmp_path / "requests.jsonl"
    requests_path.write_text(
        '{"request_id":"a","contents":"reviewed prompt","metadata":{"child_id":"1"}}\n',
        encoding="utf-8",
    )
    output = tmp_path / "responses.jsonl"

    summary = run_requests(load_requests(requests_path), output)

    assert summary == {"total": 1, "completed": 0, "unknown": 0, "pending": 1, "sent": 0}
    assert not output.exists()


def test_network_requires_explicit_confirmation(tmp_path: Path):
    request = load_requests(
        _write(tmp_path / "requests.jsonl", '{"request_id":"a","contents":"x"}\n')
    )

    with pytest.raises(RuntimeError, match="confirm-network"):
        run_requests(request, tmp_path / "responses.jsonl", execute=True)


def test_search_is_disabled_by_default():
    assert _search_config(False) is None


def test_usage_metadata_is_absent_when_response_has_none():
    class Response:
        usage_metadata = None

    assert _usage_metadata(Response()) is None


def test_unknown_submission_is_not_retried_by_default(tmp_path: Path, monkeypatch):
    request = load_requests(_write(tmp_path / "requests.jsonl", '{"request_id":"a","contents":"x"}\n'))

    class FailingModels:
        def generate_content(self, **kwargs):
            raise RuntimeError("transport failed")

    class FailingClient:
        models = FailingModels()

    monkeypatch.setattr("gemini_flash_harness._client", lambda project, location: FailingClient())
    output = tmp_path / "responses.jsonl"
    attempts = tmp_path / "attempts.jsonl"
    with pytest.raises(RuntimeError, match="transport failed"):
        run_requests(request, output, execute=True, confirm_network=True, attempt_log=attempts)
    summary = run_requests(request, output, attempt_log=attempts)
    assert summary == {"total": 1, "completed": 0, "unknown": 1, "pending": 0, "sent": 0}
    rows = [json.loads(line) for line in attempts.read_text().splitlines()]
    assert [row["status"] for row in rows] == ["submitted", "unknown_outcome"]


def test_transient_failure_is_held_back_and_processing_continues(tmp_path: Path, monkeypatch):
    requests = load_requests(_write(
        tmp_path / "requests.jsonl",
        '{"request_id":"a","contents":"first"}\n'
        '{"request_id":"b","contents":"second"}\n',
    ))

    class Response:
        text = "ok"
        model_version = "test"
        grounding_metadata = None
        usage_metadata = None

    class Models:
        calls = 0

        def generate_content(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("502 Bad Gateway")
            return Response()

    class Client:
        models = Models()

    sleeps = []
    monkeypatch.setattr("gemini_flash_harness._client", lambda project, location: Client())
    monkeypatch.setattr("gemini_flash_harness.time.sleep", sleeps.append)
    output = tmp_path / "responses.jsonl"
    attempts = tmp_path / "attempts.jsonl"

    summary = run_requests(
        requests, output, execute=True, confirm_network=True,
        attempt_log=attempts, transient_backoff_seconds=3,
    )

    assert summary == {"total": 2, "completed": 1, "unknown": 1, "pending": 0, "sent": 1}
    assert sleeps == [3]
    assert [json.loads(line)["request_id"] for line in output.read_text().splitlines()] == ["b"]
    rows = [json.loads(line) for line in attempts.read_text().splitlines()]
    assert [row["status"] for row in rows] == [
        "submitted", "unknown_outcome", "submitted", "completed",
    ]
    assert rows[1]["transient_http_code"] == 502


def test_non_transient_failure_remains_fail_fast(tmp_path: Path, monkeypatch):
    request = load_requests(_write(tmp_path / "requests.jsonl", '{"request_id":"a","contents":"x"}\n'))

    class Models:
        def generate_content(self, **kwargs):
            raise RuntimeError("400 INVALID_ARGUMENT")

    class Client:
        models = Models()

    monkeypatch.setattr("gemini_flash_harness._client", lambda project, location: Client())
    with pytest.raises(RuntimeError, match="INVALID_ARGUMENT"):
        run_requests(
            request, tmp_path / "responses.jsonl", execute=True,
            confirm_network=True, attempt_log=tmp_path / "attempts.jsonl",
        )


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path
