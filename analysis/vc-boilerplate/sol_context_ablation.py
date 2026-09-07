#!/usr/bin/env python3
"""Run the frozen-v1 versus context-aware-v2 held-out prompt experiment."""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import json
import math
import random
import subprocess
import tempfile
import time
from pathlib import Path

import sol_subdirective_benchmark as benchmark


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUTPUTS = HERE / "outputs" / "sol_low_context_ablation"
SHUFFLE_SEED = 20260820
BOOTSTRAP_SEED = 20260820
BOOTSTRAP_REPETITIONS = 2000

CONTEXT_INSTRUCTION = """SEGMENTATION AND CONTEXT
The supplied sub-directives were created mechanically by splitting the directive around a predefined set of operative verbs and ordering phrases that signal presidential action. This procedure may produce fragments or segments whose actor, object, referent, condition, scope, or legal effect appears in surrounding text. Classify the action represented by each target as understood in the full directive context. Use relevant surrounding text to interpret the target, but do not classify surrounding actions or transfer the overall directive's posture to the target. Evidence must come from the target; the rationale and classification may rely on the full directive context."""


def prompt_artifacts() -> dict[str, dict]:
    original = json.loads(
        (benchmark.OUTPUTS / "validation_prompt_frozen.json").read_text(encoding="utf-8")
    )
    baseline = original["prompt"]
    marker = "\n\nFROZEN LABELED DEVELOPMENT EXAMPLES"
    if baseline.count(marker) != 1:
        raise ValueError("cannot locate the frozen-example boundary in the v1 prompt")
    context = baseline.replace(marker, "\n\n" + CONTEXT_INSTRUCTION + marker)
    common = {
        "model": benchmark.MODEL,
        "reasoning_effort": benchmark.REASONING_EFFORT,
        "exemplar_target_ids": original["exemplar_target_ids"],
    }
    return {
        "v1": {**common, "version": "fresh-frozen-v1", "prompt": baseline,
               "sha256": benchmark.sha256_text(baseline)},
        "v2": {**common, "version": "context-aware-v2", "prompt": context,
               "sha256": benchmark.sha256_text(context)},
    }


def paired_jobs(requests: list[dict]) -> list[dict]:
    jobs = [
        {"condition": condition, "target_id": row["target_id"]}
        for row in requests
        for condition in ("v1", "v2")
    ]
    random.Random(SHUFFLE_SEED).shuffle(jobs)
    return jobs


def prepare(_args) -> None:
    requests = json.loads(
        (benchmark.OUTPUTS / "validation_blind.json").read_text(encoding="utf-8")
    )
    source_manifest = json.loads(
        (benchmark.OUTPUTS / "manifest.json").read_text(encoding="utf-8")
    )
    prompts = prompt_artifacts()
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    benchmark.write_json(OUTPUTS / "requests.json", requests)
    benchmark.write_json(OUTPUTS / "jobs.json", paired_jobs(requests))
    for condition, artifact in prompts.items():
        benchmark.write_json(OUTPUTS / f"prompt_{condition}_frozen.json", {
            **artifact, "frozen_at": benchmark.utc_now(),
        })
    benchmark.write_json(OUTPUTS / "manifest.json", {
        "schema_version": 1,
        "prepared_at": benchmark.utc_now(),
        "experiment": "pre-specified context-instruction intervention",
        "evaluation_policy": (
            "Gold labels and target-level held-out outcomes are not loaded by prepare or run; "
            "evaluation occurs only after both conditions complete."
        ),
        "model": benchmark.MODEL,
        "reasoning_effort": benchmark.REASONING_EFFORT,
        "targets": len(requests),
        "calls": len(requests) * 2,
        "conditions": {key: value["sha256"] for key, value in prompts.items()},
        "shuffle_seed": SHUFFLE_SEED,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_repetitions": BOOTSTRAP_REPETITIONS,
        "max_attempts": benchmark.MAX_ATTEMPTS,
        "gold_source": str(benchmark.GOLD.relative_to(ROOT)),
        "gold_sha256": source_manifest["gold_sha256"],
        "gold_finalized_at": source_manifest.get("finalized_at"),
        "original_artifacts_untouched": True,
    })
    print(json.dumps({
        "targets": len(requests), "calls": len(requests) * 2,
        "v1": prompts["v1"]["sha256"], "v2": prompts["v2"]["sha256"],
    }, indent=2))


def successful_responses(condition: str, prompt_hash: str) -> dict[str, dict]:
    path = OUTPUTS / f"responses_{condition}.jsonl"
    return {
        row["target_id"]: row
        for row in benchmark.read_jsonl(path)
        if row.get("ok") and row.get("prompt_hash") == prompt_hash
    }


def command(answer_path: Path) -> list[str]:
    """Use the frozen benchmark command with optional app initialization disabled."""
    base = benchmark.command(answer_path)
    return base[:2] + ["--disable", "apps"] + base[2:]


def run(args) -> None:
    requests = {
        row["target_id"]: row
        for row in json.loads((OUTPUTS / "requests.json").read_text(encoding="utf-8"))
    }
    jobs = json.loads((OUTPUTS / "jobs.json").read_text(encoding="utf-8"))
    prompts = {
        condition: json.loads((OUTPUTS / f"prompt_{condition}_frozen.json").read_text(encoding="utf-8"))
        for condition in ("v1", "v2")
    }
    done = {
        condition: successful_responses(condition, prompts[condition]["sha256"])
        for condition in ("v1", "v2")
    }
    remaining = [job for job in jobs if job["target_id"] not in done[job["condition"]]]
    if args.limit is not None:
        remaining = remaining[:args.limit]
    for job in remaining:
        condition = job["condition"]
        row = requests[job["target_id"]]
        artifact = prompts[condition]
        prompt = benchmark.request_prompt(artifact["prompt"], row)
        request_hash = benchmark.sha256_text(prompt)
        final_record = None
        for attempt in range(1, benchmark.MAX_ATTEMPTS + 1):
            safe_id = row["target_id"].replace(":", "_")
            stem = f"{safe_id}.{artifact['sha256'][:10]}.attempt{attempt}"
            log_dir = OUTPUTS / "logs" / condition
            log_dir.mkdir(parents=True, exist_ok=True)
            answer_path = log_dir / f"{stem}.answer.json"
            event_path = log_dir / f"{stem}.events.jsonl"
            stderr_path = log_dir / f"{stem}.stderr.txt"
            started = time.monotonic()
            with tempfile.TemporaryDirectory(prefix=f"sol-context-{condition}-") as empty_cwd:
                with event_path.open("w", encoding="utf-8") as events, stderr_path.open("w", encoding="utf-8") as stderr:
                    completed = subprocess.run(
                        command(answer_path), input=prompt, text=True,
                        stdout=events, stderr=stderr, cwd=empty_cwd, check=False,
                    )
            elapsed = time.monotonic() - started
            event_info = benchmark.event_metadata(event_path)
            answer, errors = benchmark.parse_answer(answer_path, row["target_text"])
            if completed.returncode:
                errors.append(f"codex exit code {completed.returncode}")
            if event_info["violations"]:
                errors.append(f"tool activity detected: {event_info['violations']}")
            final_record = {
                "target_id": row["target_id"], "document_id": row["document_id"],
                "condition": condition, "attempt": attempt, "at": benchmark.utc_now(),
                "model": benchmark.MODEL, "reasoning_effort": benchmark.REASONING_EFFORT,
                "prompt_hash": artifact["sha256"], "request_hash": request_hash,
                "elapsed_seconds": elapsed, "returncode": completed.returncode,
                "event_log": str(event_path.relative_to(ROOT)),
                "stderr_log": str(stderr_path.relative_to(ROOT)),
                "usage": event_info["usage"], "web_search_used": event_info["web_search_used"],
                "tool_violations": event_info["violations"], "validation_errors": errors,
                "ok": not errors, "answer": answer,
            }
            benchmark.append_jsonl(OUTPUTS / f"attempts_{condition}.jsonl", final_record)
            if not errors:
                break
        benchmark.append_jsonl(OUTPUTS / f"responses_{condition}.jsonl", final_record)
        if not final_record["ok"]:
            raise RuntimeError(f"{condition}:{row['target_id']} failed after {benchmark.MAX_ATTEMPTS} attempts")
        done[condition][row["target_id"]] = final_record
        benchmark.write_json(OUTPUTS / "status.json", {
            "updated_at": benchmark.utc_now(),
            "v1_completed": len(done["v1"]), "v2_completed": len(done["v2"]),
            "total_per_condition": len(requests),
            "current": job,
        })
        print(json.dumps({
            **job, "v1_completed": len(done["v1"]), "v2_completed": len(done["v2"]),
            "elapsed_seconds": round(final_record["elapsed_seconds"], 2),
        }), flush=True)


def exact_mcnemar(b: int, c: int) -> dict:
    discordant = b + c
    if not discordant:
        return {"v1_only_correct": b, "v2_only_correct": c, "discordant": 0, "p_value": 1.0}
    tail = sum(math.comb(discordant, k) for k in range(0, min(b, c) + 1)) / (2 ** discordant)
    return {
        "v1_only_correct": b, "v2_only_correct": c, "discordant": discordant,
        "p_value": min(1.0, 2 * tail),
    }


def paired_clustered_intervals(rows: list[dict], repetitions: int = BOOTSTRAP_REPETITIONS) -> dict:
    grouped: dict[str, list[dict]] = collections.defaultdict(list)
    for row in rows:
        grouped[row["document_id"]].append(row)
    documents = sorted(grouped)
    rng = random.Random(BOOTSTRAP_SEED)
    accuracy_deltas, macro_f1_deltas = [], []
    for _ in range(repetitions):
        sample = [item for _doc in documents for item in grouped[rng.choice(documents)]]
        v1 = benchmark.metrics([{**row, "prediction": row["v1_prediction"]} for row in sample])
        v2 = benchmark.metrics([{**row, "prediction": row["v2_prediction"]} for row in sample])
        accuracy_deltas.append(v2["accuracy"] - v1["accuracy"])
        macro_f1_deltas.append(v2["macro_f1"] - v1["macro_f1"])
    def interval(values: list[float]) -> list[float]:
        values.sort()
        return [values[math.floor(.025 * (len(values) - 1))],
                values[math.floor(.975 * (len(values) - 1))]]
    return {"accuracy_delta_95ci": interval(accuracy_deltas),
            "macro_f1_delta_95ci": interval(macro_f1_deltas)}


def write_changed_csv(rows: list[dict]) -> None:
    fields = [
        "target_id", "document_id", "gold_code", "v1_prediction", "v2_prediction",
        "v1_correct", "v2_correct", "target_text", "v1_rationale", "v2_rationale",
        "v1_evidence", "v2_evidence",
    ]
    path = OUTPUTS / "changed_predictions.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{key: row[key] for key in fields} for row in rows])


def evaluate(_args) -> None:
    requests = {
        row["target_id"]: row
        for row in json.loads((OUTPUTS / "requests.json").read_text(encoding="utf-8"))
    }
    prompts = {
        condition: json.loads((OUTPUTS / f"prompt_{condition}_frozen.json").read_text(encoding="utf-8"))
        for condition in ("v1", "v2")
    }
    responses = {
        condition: successful_responses(condition, prompts[condition]["sha256"])
        for condition in ("v1", "v2")
    }
    missing = {condition: sorted(set(requests) - set(responses[condition])) for condition in ("v1", "v2")}
    if any(missing.values()):
        raise SystemExit(f"paired run incomplete: { {key: len(value) for key, value in missing.items()} }")
    gold = {
        row["target_id"]: row["gold_code"]
        for row in json.loads((benchmark.OUTPUTS / "validation_gold.json").read_text(encoding="utf-8"))
    }
    rows = []
    for target_id, request in requests.items():
        v1 = responses["v1"][target_id]["answer"]
        v2 = responses["v2"][target_id]["answer"]
        truth = gold[target_id]
        rows.append({
            "target_id": target_id, "document_id": request["document_id"], "gold_code": truth,
            "target_text": request["target_text"],
            "v1_prediction": v1["code"], "v2_prediction": v2["code"],
            "v1_correct": v1["code"] == truth, "v2_correct": v2["code"] == truth,
            "v1_rationale": v1["rationale"], "v2_rationale": v2["rationale"],
            "v1_evidence": v1["evidence"], "v2_evidence": v2["evidence"],
        })
    v1_metrics = benchmark.metrics([{**row, "prediction": row["v1_prediction"]} for row in rows])
    v2_metrics = benchmark.metrics([{**row, "prediction": row["v2_prediction"]} for row in rows])
    b = sum(row["v1_correct"] and not row["v2_correct"] for row in rows)
    c = sum(not row["v1_correct"] and row["v2_correct"] for row in rows)
    transitions = [[sum(row["v1_prediction"] == i and row["v2_prediction"] == j for row in rows)
                    for j in range(5)] for i in range(5)]
    original = {
        row["target_id"]: row["prediction"]
        for row in json.loads((benchmark.OUTPUTS / "validation_predictions.json").read_text(encoding="utf-8"))
    }
    original_agreement = sum(original[row["target_id"]] == row["v1_prediction"] for row in rows) / len(rows)
    changed = [row for row in rows if row["v1_prediction"] != row["v2_prediction"]]
    report = {
        "evaluated_at": benchmark.utc_now(), "targets": len(rows),
        "framing": (
            "Pre-specified context-instruction intervention on an existing held-out set; "
            "the change was motivated independently of target-level held-out error review."
        ),
        "prompt_hashes": {key: prompts[key]["sha256"] for key in prompts},
        "v1": v1_metrics, "v2": v2_metrics,
        "delta": {
            "accuracy": v2_metrics["accuracy"] - v1_metrics["accuracy"],
            "macro_f1": v2_metrics["macro_f1"] - v1_metrics["macro_f1"],
            **paired_clustered_intervals(rows),
        },
        "mcnemar_exact": exact_mcnemar(b, c),
        "prediction_transition_matrix_v1_rows_v2_columns": transitions,
        "changed_predictions": len(changed),
        "fresh_v1_vs_original_v1_agreement": original_agreement,
    }
    benchmark.write_json(OUTPUTS / "evaluation.json", report)
    benchmark.write_json(OUTPUTS / "paired_predictions.json", rows)
    benchmark.write_json(OUTPUTS / "changed_predictions.json", changed)
    write_changed_csv(changed)
    lines = [
        "# Context-aware prompt A/B evaluation", "",
        "This is a pre-specified context-instruction intervention on an existing held-out set. The prompt change was motivated independently of target-level held-out error review.", "",
        "## Paired results", "",
        "| Condition | Accuracy | Macro-F1 | Balanced accuracy | Codes 2/3 F1 |", "|---|---:|---:|---:|---:|",
        f"| Fresh frozen v1 | {v1_metrics['accuracy']:.1%} | {v1_metrics['macro_f1']:.3f} | {v1_metrics['balanced_accuracy']:.3f} | {v1_metrics['codes_2_or_3']['f1']:.3f} |",
        f"| Context-aware v2 | {v2_metrics['accuracy']:.1%} | {v2_metrics['macro_f1']:.3f} | {v2_metrics['balanced_accuracy']:.3f} | {v2_metrics['codes_2_or_3']['f1']:.3f} |", "",
        f"- Accuracy difference (v2 - v1): {report['delta']['accuracy']:+.1%}; document-clustered 95% CI {report['delta']['accuracy_delta_95ci'][0]:+.1%} to {report['delta']['accuracy_delta_95ci'][1]:+.1%}.",
        f"- Macro-F1 difference: {report['delta']['macro_f1']:+.3f}; document-clustered 95% CI {report['delta']['macro_f1_delta_95ci'][0]:+.3f} to {report['delta']['macro_f1_delta_95ci'][1]:+.3f}.",
        f"- McNemar discordant pairs: {b} v1-only correct and {c} v2-only correct; exact p={report['mcnemar_exact']['p_value']:.4f}.",
        f"- Changed predictions: {len(changed)}/{len(rows)}.",
        f"- Fresh-v1 agreement with the stored original v1 run: {original_agreement:.1%}.", "",
        "A wholly untouched confirmation set is required before treating any further outcome-informed prompt revision as confirmatory.", "",
    ]
    (OUTPUTS / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(report, indent=2))


def status(_args) -> None:
    path = OUTPUTS / "status.json"
    print(path.read_text(encoding="utf-8").strip() if path.exists() else json.dumps({"status": "not started"}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(required=True)
    sub.add_parser("prepare").set_defaults(func=prepare)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--limit", type=int)
    run_parser.set_defaults(func=run)
    sub.add_parser("status").set_defaults(func=status)
    sub.add_parser("evaluate").set_defaults(func=evaluate)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
