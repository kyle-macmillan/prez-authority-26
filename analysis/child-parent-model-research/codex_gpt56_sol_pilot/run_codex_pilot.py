#!/usr/bin/env python3
"""Run isolated, schema-constrained Codex calls only when explicitly enabled."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FROZEN = ROOT / "data/parent_analysis/function_parent_pilot/eo_pilot_20_v2"


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as handle:
        yield from (json.loads(line) for line in handle if line.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, choices=("ranking", "acceptance"))
    parser.add_argument("--execute", action="store_true", help="required safety switch; calls Codex")
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--reasoning-effort", default="xhigh")
    args = parser.parse_args()
    if args.phase == "ranking":
        request_path = FROZEN / "gemini_rank_v2_requests.jsonl"
    else:
        request_path = HERE / "outputs" / "acceptance_requests.jsonl"
    schema = HERE / "schemas" / f"{args.phase}.schema.json"
    output = HERE / "outputs" / f"{args.phase}_responses.jsonl"
    log_dir = HERE / "logs" / args.phase
    requests = list(read_jsonl(request_path)) if request_path.exists() else []
    plan = {"phase": args.phase, "requests": len(requests), "input": str(request_path),
            "output": str(output), "model": args.model, "reasoning_effort": args.reasoning_effort}
    if not args.execute:
        print(json.dumps({"DRY_RUN": True, **plan}, sort_keys=True))
        print("No Codex calls were made. Re-run with --execute only after approving the pilot.", file=sys.stderr)
        return
    if not requests:
        raise FileNotFoundError(f"no requests found at {request_path}")
    log_dir.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as responses:
        for ordinal, request in enumerate(requests, 1):
            child_id = str(request["metadata"]["child_id"])
            stem = f"{ordinal:02d}_{child_id}"
            answer_path, event_path = log_dir / f"{stem}.answer.json", log_dir / f"{stem}.events.jsonl"
            command = ["codex", "exec", "--model", args.model,
                       "-c", f'model_reasoning_effort="{args.reasoning_effort}"',
                       "--ephemeral", "--ignore-user-config", "--ignore-rules", "--sandbox", "read-only",
                       "--output-schema", str(schema), "--output-last-message", str(answer_path), "--json", "-"]
            stderr_path = log_dir / f"{stem}.stderr.txt"
            with event_path.open("w", encoding="utf-8") as events, stderr_path.open("w", encoding="utf-8") as stderr:
                prompt = "Do not invoke any tools. Judge only the supplied request content.\n\n" + request["contents"]
                completed = subprocess.run(command, input=prompt, text=True,
                                           stdout=events, stderr=stderr, check=False)
            if completed.returncode or not answer_path.exists():
                raise RuntimeError(f"child {child_id} failed (exit {completed.returncode}); see {event_path} and {stderr_path}")
            response = {"request_id": request["request_id"], "metadata": request["metadata"],
                        "text": answer_path.read_text(encoding="utf-8"), "model": args.model,
                        "model_version": "codex-cli", "event_log": str(event_path)}
            responses.write(json.dumps(response, ensure_ascii=False) + "\n")
            print(json.dumps({"completed": ordinal, "child_id": child_id, "phase": args.phase}))


if __name__ == "__main__":
    main()
