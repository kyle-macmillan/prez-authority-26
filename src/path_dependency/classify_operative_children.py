#!/usr/bin/env python3
"""Identify unresolved directives likely to contain Code 3 legal effects.

The model is used as an automated classifier, calibrated against the existing
three-rater Round 2 labels. Inference is resumable through a JSONL cache.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
PARENT_DIR = DATA / "parent_analysis"
OUTPUT_DIR = PARENT_DIR / "path_dependency_pilot" / "operative"
MODEL_ID = "Qwen/Qwen3-4B-Instruct-2507"
MODEL_REVISION = "cdbee75f17c01a7cc42f958dc650907174af0554"
MODEL_CACHE = ROOT / ".cache" / "huggingface"
SEED = 20260804
SAMPLE_SIZE = 50
MIN_PRECISION = 0.80

PROMPTS = (
    """Apply the supplied presidential-directive codebook to one provision.
Return only the single digit 0, 1, 2, 3, or 4.
0: outside governance scope.
1: discretionary executive direction or internal management.
2: requires an agency to create a specified legal consequence later.
3: this provision itself changes legal rights, duties, eligibility, status,
prohibitions, sanctions, funding availability, entry, asset control, land
designation, or another legal consequence without further agency action, or
is itself the legal condition precedent.
4: genuinely unclear or inseparably mixed.
The distinction is strict: mandatory agency implementation is Code 2, not 3.

Document type: {document_type}
Provision:
{text}

Code:""",
    """Classify the legal posture of this presidential-directive provision.
Answer with exactly one digit from 0 through 4.
Use 3 only where the President's provision is the operative legal act or legal
trigger. If an agency must later impose the consequence, use 2. Planning,
review, coordination, reporting, recommendations, and internal organization
are 1. Ceremonial or communicative material is 0. Use 4 sparingly for text that
cannot reliably be separated or resolved.

Type: {document_type}
Text:
{text}

Classification:""",
)
PROMPT_HASH = hashlib.sha256("\n---\n".join(PROMPTS).encode()).hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def load_rules_module():
    path = ROOT / "Authority Vagueness Analysis" / "vague_authority_self_executing_legal_effect.py"
    spec = importlib.util.spec_from_file_location("self_executing_rules", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def majority_round2_labels(annotation_dir: Path) -> dict[str, str]:
    """Return document ID -> majority Code 0-4 from the three existing raters."""
    mapping = {key: str(value) for key, value in json.loads(
        (annotation_dir / "doc_id_map_viewer.json").read_text()
    ).items()}
    paths = (
        annotation_dir / "7.16.2026 Tweil_annotations.json",
        annotation_dir / "annotations-viewer2-claire-2026-07-17.json",
        annotation_dir / "annotations-viewer2-kylem-2026-07-17.json",
    )
    exports = [json.loads(path.read_text()) for path in paths]
    output = {}
    for viewer_id, document_id in mapping.items():
        codes = [
            export.get(viewer_id, {}).get("classification", {}).get("code")
            for export in exports
        ]
        codes = [code for code in codes if code in {"0", "1", "2", "3", "4"}]
        if len(codes) < 2:
            continue
        counts = Counter(codes)
        code, count = counts.most_common(1)[0]
        if list(counts.values()).count(count) == 1:
            output[document_id] = code
    return output


def rule_predictions(corpus: dict[str, dict], document_ids: Iterable[str]) -> dict[str, dict]:
    rules = load_rules_module()
    output = {}
    for document_id in document_ids:
        row = corpus[document_id]
        category, rationale, evidence, excerpt = rules.classify_self_executing_legal_effect(
            row["doc_text"], row["doc_type"]
        )
        output[document_id] = {
            "rule_category": category,
            "rule_positive": category == "self_executing_legal_effect",
            "rule_rationale": rationale,
            "rule_evidence": evidence,
            "rule_excerpt": excerpt,
        }
    return output


def group_segments(rows: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[str(row["document_id"])].append(row)
    for values in grouped.values():
        values.sort(key=lambda row: int(row["segment_index"]))
    return grouped


def _probabilities(logits, token_ids: list[int]) -> list[float]:
    import torch
    selected = logits[token_ids].float()
    return torch.softmax(selected, dim=0).cpu().tolist()


def text_windows(text: str, size: int = 10_000, overlap: int = 500) -> list[str]:
    """Split very long provisions without silently discarding their ending."""
    if len(text) <= size:
        return [text]
    windows = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        windows.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return windows


class QwenCodeClassifier:
    def __init__(self, model_path: str, revision: str | None, batch_size: int = 1):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        if not torch.cuda.is_available():
            raise RuntimeError(
                "Automated Code 3 inference requires a CUDA GPU with at least 11 GB VRAM"
            )
        self.batch_size = batch_size
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_path, revision=revision, cache_dir=MODEL_CACHE, local_files_only=True,
        )
        self.tokenizer.padding_side = "left"
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token_id = self.tokenizer.eos_token_id
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path, revision=revision, torch_dtype=torch.float16,
            low_cpu_mem_usage=True, cache_dir=MODEL_CACHE, local_files_only=True,
        ).to("cuda").eval()
        self.revision = getattr(self.model.config, "_commit_hash", None) or revision or "unknown"
        self.code_token_ids = []
        for code in "01234":
            ids = self.tokenizer.encode(code, add_special_tokens=False)
            if len(ids) != 1:
                raise ValueError(f"Code {code!r} is not one tokenizer token: {ids}")
            self.code_token_ids.append(ids[0])

    def classify(self, items: list[dict]) -> list[dict]:
        """Classify provisions using both prompts; return one result per item."""
        output = [{"prompt_probabilities": []} for _ in items]
        for prompt_index, template in enumerate(PROMPTS):
            expanded = [
                (item_index, window)
                for item_index, item in enumerate(items)
                for window in text_windows(item["text"])
            ]
            prompts = [
                template.format(document_type=items[item_index]["document_type"], text=window)
                for item_index, window in expanded
            ]
            window_results: dict[int, list[list[float]]] = defaultdict(list)
            for start in range(0, len(prompts), self.batch_size):
                batch_prompts = prompts[start : start + self.batch_size]
                messages = [[{"role": "user", "content": prompt}] for prompt in batch_prompts]
                rendered = [
                    self.tokenizer.apply_chat_template(
                        message, tokenize=False, add_generation_prompt=True,
                        enable_thinking=False,
                    )
                    for message in messages
                ]
                encoded = self.tokenizer(
                    rendered, return_tensors="pt", padding=True, truncation=True,
                    max_length=4096,
                ).to("cuda")
                with self.torch.inference_mode():
                    logits = self.model(**encoded, use_cache=False).logits[:, -1, :]
                for offset, row_logits in enumerate(logits):
                    item_index = expanded[start + offset][0]
                    window_results[item_index].append(
                        _probabilities(row_logits, self.code_token_ids)
                    )
            for item_index in range(len(items)):
                output[item_index]["prompt_probabilities"].append(
                    max(window_results[item_index], key=lambda probabilities: probabilities[3])
                )
        for item, result in zip(items, output):
            predictions = [
                int(max(range(5), key=lambda code: probabilities[code]))
                for probabilities in result["prompt_probabilities"]
            ]
            result.update({
                "segment_id": item["segment_id"],
                "document_id": str(item["document_id"]),
                "predicted_codes": predictions,
                "dual_code3": predictions == [3, 3],
                "minimum_code3_probability": min(
                    probabilities[3] for probabilities in result["prompt_probabilities"]
                ),
                "maximum_code3_probability": max(
                    probabilities[3] for probabilities in result["prompt_probabilities"]
                ),
                "evidence": max(
                    text_windows(item["text"]),
                    key=lambda window: sum(
                        phrase in window.lower()
                        for phrase in ("hereby", "prohibited", "suspended", "blocked", "revoked")
                    ),
                )[:1200],
            })
        return output


def classify_documents(
    classifier: QwenCodeClassifier, document_ids: list[str],
    segments_by_document: dict[str, list[dict]], cache_path: Path,
) -> dict[str, dict]:
    """Classify all operative segments for requested documents with a resumable cache."""
    cached = {}
    if cache_path.exists():
        for row in load_jsonl(cache_path):
            if row.get("prompt_hash") == PROMPT_HASH and row.get("model_revision") == classifier.revision:
                cached[row["segment_id"]] = row
    wanted = [
        segment for document_id in document_ids
        for segment in segments_by_document.get(document_id, [])
    ]
    missing = [segment for segment in wanted if segment["segment_id"] not in cached]
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    for start in range(0, len(missing), classifier.batch_size):
        batch = missing[start : start + classifier.batch_size]
        results = classifier.classify(batch)
        with cache_path.open("a", encoding="utf-8") as handle:
            for result in results:
                result.update({
                    "model_id": MODEL_ID,
                    "model_revision": classifier.revision,
                    "prompt_hash": PROMPT_HASH,
                })
                handle.write(json.dumps(result, ensure_ascii=False) + "\n")
                cached[result["segment_id"]] = result
        done = min(start + len(batch), len(missing))
        if done % 100 == 0 or done == len(missing):
            print(f"classified {done}/{len(missing)} uncached provisions", flush=True)

    documents = {}
    for document_id in document_ids:
        results = [cached[row["segment_id"]] for row in segments_by_document.get(document_id, [])]
        dual = [row for row in results if row["dual_code3"]]
        best = max(
            dual or results,
            key=lambda row: (row["minimum_code3_probability"], row["segment_id"]),
            default=None,
        )
        documents[document_id] = {
            "model_code3": bool(dual),
            "minimum_code3_probability": (
                max(row["minimum_code3_probability"] for row in dual) if dual else 0.0
            ),
            "maximum_code3_probability": (
                max((row["maximum_code3_probability"] for row in results), default=0.0)
            ),
            "best_segment": best,
            "segment_predictions": results,
        }
    return documents


def policy_metrics(
    labels: dict[str, str], rules: dict[str, dict], models: dict[str, dict], policy: str,
) -> dict:
    def predicted(document_id: str) -> bool:
        rule = rules[document_id]["rule_positive"]
        model = models.get(document_id, {}).get("model_code3", False)
        return {"dual_model_plus_rule": model and rule, "dual_model": model, "rule": rule}[policy]

    tp = fp = fn = tn = 0
    for document_id, label in labels.items():
        actual = label == "3"
        guess = predicted(document_id)
        if actual and guess: tp += 1
        elif not actual and guess: fp += 1
        elif actual: fn += 1
        else: tn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {"policy": policy, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": precision, "recall": recall, "predicted_positive": tp + fp}


def choose_policy(metrics: list[dict], minimum_precision: float = MIN_PRECISION) -> dict:
    eligible = [row for row in metrics if row["precision"] >= minimum_precision]
    if eligible:
        return max(eligible, key=lambda row: (row["predicted_positive"], row["precision"]))
    return max(metrics, key=lambda row: (row["precision"], row["predicted_positive"]))


def rank_children(
    document_ids: Iterable[str], policy: str, rules: dict[str, dict], models: dict[str, dict],
) -> list[str]:
    eligible = []
    for document_id in document_ids:
        rule = rules[document_id]["rule_positive"]
        model = models.get(document_id, {}).get("model_code3", False)
        qualifies = {"dual_model_plus_rule": model and rule, "dual_model": model, "rule": rule}[policy]
        if qualifies:
            model_row = models.get(document_id, {})
            eligible.append((
                document_id,
                int(rule and model),
                model_row.get("minimum_code3_probability", 0.0),
                model_row.get("maximum_code3_probability", 0.0),
            ))
    eligible.sort(key=lambda row: (-row[1], -row[2], -row[3], int(row[0])))
    return [row[0] for row in eligible]


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=MODEL_ID)
    parser.add_argument("--revision", default=MODEL_REVISION)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--sample-size", type=int, default=SAMPLE_SIZE)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (DATA / "4_28_2026_build_dev.csv").open(newline="", encoding="utf-8-sig") as handle:
        corpus = {row[""]: row for row in csv.DictReader(handle)}
    with (PARENT_DIR / "unresolved_children.csv").open(newline="", encoding="utf-8") as handle:
        unresolved_rows = list(csv.DictReader(handle))
    unresolved = {row["document_id"]: row for row in unresolved_rows}
    holdout = {str(value) for value in json.loads((DATA / "holdout_ids.json").read_text())}
    with (PARENT_DIR / "pilot" / "sampled_children.csv").open(newline="", encoding="utf-8") as handle:
        original = {row["document_id"] for row in csv.DictReader(handle)}
    eligible_ids = sorted(set(unresolved) - holdout - original, key=int)

    segments = load_jsonl(PARENT_DIR / "directive_operative_segments.jsonl")
    segments_by_document = group_segments(segments)
    labels = majority_round2_labels(DATA / "Annotations" / "Sandbox 2")
    benchmark_ids = sorted(set(labels) & set(corpus), key=int)
    rules = rule_predictions(corpus, set(eligible_ids) | set(benchmark_ids))

    classifier = QwenCodeClassifier(args.model, args.revision, args.batch_size)
    cache = args.output_dir / "model_provision_predictions.jsonl"
    benchmark_models = classify_documents(
        classifier, benchmark_ids, segments_by_document, cache
    )
    metrics = [
        policy_metrics(labels, rules, benchmark_models, policy)
        for policy in ("dual_model_plus_rule", "dual_model", "rule")
    ]
    selected_policy = choose_policy(metrics)
    print("validation:", json.dumps(metrics, indent=2))
    print("selected policy:", selected_policy["policy"])

    if selected_policy["policy"] == "dual_model_plus_rule":
        inference_ids = [document_id for document_id in eligible_ids if rules[document_id]["rule_positive"]]
    elif selected_policy["policy"] == "dual_model":
        inference_ids = eligible_ids
    else:
        inference_ids = []
    corpus_models = classify_documents(classifier, inference_ids, segments_by_document, cache)
    ranked = rank_children(eligible_ids, selected_policy["policy"], rules, corpus_models)
    if len(ranked) < args.sample_size:
        raise RuntimeError(f"Only {len(ranked)} children qualify under {selected_policy['policy']}")
    sampled_ids = ranked[: args.sample_size]

    classifications = []
    for document_id in sampled_ids:
        model = corpus_models.get(document_id, {})
        best = model.get("best_segment")
        classifications.append({
            "document_id": document_id,
            "document_type": unresolved[document_id]["document_type"],
            "selected_policy": selected_policy["policy"],
            **rules[document_id],
            "model_code3": model.get("model_code3", False),
            "minimum_code3_probability": model.get("minimum_code3_probability", 0.0),
            "maximum_code3_probability": model.get("maximum_code3_probability", 0.0),
            "evidence_segment_id": best.get("segment_id") if best else "",
            "model_evidence": best.get("evidence") if best else rules[document_id]["rule_excerpt"],
            "predicted_codes": best.get("predicted_codes") if best else [],
            "model_rationale": (
                "Both codebook-grounded prompts classified this provision as Code 3: "
                "the provision itself is the asserted legal act or trigger."
                if model.get("model_code3") else ""
            ),
        })

    write_jsonl(args.output_dir / "selected_code3_classifications.jsonl", classifications)
    with (args.output_dir / "sampled_children.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(unresolved_rows[0]))
        writer.writeheader()
        writer.writerows(unresolved[document_id] for document_id in sampled_ids)
    validation = {
        "majority_labeled_documents": len(labels),
        "code3_documents": sum(code == "3" for code in labels.values()),
        "minimum_precision": MIN_PRECISION,
        "policies": metrics,
        "selected_policy": selected_policy,
    }
    (args.output_dir / "validation_report.json").write_text(
        json.dumps(validation, indent=2) + "\n"
    )
    manifest = {
        "seed": SEED,
        "sample_size": len(sampled_ids),
        "selection": "strongest automated Code 3 classifications; no manual confirmation",
        "selected_policy": selected_policy["policy"],
        "model_id": MODEL_ID,
        "model_revision": classifier.revision,
        "prompt_hash": PROMPT_HASH,
        "sample_counts_by_type": dict(Counter(unresolved[x]["document_type"] for x in sampled_ids)),
        "holdout_overlap": sorted(set(sampled_ids) & holdout),
        "original_pilot_overlap": sorted(set(sampled_ids) & original),
        "sampled_ids": sampled_ids,
    }
    (args.output_dir / "sample_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"selected {len(sampled_ids)} children in {args.output_dir}")


if __name__ == "__main__":
    main()
