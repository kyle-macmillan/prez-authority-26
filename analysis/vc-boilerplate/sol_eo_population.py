#!/usr/bin/env python3
"""Classify all nonceremonial generic-authority EO operative segments via local Codex CLI."""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import sol_subdirective_benchmark as benchmark

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUTPUTS = HERE / "outputs" / "sol_low_eo_population"
SEGMENTS = ROOT / "data/parent_analysis_all_corpus/directive_operative_segments.jsonl"
SCHEMA = HERE / "sol_eo_population.schema.json"
MODEL = benchmark.MODEL
REASONING_EFFORT = benchmark.REASONING_EFFORT
MAX_ATTEMPTS = 2
CALL_TIMEOUT_SECONDS = 90
DOCUMENT_TYPE = "executive_order"
DOCUMENT_LABEL = "EO"
DOCUMENT_LABEL_PLURAL = "EOs"
EXPECTED_TARGETS = 1016
EXPECTED_CALLS = 993
EXPECTED_NO_SEGMENTS = 23
EXPECTED_SEGMENTS = 5224

POPULATION_GUIDANCE = """Classify every item in OPERATIVE_SEGMENTS independently under the codebook. FULL_DIRECTIVE_CONTEXT may resolve references, but never assign the overall directive's posture to a segment.

For each segment:
1. Identify the actor, mandatory or discretionary action, object, and when the legal consequence occurs.
2. Code 3 only when that segment itself presently performs a substantive legally consequential act, such as a statutory determination or waiver, property block, entry suspension, eligibility or status designation, funding release, compensation entitlement, binding rate, or comparable consequence. Later ministerial implementation does not turn that present presidential act into Code 2.
3. Code 2 when the segment mandates an agency or official to impose a specified later legal consequence, such as funding or eligibility conditions, binding rules, sanctions, termination of assistance, or mandatory contract clauses. Use Code 2 for that posture even when written as an immediate amendment to an earlier executive order: the relevant consequence is still produced through later agency administration or contracts.
4. Code 1 covers internal executive organization and housekeeping: establishment and staffing of offices or advisory bodies, succession, delegation of presidential functions to officials, internal authority assignments, amendments or revocations of prior executive orders that reorganize administration, reporting, review, coordination, discretionary implementation, and authority to set something later without dictating its result. Do not call these Code 3 merely because the internal change takes effect immediately.
5. Code 0 covers ceremonial or hortatory appeals, messages or reports to Congress, recognition or veto communications, and text with no in-scope presidential governance or legal-rights relationship.
6. Use Code 4 sparingly, only where materially different postures are genuinely inseparable inside that segment or the posture cannot reliably be determined. Do not use it merely because a segment is long or contains several actions.

Return exactly one classification for every supplied segment_id, in the supplied order. Evidence must be one short passage from that segment. Do not classify text outside OPERATIVE_SEGMENTS."""


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def append_jsonl(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def frozen_prefix() -> tuple[str, str, list[str]]:
    dev, _, _ = benchmark.load_partitioned_records()
    examples = benchmark.example_rows(dev)
    prefix = benchmark.base_prompt(POPULATION_GUIDANCE, examples)
    return prefix, benchmark.sha256_text(prefix), [row["target_id"] for row in examples]


def target_eos() -> tuple[list[dict], list[dict]]:
    build = benchmark.load_build_module()
    sources = build.load_source_rows()
    target = [row for row in build.select_target(sources) if row["doc_type"] == DOCUMENT_TYPE]
    if len(target) != EXPECTED_TARGETS:
        raise ValueError(f"expected {EXPECTED_TARGETS:,} nonceremonial target {DOCUMENT_LABEL_PLURAL}, found {len(target)}")
    target_by_id = {str(row["ucsb_identifier"]): row for row in target}
    by_document = collections.defaultdict(list)
    with SEGMENTS.open(encoding="utf-8") as handle:
        for line in handle:
            segment = json.loads(line)
            document_id = str(segment["document_id"])
            if document_id in target_by_id:
                by_document[document_id].append(segment)
    requests, no_segments = [], []
    for document_id, source in sorted(target_by_id.items(), key=lambda item: int(item[0])):
        segments = sorted(by_document.get(document_id, []), key=lambda row: int(row["segment_index"]))
        if not segments:
            no_segments.append({
                "document_id": document_id, "url": source["url"], "date": source["date"],
                "president": source["president"], "source_file": source["source_file"],
                "reason": "no order_action segment in all-corpus deterministic segmentation",
            })
            continue
        requests.append({
            "document_id": document_id,
            "url": source["url"],
            "date": source["date"],
            "president": source["president"],
            "source_file": source["source_file"],
            "full_context": source["doc_text"],
            "segments": [{"segment_id": row["segment_id"], "segment_index": row["segment_index"],
                          "text": row["text"], "chunk_indices": row["chunk_indices"]} for row in segments],
        })
    if len(requests) != EXPECTED_CALLS or len(no_segments) != EXPECTED_NO_SEGMENTS:
        raise ValueError(f"expected {EXPECTED_CALLS:,} requests and {EXPECTED_NO_SEGMENTS:,} no-segment {DOCUMENT_LABEL_PLURAL}; got {len(requests)} and {len(no_segments)}")
    if sum(len(row["segments"]) for row in requests) != EXPECTED_SEGMENTS:
        raise ValueError(f"expected {EXPECTED_SEGMENTS:,} operative segments")
    return requests, no_segments


def prepare(_args) -> None:
    requests, no_segments = target_eos()
    prefix, prompt_hash, exemplar_ids = frozen_prefix()
    write_json(OUTPUTS / "requests.json", requests)
    write_json(OUTPUTS / "no_operative_segments.json", no_segments)
    write_json(OUTPUTS / "prompt_frozen.json", {
        "version": f"{DOCUMENT_TYPE}-population-v1", "frozen_at": benchmark.utc_now(), "prompt": prefix,
        "sha256": prompt_hash, "model": MODEL, "reasoning_effort": REASONING_EFFORT,
        "exemplar_target_ids": exemplar_ids,
    })
    write_json(OUTPUTS / "manifest.json", {
        "schema_version": 1, "prepared_at": benchmark.utc_now(), "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "invocation": f"one local codex exec call per {DOCUMENT_LABEL}; no direct OpenAI API integration",
        "authority_category": "generic_constitution_and_generic_statute",
        "document_type": DOCUMENT_TYPE, "ceremonial_excluded": True,
        "target_documents": EXPECTED_TARGETS, "called_documents": len(requests), "no_segment_documents": len(no_segments),
        "operative_segments": sum(len(row["segments"]) for row in requests),
        "segment_source": str(SEGMENTS.relative_to(ROOT)),
        "segment_source_sha256": hashlib.sha256(SEGMENTS.read_bytes()).hexdigest(),
        "prompt_sha256": prompt_hash, "max_attempts": MAX_ATTEMPTS,
    })
    print(f"Prepared {len(requests)} {DOCUMENT_LABEL} calls covering {EXPECTED_SEGMENTS:,} segments; {len(no_segments)} {DOCUMENT_LABEL_PLURAL} have no operative segment")


def render_prompt(prefix: str, request: dict) -> str:
    segment_payload = [{"segment_id": row["segment_id"], "text": row["text"]} for row in request["segments"]]
    return (
        prefix + "\n\nFULL_DIRECTIVE_CONTEXT\n<full_directive>\n" + request["full_context"]
        + "\n</full_directive>\n\nOPERATIVE_SEGMENTS\n"
        + json.dumps(segment_payload, ensure_ascii=False, indent=2) + "\n"
    )


def command(answer_path: Path) -> list[str]:
    return [
        "codex", "exec", "--model", MODEL,
        "-c", f'model_reasoning_effort="{REASONING_EFFORT}"',
        "--ephemeral", "--ignore-user-config", "--ignore-rules", "--sandbox", "read-only",
        "--skip-git-repo-check", "--output-schema", str(SCHEMA),
        "--output-last-message", str(answer_path), "--json", "-",
    ]


def parse_answer(path: Path, request: dict) -> tuple[dict | None, list[str]]:
    try:
        answer = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"invalid answer JSON: {exc}"]
    return parse_answer_from_value(answer, request)


def parse_answer_from_value(answer: object, request: dict) -> tuple[dict | None, list[str]]:
    errors = []
    items = answer.get("classifications") if isinstance(answer, dict) else None
    if not isinstance(items, list):
        return None, ["classifications is not an array"]
    expected = [row["segment_id"] for row in request["segments"]]
    actual = [row.get("segment_id") for row in items if isinstance(row, dict)]
    if actual != expected:
        errors.append(f"segment IDs/order mismatch: expected {expected}, got {actual}")
    text_by_id = {row["segment_id"]: row["text"] for row in request["segments"]}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"classification {index} is not an object")
            continue
        if set(item) != {"segment_id", "code", "rationale", "evidence"}:
            errors.append(f"classification {index} has unexpected keys")
        if not isinstance(item.get("code"), int) or item.get("code") not in range(5):
            errors.append(f"classification {index} has invalid code")
        if not isinstance(item.get("rationale"), str) or not item.get("rationale", "").strip():
            errors.append(f"classification {index} has invalid rationale")
        segment_id = item.get("segment_id")
        evidence = item.get("evidence")
        if segment_id in text_by_id and (not isinstance(evidence, str) or not benchmark.evidence_matches(evidence, text_by_id[segment_id])):
            errors.append(f"classification {index} evidence does not match segment {segment_id}")
    return (answer if not errors else None), errors


def completed_ids(response_path: Path, prompt_hash: str) -> set[str]:
    return {row["document_id"] for row in read_jsonl(response_path)
            if row.get("ok") and row.get("prompt_hash") == prompt_hash}


def response_progress(response_path: Path, prompt_hash: str) -> dict:
    latest = {}
    for row in read_jsonl(response_path):
        if row.get("prompt_hash") == prompt_hash:
            latest[row["document_id"]] = row
    successful = {document_id for document_id, row in latest.items() if row.get("ok")}
    failed = {document_id for document_id, row in latest.items() if not row.get("ok")}
    return {"processed": len(latest), "successful": len(successful), "failed": len(failed)}


def run(args) -> None:
    requests = json.loads((OUTPUTS / "requests.json").read_text(encoding="utf-8"))
    prompt = json.loads((OUTPUTS / "prompt_frozen.json").read_text(encoding="utf-8"))
    if args.smoke:
        requests = requests[:1]
    response_path = OUTPUTS / "responses.jsonl"
    attempts_path = OUTPUTS / "attempts.jsonl"
    log_dir = OUTPUTS / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    done = completed_ids(response_path, prompt["sha256"])
    total = len(json.loads((OUTPUTS / "requests.json").read_text()))
    for request in requests:
        document_id = request["document_id"]
        if document_id in done:
            continue
        full_prompt = render_prompt(prompt["prompt"], request)
        request_hash = benchmark.sha256_text(full_prompt)
        final = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            stem = f"{int(document_id):06d}.{prompt['sha256'][:10]}.attempt{attempt}"
            answer_path = log_dir / f"{stem}.answer.json"
            event_path = log_dir / f"{stem}.events.jsonl"
            stderr_path = log_dir / f"{stem}.stderr.txt"
            started = time.monotonic()
            timed_out = False
            with tempfile.TemporaryDirectory(prefix="sol-eo-population-") as empty_cwd:
                with event_path.open("w", encoding="utf-8") as events, stderr_path.open("w", encoding="utf-8") as stderr:
                    try:
                        completed = subprocess.run(command(answer_path), input=full_prompt, text=True, stdout=events,
                                                   stderr=stderr, cwd=empty_cwd, check=False,
                                                   timeout=CALL_TIMEOUT_SECONDS)
                        returncode = completed.returncode
                    except subprocess.TimeoutExpired:
                        timed_out = True
                        returncode = 124
            event_info = benchmark.event_metadata(event_path)
            answer, errors = parse_answer(answer_path, request)
            turn_completed = any(
                json.loads(line).get("type") == "turn.completed"
                for line in event_path.read_text(encoding="utf-8").splitlines() if line.strip()
            )
            salvaged_completed_answer = timed_out and turn_completed and answer is not None
            if returncode and not salvaged_completed_answer:
                errors.append(f"codex exit code {returncode}")
            if event_info["violations"]:
                errors.append(f"prohibited tool activity: {event_info['violations']}")
            final = {
                "document_id": document_id, "attempt": attempt, "at": benchmark.utc_now(),
                "model": MODEL, "reasoning_effort": REASONING_EFFORT,
                "prompt_hash": prompt["sha256"], "request_hash": request_hash,
                "segment_count": len(request["segments"]), "elapsed_seconds": time.monotonic() - started,
                "returncode": returncode, "timed_out": timed_out,
                "salvaged_completed_answer": salvaged_completed_answer,
                "usage": event_info["usage"],
                "web_search_used": event_info["web_search_used"],
                "event_log": str(event_path.relative_to(ROOT)), "stderr_log": str(stderr_path.relative_to(ROOT)),
                "tool_violations": event_info["violations"], "validation_errors": errors,
                "ok": not errors, "answer": answer,
            }
            append_jsonl(attempts_path, final)
            if not errors:
                break
        append_jsonl(response_path, final)
        progress = response_progress(response_path, prompt["sha256"])
        status_noun = DOCUMENT_LABEL_PLURAL.lower().replace(" ", "_")
        write_json(OUTPUTS / "status.json", {
            f"processed_{status_noun}": progress["processed"], f"successful_{status_noun}": progress["successful"],
            f"failed_{status_noun}": progress["failed"], f"total_called_{status_noun}": total,
            "current_document_id": document_id, "updated_at": benchmark.utc_now(),
            "prompt_hash": prompt["sha256"],
        })
        print(json.dumps({f"processed_{status_noun}": progress["processed"], f"successful_{status_noun}": progress["successful"],
                          f"failed_{status_noun}": progress["failed"], f"total_called_{status_noun}": total,
                          "document_id": document_id, "segments": len(request["segments"]),
                          "ok": final["ok"], "elapsed_seconds": round(final["elapsed_seconds"], 2)}), flush=True)


def evaluate(_args) -> None:
    requests = {row["document_id"]: row for row in json.loads((OUTPUTS / "requests.json").read_text())}
    prompt_hash = json.loads((OUTPUTS / "prompt_frozen.json").read_text())["sha256"]
    responses = {}
    for row in read_jsonl(OUTPUTS / "responses.jsonl"):
        if row.get("ok") and row.get("prompt_hash") == prompt_hash:
            responses[row["document_id"]] = row
    missing = sorted(set(requests) - set(responses), key=int)
    if missing:
        raise SystemExit(f"cannot evaluate: {len(missing)} {DOCUMENT_LABEL} responses missing")
    rows = []
    for document_id, request in requests.items():
        response = responses[document_id]
        by_id = {row["segment_id"]: row for row in response["answer"]["classifications"]}
        for segment in request["segments"]:
            prediction = by_id[segment["segment_id"]]
            rows.append({
                "document_id": document_id, "segment_id": segment["segment_id"],
                "segment_index": segment["segment_index"], "code": prediction["code"],
                "rationale": prediction["rationale"], "evidence": prediction["evidence"],
                "segment_text": segment["text"], "url": request["url"], "date": request["date"],
                "president": request["president"], "source_file": request["source_file"],
                "prompt_hash": prompt_hash,
            })
    write_json(OUTPUTS / "classifications.json", rows)
    fields = list(rows[0])
    with (OUTPUTS / "classifications.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    code_counts = collections.Counter(row["code"] for row in rows)
    report = {
        "target_documents": EXPECTED_TARGETS, "called_documents": len(requests), "no_segment_documents": EXPECTED_NO_SEGMENTS,
        "classified_segments": len(rows), "code_counts": {str(code): code_counts[code] for code in range(5)},
        "code_shares": {str(code): code_counts[code] / len(rows) for code in range(5)},
        "web_search_documents": sum(bool(row.get("web_search_used")) for row in responses.values()),
        "usage": {key: sum(int(row.get("usage", {}).get(key, 0)) for row in responses.values())
                  for key in ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens")},
        "latency_seconds": {"total": sum(row["elapsed_seconds"] for row in responses.values()),
                            "mean_per_document": sum(row["elapsed_seconds"] for row in responses.values()) / len(responses),
                            "max_per_document": max(row["elapsed_seconds"] for row in responses.values())},
    }
    write_json(OUTPUTS / "summary.json", report)
    lines = [f"# GPT-5.6 Sol / low generic-authority {DOCUMENT_LABEL} population", "",
             f"One local `codex exec` call classified all operative segments within each nonceremonial {DOCUMENT_LABEL}.", "",
             f"- Target {DOCUMENT_LABEL_PLURAL}: {report['target_documents']:,}", f"- {DOCUMENT_LABEL_PLURAL} classified: {report['called_documents']:,}",
             f"- {DOCUMENT_LABEL_PLURAL} without detected operative segments: {report['no_segment_documents']:,}",
             f"- Operative segments classified: {report['classified_segments']:,}", "",
             "| Code | Count | Share |", "|---:|---:|---:|"]
    for code in range(5):
        lines.append(f"| {code} | {code_counts[code]:,} | {code_counts[code]/len(rows):.1%} |")
    lines.append("")
    (OUTPUTS / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(report, indent=2))


def status(_args) -> None:
    path = OUTPUTS / "status.json"
    if path.exists():
        print(path.read_text().strip())
    else:
        print(json.dumps({"status": "not started"}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(required=True)
    sub.add_parser("prepare").set_defaults(func=prepare)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--smoke", action="store_true")
    run_parser.set_defaults(func=run)
    sub.add_parser("status").set_defaults(func=status)
    sub.add_parser("evaluate").set_defaults(func=evaluate)
    args = parser.parse_args(); args.func(args)


if __name__ == "__main__":
    main()
