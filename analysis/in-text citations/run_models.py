#!/usr/bin/env python3
"""Resumable Codex runner for prepared Terra/Sol requests.

The runner is inert unless both --execute and --confirm-model-run are supplied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent
PROMPT = HERE / "model_prompt.md"
SCHEMA = HERE / "model_response.schema.json"


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def completed_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {str(row["document_id"]) for row in read_jsonl(path)}


def attempted_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {
        str(row["document_id"]) for row in read_jsonl(path)
        if row.get("event") == "started"
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("requests", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--attempts", type=Path)
    parser.add_argument("--logs", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--retry-unknown", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-model-run", action="store_true")
    args = parser.parse_args()
    requests = read_jsonl(args.requests)
    if args.limit is not None:
        if args.limit < 1:
            parser.error("--limit must be positive")
        requests = requests[:args.limit]
    attempts = args.attempts or args.output.with_suffix(args.output.suffix + ".attempts.jsonl")
    logs = args.logs or args.output.parent / "logs"
    done = completed_ids(args.output)
    unknown = attempted_ids(attempts) - done
    held_unknown = set() if args.retry_unknown else unknown
    pending = [
        row for row in requests
        if str(row["document_id"]) not in done and str(row["document_id"]) not in held_unknown
    ]
    models = sorted({row["model"] for row in requests})
    efforts = sorted({row["reasoning_effort"] for row in requests})
    preview = {
        "requests": len(requests),
        "already_complete": sum(str(row["document_id"]) in done for row in requests),
        "pending": len(pending), "held_unknown": len(held_unknown),
        "models": models, "reasoning_efforts": efforts,
        "output": str(args.output), "attempts": str(attempts), "logs": str(logs),
        "will_execute": bool(args.execute and args.confirm_model_run),
    }
    print(json.dumps(preview, sort_keys=True), flush=True)
    if not (args.execute and args.confirm_model_run):
        return
    codex = shutil.which("codex")
    if not codex:
        raise SystemExit("codex CLI not found on PATH")
    base_prompt = PROMPT.read_text(encoding="utf-8").rstrip()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    for position, request in enumerate(pending, 1):
        document_id = str(request["document_id"])
        prompt = base_prompt + "\n\nDOCUMENT DATA\n" + json.dumps(request, ensure_ascii=False, separators=(",", ":")) + "\n"
        command = [
            codex, "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral",
            "--model", request["model"], "--config",
            f'model_reasoning_effort="{request["reasoning_effort"]}"',
            "--sandbox", "read-only", "--skip-git-repo-check", "--output-schema", str(SCHEMA),
            "--color", "never", "--json", "-",
        ]
        started = datetime.now(timezone.utc).isoformat()
        append_jsonl(attempts, {
            "document_id": document_id, "request_id": request["request_id"], "event": "started",
            "timestamp": started, "model": request["model"],
            "reasoning_effort": request["reasoning_effort"],
            "request_sha256": hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest(),
        })
        with tempfile.NamedTemporaryFile(dir=args.output.parent, prefix=f".{document_id}.", suffix=".json", delete=False) as handle:
            temporary = Path(handle.name)
        command[-1:-1] = ["--output-last-message", str(temporary)]
        result = subprocess.run(command, input=prompt, text=True, capture_output=True, cwd=HERE)
        (logs / f"{document_id}.events.jsonl").write_text(result.stdout, encoding="utf-8")
        (logs / f"{document_id}.stderr.txt").write_text(result.stderr, encoding="utf-8")
        if result.returncode:
            temporary.unlink(missing_ok=True)
            append_jsonl(attempts, {"document_id": document_id, "event": "failed", "timestamp": datetime.now(timezone.utc).isoformat(), "returncode": result.returncode})
            raise SystemExit(f"document {document_id} failed; inspect {logs}")
        try:
            response = json.loads(temporary.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            temporary.replace(logs / f"{document_id}.invalid.txt")
            append_jsonl(attempts, {"document_id": document_id, "event": "invalid", "timestamp": datetime.now(timezone.utc).isoformat(), "error": str(error)})
            raise SystemExit(f"document {document_id} returned invalid JSON")
        temporary.unlink(missing_ok=True)
        append_jsonl(args.output, response)
        append_jsonl(attempts, {"document_id": document_id, "event": "completed", "timestamp": datetime.now(timezone.utc).isoformat()})
        print(json.dumps({"document_id": document_id, "status": "completed", "progress": f"{position}/{len(pending)}"}), flush=True)


if __name__ == "__main__":
    main()
