#!/usr/bin/env python3
"""Run standalone GPT-5.6 Sol/low web verification for citation pairs."""
from __future__ import annotations

import argparse, hashlib, json, subprocess, tempfile
from pathlib import Path

from run_gpt56 import append_jsonl, event_metadata, re_safe, utc_now

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUTPUTS = HERE / "outputs"
MODEL = "gpt-5.6-sol"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def validate(answer_path: Path, packet: dict) -> tuple[dict | None, list[str]]:
    try:
        answer = json.loads(answer_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, [f"invalid answer: {exc}"]
    errors = []
    for field in ("pair_id", "left_authority_id", "right_authority_id"):
        if answer.get(field) != packet[field]: errors.append(f"{field} mismatch")
    relationship = answer.get("relationship")
    if relationship == "equivalent" and answer.get("preferred_authority_id") not in {
        packet["left_authority_id"], packet["right_authority_id"]
    }: errors.append("equivalent result requires a preferred input authority")
    if relationship != "cannot_verify" and not answer.get("official_sources"):
        errors.append("resolved result requires an official source")
    return (answer if not errors else None), errors


def command(answer: Path) -> list[str]:
    return ["codex", "exec", "--model", MODEL, "-c", 'model_reasoning_effort="low"',
            "--enable", "standalone_web_search", "--ephemeral", "--ignore-user-config", "--ignore-rules",
            "--sandbox", "read-only", "--skip-git-repo-check", "--output-schema",
            str(HERE / "equivalence_response.schema.json"), "--output-last-message", str(answer), "--json", "-"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    packets = read_jsonl(OUTPUTS / "equivalence_candidate_packets.jsonl")
    if args.limit is not None: packets = packets[:args.limit]
    prompt = (HERE / "equivalence_prompt.md").read_text(encoding="utf-8")
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
    output = OUTPUTS / "equivalence_responses.jsonl"
    completed_rows = [row for row in read_jsonl(output)
                      if row.get("ok") and row.get("prompt_hash") == prompt_hash] if output.exists() else []
    completed_pairs = {frozenset((row["answer"]["left_authority_id"], row["answer"]["right_authority_id"]))
                       for row in completed_rows}
    selected_pairs = {frozenset((row["left_authority_id"], row["right_authority_id"])) for row in packets}
    if not args.execute:
        print(json.dumps({"dry_run": True, "requests": len(packets), "completed": len(completed_pairs & selected_pairs),
                          "model": MODEL, "reasoning_effort": "low", "web_search": True}, indent=2)); return
    logs = OUTPUTS / "logs" / "equivalence"; logs.mkdir(parents=True, exist_ok=True)
    for ordinal, packet in enumerate(packets, 1):
        if frozenset((packet["left_authority_id"], packet["right_authority_id"])) in completed_pairs:
            continue
        request = prompt + "\n\nPAIR_PACKET\n" + json.dumps(packet, indent=2, ensure_ascii=False)
        stem = re_safe(packet["pair_id"]); answer_path = logs / f"{stem}.answer.json"; events_path = logs / f"{stem}.events.jsonl"
        with tempfile.TemporaryDirectory(prefix="statutory-equivalence-") as cwd, events_path.open("w") as events:
            result = subprocess.run(command(answer_path), input=request, text=True, stdout=events,
                                    stderr=subprocess.PIPE, cwd=cwd, check=False)
        metadata = event_metadata(events_path); answer, errors = validate(answer_path, packet)
        if result.returncode: errors.append(f"codex exit code {result.returncode}")
        if metadata["violations"]: errors.append(f"prohibited tool activity: {metadata['violations']}")
        row = {"pair_id": packet["pair_id"], "ok": not errors, "answer": answer, "errors": errors,
               "model": MODEL, "reasoning_effort": "low", "prompt_hash": prompt_hash,
               "web_search_used": metadata["web_search_used"], "usage": metadata["usage"], "at": utc_now()}
        append_jsonl(output, row); print(json.dumps({"completed": ordinal, "total": len(packets), "pair": packet["pair_id"], "ok": not errors}), flush=True)
        if errors: raise RuntimeError(errors)


if __name__ == "__main__":
    main()
