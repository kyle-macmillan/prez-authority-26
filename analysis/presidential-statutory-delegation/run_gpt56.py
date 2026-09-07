#!/usr/bin/env python3
"""Run isolated GPT-5.6 Sol/low statutory-delegation calls via Codex CLI."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import subprocess
import tempfile
import time
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUTPUTS = HERE / "outputs"
SCHEMA = HERE / "response.schema.json"
MODEL = "gpt-5.6-sol"
REASONING_EFFORT = "low"
MAX_ATTEMPTS = 2
FORBIDDEN_EVENT_TYPES = ("command_execution", "mcp", "file_search", "computer", "apply_patch", "image_generation")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_jsonl(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def nested_types(value):
    if isinstance(value, dict):
        if isinstance(value.get("type"), str):
            yield value["type"]
        for child in value.values():
            yield from nested_types(child)
    elif isinstance(value, list):
        for child in value:
            yield from nested_types(child)


def event_metadata(path: Path) -> dict:
    violations, web_search_used, usage = set(), False, {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        for kind in nested_types(event):
            if any(flag in kind.casefold() for flag in FORBIDDEN_EVENT_TYPES):
                violations.add(kind)
            if "web_search" in kind.casefold():
                web_search_used = True
        if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            usage = event["usage"]
    return {"violations": sorted(violations), "web_search_used": web_search_used, "usage": usage}


def validate_answer(answer_path: Path, packet: dict) -> tuple[dict | None, list[str]]:
    errors = []
    try:
        answer = json.loads(answer_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"invalid answer JSON: {exc}"]
    if answer.get("canonical_authority_id") != packet["canonical_authority_id"]:
        errors.append("canonical_authority_id does not match request")
    versions = answer.get("classifications")
    if not isinstance(versions, list) or not versions:
        return None, errors + ["classifications must be a nonempty list"]
    intervals = []
    for index, item in enumerate(versions):
        try:
            start = date.fromisoformat(item["version_start"])
            end = date.fromisoformat(item["version_end"]) if item.get("version_end") else None
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"classification {index} has invalid date interval: {exc}")
            continue
        if end and end < start:
            errors.append(f"classification {index} ends before it starts")
        intervals.append((start, end, item))
        expected = bool(item.get("presidential_authorization") or item.get("presidential_condition_precedent"))
        if item.get("classification") in {"delegation", "nondelegation"}:
            if (item["classification"] == "delegation") != expected:
                errors.append(f"classification {index} violates headline derivation rule")
            if not str(item.get("operative_excerpt", "")).strip():
                errors.append(f"classification {index} resolved without operative excerpt")
            if not item.get("official_sources"):
                errors.append(f"classification {index} resolved without official source")
    for observed in packet["observed_dates"]:
        target = date.fromisoformat(observed)
        matches = [item for start, end, item in intervals if start <= target and (end is None or target <= end)]
        if len(matches) != 1:
            errors.append(f"observed date {observed} is covered by {len(matches)} classifications")
    ordered = sorted(intervals, key=lambda value: value[0])
    for prior, current in zip(ordered, ordered[1:]):
        if prior[1] is None or current[0] <= prior[1]:
            errors.append("classification date intervals overlap")
    return (answer if not errors else None), errors


def command(answer_path: Path, model: str) -> list[str]:
    return [
        "codex", "exec", "--model", model,
        "-c", f'model_reasoning_effort="{REASONING_EFFORT}"',
        "--enable", "standalone_web_search",
        "--ephemeral", "--ignore-user-config", "--ignore-rules",
        "--sandbox", "read-only", "--skip-git-repo-check",
        "--output-schema", str(SCHEMA), "--output-last-message", str(answer_path),
        "--json", "-",
    ]


def packet_prompt(prefix: str, packet: dict) -> str:
    model_packet = dict(packet)
    if len(model_packet.get("observed_dates", [])) > 100:
        model_packet.pop("observed_dates")
        model_packet["date_list_compression_note"] = (
            "The complete occurrence-date list was compressed. Classify every controlling statutory "
            "version across OBSERVED_DATE_RANGE; OBSERVED_YEARS identifies years containing occurrences."
        )
    return prefix + "\n\nAUTHORITY_PACKET\n<authority_packet>\n" + json.dumps(model_packet, indent=2, ensure_ascii=False) + "\n</authority_packet>\n"


def terminal_successes(path: Path, prompt_hash: str) -> set[str]:
    return {
        row["canonical_authority_id"] for row in read_jsonl(path)
        if row.get("ok") and row.get("prompt_hash") == prompt_hash
    }


def load_inputs(args) -> tuple[list[dict], str, str, Path]:
    packets = read_jsonl(args.packets)
    if args.phase == "pilot":
        with args.pilot.open(newline="", encoding="utf-8") as handle:
            ids = {row["canonical_authority_id"] for row in csv.DictReader(handle)}
        packets = [row for row in packets if row["canonical_authority_id"] in ids]
        prompt = (HERE / "prompt_candidate.md").read_text(encoding="utf-8")
        output = OUTPUTS / "pilot_responses.jsonl"
    elif args.phase == "batch":
        # An explicitly requested exploratory run.  It deliberately uses the
        # unfrozen candidate prompt and writes to isolated artifacts, leaving
        # the blinded-pilot and frozen full-run gates intact.
        packets = sorted(packets, key=lambda row: (-row["occurrence_count"], row["canonical_authority_id"]))
        prompt = (HERE / "prompt_candidate.md").read_text(encoding="utf-8")
        output = OUTPUTS / f"batch_{args.model_tag}_responses.jsonl"
    else:
        if not args.frozen_prompt.exists():
            raise SystemExit("full/targeted execution requires outputs/frozen_prompt.json")
        artifact = json.loads(args.frozen_prompt.read_text(encoding="utf-8"))
        prompt = artifact["prompt"]
        output = OUTPUTS / ("full_responses.jsonl" if args.phase == "full" else "targeted_responses.jsonl")
        if args.phase == "targeted":
            primary = {row["canonical_authority_id"]: row for row in read_jsonl(OUTPUTS / "full_responses.jsonl") if row.get("ok")}
            target_ids = set()
            for authority_id, row in primary.items():
                classifications = row["answer"]["classifications"]
                if any(item["confidence"] == "low" or item["classification"] == "cannot_verify" for item in classifications):
                    target_ids.add(authority_id)
            packets = [row for row in packets if row["canonical_authority_id"] in target_ids]
    return packets, prompt, hashlib.sha256(prompt.encode()).hexdigest(), output


def run(args) -> None:
    packets, prefix, prompt_hash, response_path = load_inputs(args)
    if args.limit is not None:
        packets = packets[:args.limit]
    plan = {
        "phase": args.phase, "requests": len(packets), "model": args.model,
        "reasoning_effort": REASONING_EFFORT, "prompt_hash": prompt_hash,
        "output": str(response_path.relative_to(ROOT)),
    }
    if not args.execute:
        print(json.dumps({"DRY_RUN": True, **plan}, indent=2))
        return
    done = terminal_successes(response_path, prompt_hash)
    log_dir = OUTPUTS / "logs" / f"{args.phase}_{args.model_tag}"
    log_dir.mkdir(parents=True, exist_ok=True)
    status_path = OUTPUTS / f"{args.phase}_{args.model_tag}_status.json"
    for ordinal, packet in enumerate(packets, 1):
        authority_id = packet["canonical_authority_id"]
        if authority_id in done:
            continue
        prompt = packet_prompt(prefix, packet)
        request_hash = hashlib.sha256(prompt.encode()).hexdigest()
        final = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            safe = re_safe(authority_id)
            stem = f"{safe}.{prompt_hash[:10]}.attempt{attempt}"
            answer_path = log_dir / f"{stem}.answer.json"
            event_path = log_dir / f"{stem}.events.jsonl"
            stderr_path = log_dir / f"{stem}.stderr.txt"
            started = time.monotonic()
            with tempfile.TemporaryDirectory(prefix="presidential-delegation-") as empty_cwd:
                with event_path.open("w", encoding="utf-8") as events, stderr_path.open("w", encoding="utf-8") as stderr:
                    completed = subprocess.run(command(answer_path, args.model), input=prompt, text=True, stdout=events,
                                               stderr=stderr, cwd=empty_cwd, check=False)
            event_info = event_metadata(event_path)
            answer, errors = validate_answer(answer_path, packet)
            if completed.returncode:
                errors.append(f"codex exit code {completed.returncode}")
            if event_info["violations"]:
                errors.append(f"prohibited tool activity: {event_info['violations']}")
            final = {
                "canonical_authority_id": authority_id, "phase": args.phase, "attempt": attempt,
                "at": utc_now(), "model": args.model, "reasoning_effort": REASONING_EFFORT,
                "prompt_hash": prompt_hash, "request_hash": request_hash,
                "elapsed_seconds": time.monotonic() - started, "returncode": completed.returncode,
                "event_log": str(event_path.relative_to(ROOT)), "stderr_log": str(stderr_path.relative_to(ROOT)),
                "usage": event_info["usage"], "web_search_used": event_info["web_search_used"],
                "tool_violations": event_info["violations"], "validation_errors": errors,
                "ok": not errors, "answer": answer,
            }
            append_jsonl(OUTPUTS / f"{args.phase}_attempts.jsonl", final)
            if not errors:
                break
        append_jsonl(response_path, final)
        done = terminal_successes(response_path, prompt_hash)
        write_json(status_path, {**plan, "completed": len(done), "current": authority_id, "updated_at": utc_now()})
        print(json.dumps({"completed": len(done), "total": len(packets), "authority": authority_id, "ok": final["ok"]}), flush=True)
        if not final["ok"]:
            raise RuntimeError(f"{authority_id} failed after {MAX_ATTEMPTS} attempts")


def re_safe(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value)[:120]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, choices=("pilot", "batch", "full", "targeted"))
    parser.add_argument("--execute", action="store_true", help="required switch; permits model/network calls")
    parser.add_argument("--model", choices=("gpt-5.6-sol", "gpt-5.6-luna"), default=MODEL)
    parser.add_argument("--model-tag", choices=("sol", "luna"), help="isolates batch artifacts; defaults from --model")
    parser.add_argument("--limit", type=int, help="cap the selected batch size; useful for exploratory execution")
    parser.add_argument("--packets", type=Path, default=OUTPUTS / "authority_packets.jsonl")
    parser.add_argument("--pilot", type=Path, default=OUTPUTS / "pilot_human_gold.csv")
    parser.add_argument("--frozen-prompt", type=Path, default=OUTPUTS / "frozen_prompt.json")
    args = parser.parse_args()
    args.model_tag = args.model_tag or args.model.rsplit("-", 1)[-1]
    run(args)


if __name__ == "__main__":
    main()
