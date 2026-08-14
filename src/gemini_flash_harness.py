#!/usr/bin/env python3
"""Safe, resumable transport harness for Gemini 3.6 Flash on Vertex AI.

This module deliberately does not construct legal-analysis prompts or discover
corpus files.  Request JSONL must be prepared separately and reviewed before
execution.  The CLI is dry-run unless both ``--execute`` and
``--confirm-network`` are supplied.

Request format (one JSON object per line)::

    {"request_id": "example-1", "contents": " reviewed prompt ",
     "metadata": {"child_id": "..."}}

The metadata is carried through to the output but is never sent to Gemini.
Google Search grounding is disabled unless ``--google-search`` is supplied.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from tqdm import tqdm


DEFAULT_MODEL = "gemini-3.6-flash"
DEFAULT_PROJECT = "prez-authority"
DEFAULT_LOCATION = "global"
TRANSIENT_HTTP_CODES = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class Request:
    request_id: str
    contents: str
    metadata: dict[str, Any]


def load_requests(path: Path) -> list[Request]:
    requests: list[Request] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            raw = json.loads(line)
            request_id = str(raw["request_id"])
            if request_id in seen:
                raise ValueError(f"duplicate request_id on line {line_number}: {request_id}")
            contents = raw["contents"]
            if not isinstance(contents, str) or not contents.strip():
                raise ValueError(f"contents must be non-empty text on line {line_number}")
            metadata = raw.get("metadata", {})
            if not isinstance(metadata, dict):
                raise ValueError(f"metadata must be an object on line {line_number}")
            requests.append(Request(request_id, contents, metadata))
            seen.add(request_id)
    return requests


def completed_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    ids: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                ids.add(str(json.loads(line)["request_id"]))
    return ids


def _attempt_log_path(output: Path) -> Path:
    return output.with_name(output.name + ".attempts.jsonl")


def _attempt_state(path: Path) -> tuple[dict[str, str], dict[str, int]]:
    state: dict[str, str] = {}
    counts: dict[str, int] = {}
    if not path.exists():
        return state, counts
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            request_id = str(row["request_id"])
            counts[request_id] = max(counts.get(request_id, 0), int(row.get("attempt", 0)))
            state[request_id] = str(row["status"])
    return state, counts


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        handle.flush()


def _transient_http_code(exc: Exception) -> int | None:
    """Return a retryable HTTP status without depending on one SDK exception type."""
    candidates = [
        getattr(exc, "status_code", None),
        getattr(exc, "code", None),
        getattr(getattr(exc, "response", None), "status_code", None),
    ]
    for value in candidates:
        try:
            code = int(value)
        except (TypeError, ValueError):
            continue
        if code in TRANSIENT_HTTP_CODES:
            return code
    message = str(exc)
    for code in TRANSIENT_HTTP_CODES:
        if re.search(rf"(?<!\d){code}(?!\d)", message):
            return code
    return None


def _client(project: str, location: str):
    # Force credential discovery before any request is written to the submission
    # ledger. The genai client otherwise loads ADC lazily inside generate_content,
    # which can make a purely local authentication failure look like an unknown
    # network outcome.
    import google.auth
    from google import genai
    from google.genai import types

    google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
        quota_project_id=project,
    )

    # One SDK transport attempt per submitted request.  The harness owns
    # retries because an SDK retry can be invisible to the submission ledger.
    http_options = types.HttpOptions(
        retry_options=types.HttpRetryOptions(attempts=1)
    )
    return genai.Client(
        vertexai=True, project=project, location=location, http_options=http_options
    )


def _generation_config(*, google_search: bool, thinking_off: bool):
    if not google_search and not thinking_off:
        return None
    from google.genai import types

    kwargs = {}
    if google_search:
        kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]
    if thinking_off:
        kwargs["thinking_config"] = types.ThinkingConfig(
            include_thoughts=False, thinking_budget=0
        )
    return types.GenerateContentConfig(**kwargs)


def _search_config(enabled: bool):
    """Compatibility wrapper for callers that only configure Google Search."""
    return _generation_config(google_search=enabled, thinking_off=False)


def _grounding_metadata(response: Any) -> Any:
    """Return SDK grounding metadata in a JSON-serializable form when present."""
    candidates = getattr(response, "candidates", None) or []
    metadata = getattr(candidates[0], "grounding_metadata", None) if candidates else None
    if metadata is None:
        return None
    if hasattr(metadata, "model_dump"):
        return metadata.model_dump(mode="json")
    if hasattr(metadata, "to_json_dict"):
        return metadata.to_json_dict()
    return str(metadata)


def _usage_metadata(response: Any) -> Any:
    """Return model token usage in a JSON-serializable form when present."""
    metadata = getattr(response, "usage_metadata", None)
    if metadata is None:
        return None
    if hasattr(metadata, "model_dump"):
        return metadata.model_dump(mode="json")
    if hasattr(metadata, "to_json_dict"):
        return metadata.to_json_dict()
    return str(metadata)


def run_requests(
    requests: Iterable[Request],
    output: Path,
    *,
    model: str = DEFAULT_MODEL,
    project: str = DEFAULT_PROJECT,
    location: str = DEFAULT_LOCATION,
    execute: bool = False,
    confirm_network: bool = False,
    google_search: bool = False,
    thinking_off: bool = False,
    delay_seconds: float = 0.0,
    transient_backoff_seconds: float = 5.0,
    transient_backoff_max_seconds: float = 60.0,
    attempt_log: Path | None = None,
    retry_unknown: bool = False,
) -> dict[str, int]:
    if delay_seconds < 0:
        raise ValueError("delay seconds must be nonnegative")
    if transient_backoff_seconds < 0 or transient_backoff_max_seconds < 0:
        raise ValueError("transient backoff seconds must be nonnegative")
    requests = list(requests)
    done = completed_ids(output)
    attempt_log = attempt_log or _attempt_log_path(output)
    attempt_states, attempt_counts = _attempt_state(attempt_log)
    unknown = {
        request_id for request_id, status in attempt_states.items()
        if status in {"submitted", "unknown_outcome"} and request_id not in done
    }
    pending = [
        request for request in requests
        if request.request_id not in done
        and (retry_unknown or request.request_id not in unknown)
    ]
    if not execute:
        return {
            "total": len(requests), "completed": len(done), "unknown": len(unknown),
            "pending": len(pending), "sent": 0,
        }
    if not confirm_network:
        raise RuntimeError("network execution requires --confirm-network")

    client = _client(project, location)
    config = _generation_config(google_search=google_search, thinking_off=thinking_off)
    output.parent.mkdir(parents=True, exist_ok=True)
    attempt_log.parent.mkdir(parents=True, exist_ok=True)
    sent = 0
    newly_unknown = 0
    consecutive_transient_errors = 0
    progress = tqdm(pending, desc="Gemini requests", unit="request")
    progress.set_postfix(remaining=len(pending))
    for request in progress:
        attempt = attempt_counts.get(request.request_id, 0) + 1
        submitted_at = datetime.now(timezone.utc).isoformat()
        # Write the exact request before calling the API.  If the process dies
        # after this point, the next run treats the outcome as unknown and does
        # not spend again unless --retry-unknown is explicitly supplied.
        _append_jsonl(attempt_log, {
            "request_id": request.request_id,
            "attempt": attempt,
            "status": "submitted",
            "submitted_at": submitted_at,
            "model": model,
            "project": project,
            "location": location,
            "google_search": google_search,
            "thinking_off": thinking_off,
            "contents": request.contents,
            "metadata": request.metadata,
        })
        try:
            response = client.models.generate_content(
                model=model, contents=request.contents, config=config
            )
        except Exception as exc:
            transient_code = _transient_http_code(exc)
            _append_jsonl(attempt_log, {
                "request_id": request.request_id,
                "attempt": attempt,
                "status": "unknown_outcome",
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "transient_http_code": transient_code,
            })
            if transient_code is None:
                raise
            newly_unknown += 1
            consecutive_transient_errors += 1
            cooldown = min(
                transient_backoff_max_seconds,
                transient_backoff_seconds * (2 ** (consecutive_transient_errors - 1)),
            )
            progress.set_postfix(
                remaining=len(pending) - sent - newly_unknown,
                unknown=len(unknown) + newly_unknown,
                cooldown=cooldown,
            )
            if cooldown:
                time.sleep(cooldown)
            continue
        record = {
            "request_id": request.request_id,
            "metadata": request.metadata,
            "model": model,
            "model_version": getattr(response, "model_version", None),
            "text": response.text,
            "grounding_metadata": _grounding_metadata(response),
            "usage_metadata": _usage_metadata(response),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _append_jsonl(output, record)
        _append_jsonl(attempt_log, {
            "request_id": request.request_id,
            "attempt": attempt,
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        sent += 1
        consecutive_transient_errors = 0
        progress.set_postfix(remaining=len(pending) - sent - newly_unknown)
        if delay_seconds:
            time.sleep(delay_seconds)
    return {
        "total": len(requests), "completed": len(done) + sent,
        "unknown": len(unknown) + newly_unknown,
        "pending": len(pending) - sent - newly_unknown,
        "sent": sent,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("requests", type=Path, help="reviewed request JSONL")
    parser.add_argument("output", type=Path, help="resumable response JSONL")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--project", default=os.getenv("GOOGLE_CLOUD_PROJECT", DEFAULT_PROJECT))
    parser.add_argument("--location", default=os.getenv("GOOGLE_CLOUD_LOCATION", DEFAULT_LOCATION))
    parser.add_argument("--execute", action="store_true", help="permit network requests")
    parser.add_argument("--confirm-network", action="store_true", help="explicit second execution confirmation")
    parser.add_argument(
        "--google-search",
        action="store_true",
        help="enable Google Search grounding; requires the two network confirmations",
    )
    parser.add_argument(
        "--thinking-off",
        action="store_true",
        help="disable Gemini thinking/reasoning tokens for this run",
    )
    parser.add_argument("--delay-seconds", type=float, default=0.0)
    parser.add_argument(
        "--transient-backoff-seconds", type=float, default=5.0,
        help="initial cooldown after a 429 or retryable 5xx; the uncertain request is not retried",
    )
    parser.add_argument(
        "--transient-backoff-max-seconds", type=float, default=60.0,
        help="maximum exponential cooldown after consecutive transient failures",
    )
    parser.add_argument("--attempt-log", type=Path)
    parser.add_argument(
        "--retry-unknown",
        action="store_true",
        help="retry requests whose prior submission outcome is unknown; may spend twice",
    )
    args = parser.parse_args()
    requests = load_requests(args.requests)
    summary = run_requests(
        requests,
        args.output,
        model=args.model,
        project=args.project,
        location=args.location,
        execute=args.execute,
        confirm_network=args.confirm_network,
        google_search=args.google_search,
        thinking_off=args.thinking_off,
        delay_seconds=args.delay_seconds,
        transient_backoff_seconds=args.transient_backoff_seconds,
        transient_backoff_max_seconds=args.transient_backoff_max_seconds,
        attempt_log=args.attempt_log,
        retry_unknown=args.retry_unknown,
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
