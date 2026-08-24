#!/usr/bin/env python3
"""Run the blinded HC parent requests through local Codex, resumably."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent
DEFAULT_PACKAGE = HERE / "outputs/sol_hc_parent_100"
DEFAULT_PROMPT = HERE / "sol_parent_prompt.md"
DEFAULT_SCHEMA = HERE / "sol_parent_response.schema.json"


def validate_response(response: dict, request: dict) -> None:
    if response.get("case_id") != request["case_id"]:
        raise ValueError("response case_id does not match request")
    decision = response.get("decision")
    if decision not in {"candidate", "none", "uncertain"}:
        raise ValueError(f"invalid decision: {decision!r}")
    labels = {row["candidate_label"] for row in request["candidates"]}
    ranking = response.get("candidate_ranking")
    if not isinstance(ranking, list) or len(ranking) != 3:
        raise ValueError("candidate_ranking must contain exactly three labels")
    if len(set(ranking)) != 3 or any(label not in labels for label in ranking):
        raise ValueError("candidate_ranking must contain three unique valid labels")
    selected = response.get("selected_candidate_label")
    if decision == "candidate" and selected not in labels:
        raise ValueError(f"candidate decision has invalid label: {selected!r}")
    if decision == "candidate" and selected != ranking[0]:
        raise ValueError("selected candidate must be first in candidate_ranking")
    if decision != "candidate" and selected is not None:
        raise ValueError("none/uncertain decision must use a null selected_candidate_label")
    confidence = response.get("confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
        raise ValueError("confidence must be numeric and between zero and one")


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-dir", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--reasoning-effort", default="low")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    codex = shutil.which("codex")
    if not codex:
        raise SystemExit("codex CLI not found on PATH")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")

    request_paths = sorted((args.package_dir / "requests").glob("SHC*.json"))
    if args.case_ids:
        wanted = set(args.case_ids)
        request_paths = [path for path in request_paths if path.stem in wanted]
        missing = wanted - {path.stem for path in request_paths}
        if missing:
            raise SystemExit(f"unknown case IDs: {sorted(missing)}")
    if args.limit is not None:
        request_paths = request_paths[:args.limit]
    responses = args.package_dir / "responses"
    logs = args.package_dir / "logs"
    responses.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    base_prompt = DEFAULT_PROMPT.read_text(encoding="utf-8")
    attempts = args.package_dir / "attempts.jsonl"
    completed = 0

    for index, request_path in enumerate(request_paths, 1):
        request = json.loads(request_path.read_text(encoding="utf-8"))
        case_id = request["case_id"]
        response_path = responses / f"{case_id}.json"
        if response_path.exists() and not args.force:
            try:
                validate_response(json.loads(response_path.read_text(encoding="utf-8")), request)
                print(json.dumps({"case_id": case_id, "status": "already_complete"}), flush=True)
                completed += 1
                continue
            except (ValueError, json.JSONDecodeError):
                raise SystemExit(f"existing response is invalid; inspect or rerun with --force: {response_path}")
        prompt = (
            base_prompt.rstrip() + "\n\nCASE DATA\n" +
            json.dumps(request, ensure_ascii=False, separators=(",", ":")) + "\n"
        )
        command = [
            codex, "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral",
            "--model", args.model,
            "--config", f'model_reasoning_effort="{args.reasoning_effort}"',
            "--sandbox", "read-only", "--skip-git-repo-check",
            "--output-schema", str(DEFAULT_SCHEMA),
            "--color", "never", "--json", "-",
        ]
        if args.dry_run:
            print(json.dumps({
                "case_id": case_id, "status": "dry_run", "model": args.model,
                "reasoning_effort": args.reasoning_effort, "prompt_characters": len(prompt),
                "command": command[:-1] + ["<PROMPT_ON_STDIN>"],
            }), flush=True)
            continue
        started = datetime.now(timezone.utc).isoformat()
        append_jsonl(attempts, {
            "case_id": case_id, "event": "started", "timestamp": started,
            "model": args.model, "reasoning_effort": args.reasoning_effort,
            "request_sha256": __import__("hashlib").sha256(request_path.read_bytes()).hexdigest(),
        })
        with tempfile.NamedTemporaryFile(
            dir=responses, prefix=f".{case_id}.", suffix=".json", delete=False
        ) as handle:
            temporary = Path(handle.name)
        command[-1:-1] = ["--output-last-message", str(temporary)]
        result = subprocess.run(
            command, input=prompt, text=True, capture_output=True, cwd=args.package_dir,
        )
        (logs / f"{case_id}.events.jsonl").write_text(result.stdout, encoding="utf-8")
        (logs / f"{case_id}.stderr.txt").write_text(result.stderr, encoding="utf-8")
        if result.returncode:
            temporary.unlink(missing_ok=True)
            append_jsonl(attempts, {
                "case_id": case_id, "event": "failed", "timestamp": datetime.now(timezone.utc).isoformat(),
                "returncode": result.returncode,
            })
            raise SystemExit(f"{case_id} failed with exit code {result.returncode}; see {logs}")
        try:
            response = json.loads(temporary.read_text(encoding="utf-8"))
            validate_response(response, request)
        except (ValueError, json.JSONDecodeError) as error:
            temporary.rename(logs / f"{case_id}.invalid_response.txt")
            append_jsonl(attempts, {
                "case_id": case_id, "event": "invalid", "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(error),
            })
            raise SystemExit(f"{case_id} returned an invalid response: {error}")
        temporary.replace(response_path)
        append_jsonl(attempts, {
            "case_id": case_id, "event": "completed", "timestamp": datetime.now(timezone.utc).isoformat(),
            "decision": response["decision"], "selected_candidate_label": response["selected_candidate_label"],
        })
        completed += 1
        print(json.dumps({
            "case_id": case_id, "status": "completed", "progress": f"{index}/{len(request_paths)}",
            "decision": response["decision"],
        }), flush=True)
    print(json.dumps({"selected_requests": len(request_paths), "complete_or_preexisting": completed, "dry_run": args.dry_run}))


if __name__ == "__main__":
    main()
