#!/usr/bin/env python3
"""Run the isolated GPT-5.6 Sol/low operative-subdirective benchmark via Codex CLI."""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import hashlib
import json
import math
import os
import random
import re
import subprocess
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUTPUTS = HERE / "outputs" / "sol_low_subdirectives"
GOLD = ROOT / "data/Annotations/Round 2/round-2-finalized-validation-labels-with-subdirectives.json"
SCHEMA = HERE / "sol_subdirective.schema.json"
MODEL = "gpt-5.6-sol"
REASONING_EFFORT = "low"
MAX_ATTEMPTS = 2
FORBIDDEN_EVENT_TYPES = ("command_execution", "mcp", "file_search", "computer", "apply_patch", "image_generation")

CODEBOOK = """Operative sub-directive codes
0 - Outside scope: not presidential governance over agencies or legal rights.
1 - Discretionary executive direction / internal management: organizes, reviews, coordinates, studies, prioritizes, or directs discretionary implementation.
2 - Dictated agency legal outcome: requires an agency or official to produce a specified legally consequential result later.
3 - Self-executing legal effect: the provision itself changes legal rights, duties, eligibility, status, sanctions, funding, entry, land designation, or another legal consequence.
4 - Unclear / inseparable mixed: cannot be reliably classified or combines postures that cannot reasonably be separated."""

DRAFT_GUIDANCE = """Classify only TARGET_SUBDIRECTIVE, using FULL_DIRECTIVE_CONTEXT only to resolve references or understand what the target does.
Choose the legal posture of the target, not its policy topic. Distinguish a present legal consequence caused by the presidential text itself (3) from a mandatory command for an agency to create a specified legal consequence later (2), and both from internal or discretionary administration (1). Use 0 for ceremonial, hortatory, communicative, or otherwise out-of-scope text. Use 4 only when the target truly cannot be separated into one posture."""

# Frozen identities chosen before held-out evaluation. Text and labels are loaded from GOLD.
EXEMPLARS = (
    ("19275", "2", "A hortatory appeal to the public does not govern an agency or change legal rights."),
    ("338", "2", "Establishing an office within the Executive Office is internal executive organization."),
    ("3306", "1", "Agencies must impose specified conditions and enforcement obligations that create later legal consequences."),
    ("10067", "2", "The President directly waives a statutory provision, producing the legal effect in the target itself."),
    ("3841", "1", "Office closure, employee excusal, and statutory-holiday treatment are inseparably combined."),
)

# This constant is deliberately frozen only after the single development pass.
FINAL_GUIDANCE = """Classify only TARGET_SUBDIRECTIVE. FULL_DIRECTIVE_CONTEXT may resolve references, but do not assign the overall directive's posture to the target.

Apply this order of analysis:
1. Identify the actor, mandatory or discretionary action, object, and when the legal consequence occurs.
2. Code 3 only when the target itself presently performs a substantive legally consequential act, such as a statutory determination or waiver, property block, entry suspension, eligibility or status designation, funding release, compensation entitlement, binding rate, or comparable consequence. Later ministerial implementation does not turn that present presidential act into Code 2.
3. Code 2 when the operative posture is a mandate that an agency or official impose a specified later legal consequence, such as funding or eligibility conditions, binding rules, sanctions, termination of assistance, or mandatory contract clauses. Use Code 2 for that posture even when the target is written as an immediate amendment to an earlier executive order: the relevant consequence is still produced through later agency administration or contracts.
4. Code 1 covers internal executive organization and housekeeping: establishment and staffing of offices or advisory bodies, succession, delegation of presidential functions to officials, internal authority assignments, amendments or revocations of prior executive orders that reorganize administration, reporting, review, coordination, discretionary implementation, and authority to set something later without dictating its result. Do not call these Code 3 merely because the internal change takes effect immediately.
5. Code 0 covers ceremonial or hortatory appeals (including ceremonial flag-display directions), messages or reports to Congress, recognition or veto communications, and text with no in-scope presidential governance or legal-rights relationship. These remain outside scope even if they have constitutional significance.
6. Use Code 4 sparingly, only where materially different postures are genuinely inseparable in the target or the posture cannot reliably be determined. Do not use it merely because a target is long or contains several actions.

Return one code for the whole target exactly as segmented in TARGET_SUBDIRECTIVE. Evidence must be one short, contiguous, verbatim passage from that target (whitespace differences are acceptable). Do not join quotations, paraphrase, or use ellipses in evidence."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def evidence_matches(evidence: str, target_text: str) -> bool:
    """Accept a verbatim span despite case, whitespace, or quote-adjacent punctuation style."""
    if normalize(evidence).lower() in normalize(target_text).lower():
        return True
    evidence_words = re.findall(r"[\w]+(?:['’-][\w]+)*", evidence.casefold())
    target_words = re.findall(r"[\w]+(?:['’-][\w]+)*", target_text.casefold())
    if not evidence_words:
        return False
    width = len(evidence_words)
    if any(target_words[index:index + width] == evidence_words for index in range(len(target_words) - width + 1)):
        return True
    # Legal quotations commonly omit an embedded citation parenthetical. Permit only
    # that bounded omission, while preserving the exact surrounding word sequence.
    without_parentheticals = re.sub(r"\([^()]*\)", " ", target_text)
    parenthetical_words = re.findall(r"[\w]+(?:['’-][\w]+)*", without_parentheticals.casefold())
    if any(parenthetical_words[index:index + width] == evidence_words
           for index in range(len(parenthetical_words) - width + 1)):
        return True
    # Also permit an acronym only when the target explicitly defines it immediately
    # after an expansion whose significant-word initials match that acronym.
    stopwords = {"and", "of", "the", "for", "in", "on", "to"}
    for acronym_match in re.finditer(r"\(([A-Z][A-Z0-9]{1,9})\)", target_text):
        acronym = acronym_match.group(1)
        prior_words = list(re.finditer(r"\b[A-Za-z][A-Za-z-]*\b", target_text[:acronym_match.start()]))[-12:]
        for start in range(len(prior_words)):
            candidate = prior_words[start:]
            initials = "".join(word.group(0)[0] for word in candidate
                               if word.group(0).casefold() not in stopwords).upper()
            if initials != acronym:
                continue
            collapsed = (target_text[:candidate[0].start()] + acronym
                         + target_text[acronym_match.end():])
            collapsed_words = re.findall(r"[\w]+(?:['’-][\w]+)*", collapsed.casefold())
            if any(collapsed_words[index:index + width] == evidence_words
                   for index in range(len(collapsed_words) - width + 1)):
                return True
    return False


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


def load_build_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("vc_boilerplate_build_for_sol", HERE / "build.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def source_rows() -> dict[str, dict]:
    rows = {}
    for path in (ROOT / "data/4_28_2026_build_dev.csv", ROOT / "data/4_28_2026_build_holdout.csv"):
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                rows[str(row[""])] = row
    return rows


def load_partitioned_records() -> tuple[list[dict], list[dict], dict]:
    payload = json.loads(GOLD.read_text(encoding="utf-8"))
    build = load_build_module()
    dev_docs, validation_docs = build.build_split(build.load_gold())
    dev_ids = {str(row["global_dev_id"]) for row in dev_docs}
    validation_ids = {str(row["global_dev_id"]) for row in validation_docs}
    corpus = source_rows()
    records = []
    for row in payload["subdirective_records"]:
        document_id = str(row["global_dev_id"])
        target = row["text"]
        context = corpus[document_id]["doc_text"]
        if normalize(target) not in normalize(context):
            raise ValueError(f"target does not align after whitespace normalization: {document_id}:{row['chunk_number']}")
        records.append({
            "target_id": f"{document_id}:{int(row['chunk_number']):03d}",
            "document_id": document_id,
            "chunk_number": int(row["chunk_number"]),
            "round_id": row["round_id"],
            "target_text": target,
            "full_context": context,
            "gold_code": int(row["labels"]["code"]),
            "partition": "dev" if document_id in dev_ids else "validation",
        })
    if {row["document_id"] for row in records} - (dev_ids | validation_ids):
        raise ValueError("a subdirective document is outside the frozen split")
    dev = [row for row in records if row["partition"] == "dev"]
    validation = [row for row in records if row["partition"] == "validation"]
    if len(dev) != 91 or len(validation) != 198:
        raise ValueError(f"unexpected split sizes: {len(dev)} development, {len(validation)} validation")
    return dev, validation, payload


def example_rows(dev: list[dict]) -> list[dict]:
    by_key = {(row["document_id"], str(row["chunk_number"])): row for row in dev}
    rows = []
    for document_id, chunk_number, explanation in EXEMPLARS:
        row = by_key[(document_id, chunk_number)]
        rows.append({"code": row["gold_code"], "target": row["target_text"], "explanation": explanation,
                     "target_id": row["target_id"]})
    if [row["code"] for row in rows] != list(range(5)):
        raise ValueError("the five frozen exemplars must be ordered Code 0 through Code 4")
    return rows


def base_prompt(guidance: str, examples: list[dict] | None = None) -> str:
    parts = [
        "You are classifying one presidential operative sub-directive under a fixed legal-posture codebook.",
        CODEBOOK,
        guidance,
    ]
    if examples:
        rendered = []
        for example in examples:
            rendered.append(
                f"EXAMPLE CODE {example['code']}\nTARGET: {normalize(example['target'])}\nWHY: {example['explanation']}"
            )
        parts.append("FROZEN LABELED DEVELOPMENT EXAMPLES\n\n" + "\n\n".join(rendered))
    parts.append(
        "You may use built-in web search when it is useful to resolve incorporated legal text, "
        "the effect of a cited authority, or another genuine legal ambiguity. Do not use shell, "
        "filesystem, MCP, computer-use, or other tools. Base the classification and quoted evidence "
        "on TARGET_SUBDIRECTIVE, not on outside commentary. "
        "Return JSON matching the required schema. The evidence field must contain exactly one "
        "short, contiguous, verbatim passage from TARGET_SUBDIRECTIVE; do not join quotations, "
        "paraphrase, add quotation marks, or use ellipses."
    )
    return "\n\n".join(parts)


def request_prompt(prefix: str, row: dict) -> str:
    return (
        prefix
        + "\n\nFULL_DIRECTIVE_CONTEXT\n<full_directive>\n"
        + row["full_context"]
        + "\n</full_directive>\n\nTARGET_SUBDIRECTIVE\n<target_subdirective>\n"
        + row["target_text"]
        + "\n</target_subdirective>\n"
    )


def prepare(_args) -> None:
    dev, validation, payload = load_partitioned_records()
    examples = example_rows(dev)
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    for partition, rows in (("dev", dev), ("validation", validation)):
        blind = [{key: row[key] for key in ("target_id", "document_id", "chunk_number", "round_id", "target_text", "full_context", "partition")} for row in rows]
        gold = [{"target_id": row["target_id"], "document_id": row["document_id"], "gold_code": row["gold_code"]} for row in rows]
        write_json(OUTPUTS / f"{partition}_blind.json", blind)
        write_json(OUTPUTS / f"{partition}_gold.json", gold)
    draft = base_prompt(DRAFT_GUIDANCE)
    write_json(OUTPUTS / "draft_prompt.json", {"version": "draft-v1", "prompt": draft, "sha256": sha256_text(draft)})
    write_json(OUTPUTS / "frozen_exemplars.json", examples)
    write_json(OUTPUTS / "manifest.json", {
        "schema_version": 1,
        "prepared_at": utc_now(),
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "invocation": "local Codex CLI (codex exec); no direct OpenAI API integration",
        "gold_source": str(GOLD.relative_to(ROOT)),
        "gold_sha256": hashlib.sha256(GOLD.read_bytes()).hexdigest(),
        "finalized_at": payload.get("finalized_at"),
        "development_targets": len(dev),
        "validation_targets": len(validation),
        "development_documents": len({row["document_id"] for row in dev}),
        "validation_documents": len({row["document_id"] for row in validation}),
        "development_code_counts": collections.Counter(row["gold_code"] for row in dev),
        "validation_code_counts": collections.Counter(row["gold_code"] for row in validation),
        "max_attempts": MAX_ATTEMPTS,
    })
    print(f"Prepared {len(dev)} development and {len(validation)} validation targets in {OUTPUTS}")


def freeze(_args) -> None:
    dev = json.loads((OUTPUTS / "dev_blind.json").read_text(encoding="utf-8"))
    gold = {row["target_id"]: row["gold_code"] for row in json.loads((OUTPUTS / "dev_gold.json").read_text(encoding="utf-8"))}
    for row in dev:
        row["gold_code"] = gold[row["target_id"]]
    examples = example_rows(dev)
    prompt = base_prompt(FINAL_GUIDANCE, examples)
    artifact = {
        "version": "validation-frozen-v1",
        "frozen_at": utc_now(),
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "prompt": prompt,
        "sha256": sha256_text(prompt),
        "exemplar_target_ids": [row["target_id"] for row in examples],
    }
    write_json(OUTPUTS / "validation_prompt_frozen.json", artifact)
    print(json.dumps({key: artifact[key] for key in ("version", "sha256", "exemplar_target_ids")}, indent=2))


def nested_types(value):
    if isinstance(value, dict):
        if isinstance(value.get("type"), str):
            yield value["type"]
        for child in value.values():
            yield from nested_types(child)
    elif isinstance(value, list):
        for child in value:
            yield from nested_types(child)


def event_audit(path: Path) -> list[str]:
    return event_metadata(path)["violations"]


def event_metadata(path: Path) -> dict:
    violations = set()
    web_search_used = False
    usage = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        kinds = list(nested_types(event))
        for kind in kinds:
            if any(flag in kind.lower() for flag in FORBIDDEN_EVENT_TYPES):
                violations.add(kind)
            if "web_search" in kind.lower():
                web_search_used = True
        if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            usage = event["usage"]
    return {"violations": sorted(violations), "web_search_used": web_search_used, "usage": usage}


def parse_answer(path: Path, target_text: str) -> tuple[dict | None, list[str]]:
    errors = []
    try:
        answer = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"invalid answer JSON: {exc}"]
    if set(answer) != {"code", "rationale", "evidence"}:
        errors.append("answer keys do not exactly match code/rationale/evidence")
    if not isinstance(answer.get("code"), int) or answer.get("code") not in range(5):
        errors.append("code is not an integer from 0 through 4")
    for field in ("rationale", "evidence"):
        if not isinstance(answer.get(field), str) or not answer.get(field, "").strip():
            errors.append(f"{field} is empty or not a string")
    if isinstance(answer.get("evidence"), str) and not evidence_matches(answer["evidence"], target_text):
        errors.append("evidence is not a contiguous target passage after text normalization")
    return (answer if not errors else None), errors


def command(answer_path: Path) -> list[str]:
    return [
        "codex", "exec", "--model", MODEL,
        "-c", f'model_reasoning_effort="{REASONING_EFFORT}"',
        "--ephemeral", "--ignore-user-config", "--ignore-rules",
        "--sandbox", "read-only", "--skip-git-repo-check",
        "--output-schema", str(SCHEMA), "--output-last-message", str(answer_path),
        "--json", "-",
    ]


def terminal_successes(path: Path, prompt_hash: str) -> set[str]:
    return {row["target_id"] for row in read_jsonl(path) if row.get("ok") and row.get("prompt_hash") == prompt_hash}


def run_partition(args) -> None:
    partition = args.partition
    request_path = OUTPUTS / f"{partition}_blind.json"
    response_path = OUTPUTS / f"{partition}_responses.jsonl"
    if partition == "dev":
        prompt_artifact = json.loads((OUTPUTS / "draft_prompt.json").read_text(encoding="utf-8"))
    else:
        frozen = OUTPUTS / "validation_prompt_frozen.json"
        if not frozen.exists():
            raise SystemExit("validation prompt is not frozen; run freeze-validation after development review")
        prompt_artifact = json.loads(frozen.read_text(encoding="utf-8"))
    rows = json.loads(request_path.read_text(encoding="utf-8"))
    if args.smoke:
        rows = rows[:1]
    prefix, prompt_hash = prompt_artifact["prompt"], prompt_artifact["sha256"]
    done = terminal_successes(response_path, prompt_hash)
    status_path = OUTPUTS / f"{partition}_status.json"
    log_dir = OUTPUTS / "logs" / partition
    log_dir.mkdir(parents=True, exist_ok=True)
    for ordinal, row in enumerate(rows, 1):
        if row["target_id"] in done:
            continue
        prompt = request_prompt(prefix, row)
        request_hash = sha256_text(prompt)
        final_record = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            safe_id = row["target_id"].replace(":", "_")
            stem = f"{safe_id}.{prompt_hash[:10]}.attempt{attempt}"
            answer_path = log_dir / f"{stem}.answer.json"
            event_path = log_dir / f"{stem}.events.jsonl"
            stderr_path = log_dir / f"{stem}.stderr.txt"
            started = time.monotonic()
            with tempfile.TemporaryDirectory(prefix="sol-subdirective-") as empty_cwd:
                with event_path.open("w", encoding="utf-8") as events, stderr_path.open("w", encoding="utf-8") as stderr:
                    completed = subprocess.run(command(answer_path), input=prompt, text=True, stdout=events,
                                               stderr=stderr, cwd=empty_cwd, check=False)
            elapsed = time.monotonic() - started
            event_info = event_metadata(event_path)
            violations = event_info["violations"]
            answer, errors = parse_answer(answer_path, row["target_text"])
            if completed.returncode:
                errors.append(f"codex exit code {completed.returncode}")
            if violations:
                errors.append(f"tool activity detected: {violations}")
            attempt_record = {
                "target_id": row["target_id"], "document_id": row["document_id"],
                "partition": partition, "attempt": attempt, "at": utc_now(),
                "model": MODEL, "reasoning_effort": REASONING_EFFORT,
                "prompt_hash": prompt_hash, "request_hash": request_hash,
                "elapsed_seconds": elapsed, "returncode": completed.returncode,
                "event_log": str(event_path.relative_to(ROOT)),
                "stderr_log": str(stderr_path.relative_to(ROOT)),
                "usage": event_info["usage"], "web_search_used": event_info["web_search_used"],
                "tool_violations": violations, "validation_errors": errors,
                "ok": not errors, "answer": answer,
            }
            append_jsonl(OUTPUTS / f"{partition}_attempts.jsonl", attempt_record)
            if not errors:
                final_record = attempt_record
                break
            final_record = attempt_record
        append_jsonl(response_path, final_record)
        completed_count = len(terminal_successes(response_path, prompt_hash))
        write_json(status_path, {"partition": partition, "completed": completed_count,
                                "total": len(json.loads(request_path.read_text())),
                                "current": row["target_id"], "updated_at": utc_now(),
                                "prompt_hash": prompt_hash})
        print(json.dumps({"partition": partition, "completed": completed_count,
                          "target_id": row["target_id"], "ok": final_record["ok"],
                          "elapsed_seconds": round(final_record["elapsed_seconds"], 2)}), flush=True)
        if not final_record["ok"]:
            raise RuntimeError(f"{row['target_id']} failed after {MAX_ATTEMPTS} attempts")


def metrics(rows: list[dict]) -> dict:
    labels = range(5)
    matrix = [[sum(row["gold_code"] == i and row["prediction"] == j for row in rows) for j in labels] for i in labels]
    per_class, recalls, f1s = [], [], []
    for code in labels:
        tp = matrix[code][code]
        support = sum(matrix[code])
        predicted = sum(line[code] for line in matrix)
        precision = tp / predicted if predicted else 0.0
        recall = tp / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class.append({"code": code, "support": support, "predicted": predicted,
                          "precision": precision, "recall": recall, "f1": f1})
        if support:
            recalls.append(recall)
            f1s.append(f1)
    n = len(rows)
    accuracy = sum(row["gold_code"] == row["prediction"] for row in rows) / n
    consequential_gold = [row["gold_code"] in (2, 3) for row in rows]
    consequential_pred = [row["prediction"] in (2, 3) for row in rows]
    tp = sum(g and p for g, p in zip(consequential_gold, consequential_pred))
    fp = sum(not g and p for g, p in zip(consequential_gold, consequential_pred))
    fn = sum(g and not p for g, p in zip(consequential_gold, consequential_pred))
    cp = tp / (tp + fp) if tp + fp else 0.0
    cr = tp / (tp + fn) if tp + fn else 0.0
    return {"n": n, "accuracy": accuracy, "balanced_accuracy": sum(recalls) / len(recalls),
            "macro_f1": sum(f1s) / len(f1s),
            "weighted_f1": sum(item["f1"] * item["support"] for item in per_class) / n,
            "confusion_matrix": matrix, "per_class": per_class,
            "codes_2_or_3": {"precision": cp, "recall": cr,
                              "f1": 2 * cp * cr / (cp + cr) if cp + cr else 0.0,
                              "support": sum(consequential_gold)}}


def clustered_interval(rows: list[dict], field: str, repetitions: int = 2000) -> list[float]:
    grouped = collections.defaultdict(list)
    for row in rows:
        grouped[row["document_id"]].append(row)
    documents = sorted(grouped)
    rng = random.Random(20260819)
    values = []
    for _ in range(repetitions):
        sample = [item for _key in documents for item in grouped[rng.choice(documents)]]
        values.append(metrics(sample)[field])
    values.sort()
    return [values[math.floor(0.025 * (repetitions - 1))], values[math.floor(0.975 * (repetitions - 1))]]


def evaluate_partition(partition: str) -> dict:
    gold = {row["target_id"]: row for row in json.loads((OUTPUTS / f"{partition}_gold.json").read_text())}
    blind = {row["target_id"]: row for row in json.loads((OUTPUTS / f"{partition}_blind.json").read_text())}
    prompt_file = "draft_prompt.json" if partition == "dev" else "validation_prompt_frozen.json"
    prompt_hash = json.loads((OUTPUTS / prompt_file).read_text())["sha256"]
    valid = {}
    elapsed, usages, web_searches = {}, {}, {}
    for response in read_jsonl(OUTPUTS / f"{partition}_responses.jsonl"):
        if response.get("ok") and response.get("prompt_hash") == prompt_hash:
            valid[response["target_id"]] = response["answer"]
            elapsed[response["target_id"]] = response["elapsed_seconds"]
            event_path = ROOT / response["event_log"]
            event_info = event_metadata(event_path)
            usages[response["target_id"]] = response.get("usage") or event_info["usage"]
            web_searches[response["target_id"]] = response.get("web_search_used", event_info["web_search_used"])
    missing = sorted(set(gold) - set(valid))
    if missing:
        raise SystemExit(f"cannot evaluate {partition}; {len(missing)} valid predictions missing")
    build = load_build_module()
    rows = []
    for target_id, truth in gold.items():
        answer = valid[target_id]
        text_baseline = int(build.classify_text(blind[target_id]["target_text"])["predicted_code"])
        rows.append({**truth, "prediction": answer["code"], "rationale": answer["rationale"],
                     "evidence": answer["evidence"], "text_rule_prediction": text_baseline,
                     "elapsed_seconds": elapsed[target_id]})
    model_metrics = metrics(rows)
    model_metrics["clustered_accuracy_95ci"] = clustered_interval(rows, "accuracy")
    model_metrics["clustered_macro_f1_95ci"] = clustered_interval(rows, "macro_f1")
    majority_code = collections.Counter(row["gold_code"] for row in rows).most_common(1)[0][0]
    report = {
        "partition": partition, "model": MODEL, "reasoning_effort": REASONING_EFFORT,
        "prompt_hash": prompt_hash, "model_metrics": model_metrics,
        "majority_baseline": metrics([{**row, "prediction": majority_code} for row in rows]),
        "text_rule_diagnostic": metrics([{**row, "prediction": row["text_rule_prediction"]} for row in rows]),
        "latency_seconds": {"total": sum(elapsed.values()), "mean": sum(elapsed.values()) / len(elapsed),
                            "median": sorted(elapsed.values())[len(elapsed) // 2], "max": max(elapsed.values())},
        "usage": {key: sum(int(value.get(key, 0)) for value in usages.values())
                  for key in ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens")},
        "web_search_targets": sum(web_searches.values()),
    }
    write_json(OUTPUTS / f"{partition}_evaluation.json", report)
    write_json(OUTPUTS / f"{partition}_predictions.json", rows)
    write_json(OUTPUTS / f"{partition}_errors.json", [row for row in rows if row["gold_code"] != row["prediction"]])
    return report


def render_report(dev: dict, validation: dict) -> str:
    m = validation["model_metrics"]
    lines = [
        "# GPT-5.6 Sol / low sub-directive benchmark",
        "",
        "Calls were made through the locally installed `codex exec` CLI, one ephemeral process per target; no OpenAI API client was used.",
        "",
        "## Held-out validation",
        "",
        f"- Accuracy: **{m['accuracy']:.1%}** ({round(m['accuracy'] * m['n'])}/{m['n']}); document-clustered 95% CI {m['clustered_accuracy_95ci'][0]:.1%}–{m['clustered_accuracy_95ci'][1]:.1%}.",
        f"- Macro-F1: **{m['macro_f1']:.3f}**; balanced accuracy: **{m['balanced_accuracy']:.3f}**.",
        f"- Codes 2/3 combined precision: **{m['codes_2_or_3']['precision']:.1%}**; recall: **{m['codes_2_or_3']['recall']:.1%}**; F1: **{m['codes_2_or_3']['f1']:.3f}**.",
        f"- Majority baseline accuracy: {validation['majority_baseline']['accuracy']:.1%}.",
        f"- Current text-rule chunk diagnostic accuracy: {validation['text_rule_diagnostic']['accuracy']:.1%} (the rules were designed for whole directives).",
        "",
        "| Code | Support | Precision | Recall | F1 |",
        "|---:|---:|---:|---:|---:|",
    ]
    for row in m["per_class"]:
        lines.append(f"| {row['code']} | {row['support']} | {row['precision']:.3f} | {row['recall']:.3f} | {row['f1']:.3f} |")
    lines += [
        "", "## Prompt-development diagnostic", "",
        f"The single example-free development pass scored {dev['model_metrics']['accuracy']:.1%} accuracy and {dev['model_metrics']['macro_f1']:.3f} macro-F1. It was used only to revise and freeze the validation prompt.",
        "", "See `validation_predictions.json`, `validation_errors.json`, and `validation_evaluation.json` for complete results.", "",
    ]
    return "\n".join(lines)


def evaluate(_args) -> None:
    dev = evaluate_partition("dev")
    validation = evaluate_partition("validation")
    (OUTPUTS / "REPORT.md").write_text(render_report(dev, validation), encoding="utf-8")
    print(json.dumps(validation["model_metrics"], indent=2))


def evaluate_dev(_args) -> None:
    print(json.dumps(evaluate_partition("dev"), indent=2))


def status(_args) -> None:
    for partition in ("dev", "validation"):
        path = OUTPUTS / f"{partition}_status.json"
        print(path.read_text().strip() if path.exists() else json.dumps({"partition": partition, "status": "not started"}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(required=True)
    sub.add_parser("prepare").set_defaults(func=prepare)
    sub.add_parser("freeze-validation").set_defaults(func=freeze)
    for name, partition in (("run-dev", "dev"), ("run-validation", "validation")):
        run_parser = sub.add_parser(name)
        run_parser.add_argument("--smoke", action="store_true")
        run_parser.set_defaults(func=run_partition, partition=partition)
    sub.add_parser("status").set_defaults(func=status)
    sub.add_parser("evaluate-dev").set_defaults(func=evaluate_dev)
    sub.add_parser("evaluate").set_defaults(func=evaluate)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
