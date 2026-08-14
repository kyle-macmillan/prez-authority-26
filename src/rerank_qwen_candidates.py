"""Rerank RRF top-10 candidates with two Qwen3 reranker representations."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

MODEL_REVISION = "e61197ed45024b0ed8a2d74b80b4d909f1255473"
INSTRUCTION = (
    "Judge whether the earlier presidential directive is a likely drafting precedent for "
    "the later directive: it must address the same specific policy problem AND use a "
    "materially similar operative mechanism. Generic topic, actor, or boilerplate overlap "
    "alone is insufficient. Do not infer or compare legal authority."
)
PREFIX = ('<|im_start|>system\nJudge whether the Document meets the requirements based on '
          'the Query and the Instruct provided. Note that the answer can only be "yes" or '
          '"no".<|im_end|>\n<|im_start|>user\n')
SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"


def ordinal_ranks(scores: dict[str, float], prior: dict[str, int]) -> dict[str, int]:
    ordered = sorted(scores, key=lambda key: (-scores[key], prior[key], key))
    return {key: index for index, key in enumerate(ordered, 1)}


def bidirectional_matrix_mean(matrix: np.ndarray) -> float:
    return (float(np.mean(np.max(matrix, axis=1))) +
            float(np.mean(np.max(matrix, axis=0)))) / 2


def chunk_segments(segments: list[str], tokenizer, token_budget: int) -> list[str]:
    """Pack complete provisions, splitting only a provision larger than the budget."""
    pieces = []
    for index, text in enumerate(segments, 1):
        tokens = tokenizer.encode(f"[{index}] {text}", add_special_tokens=False)
        pieces.extend(tokenizer.decode(tokens[start:start + token_budget])
                      for start in range(0, len(tokens), token_budget))
    chunks, current, size = [], [], 0
    for piece in pieces:
        length = len(tokenizer.encode(piece, add_special_tokens=False))
        if current and size + length > token_budget:
            chunks.append("\n\n".join(current)); current, size = [], 0
        current.append(piece); size += length
    if current:
        chunks.append("\n\n".join(current))
    return chunks


class QwenReranker:
    def __init__(self, model_path: Path, max_length: int = 8192):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(
            str(model_path), padding_side="left", local_files_only=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            str(model_path), torch_dtype=torch.float16, local_files_only=True).cuda().eval()
        self.max_length = max_length
        self.prefix = self.tokenizer.encode(PREFIX, add_special_tokens=False)
        self.suffix = self.tokenizer.encode(SUFFIX, add_special_tokens=False)
        self.yes = self.tokenizer.convert_tokens_to_ids("yes")
        self.no = self.tokenizer.convert_tokens_to_ids("no")

    def score_many(self, pairs: list[tuple[str, str]], max_batch: int = 8,
                   token_budget: int = 12000, instruction: str | None = None) -> list[float]:
        encoded = []
        for query, document in pairs:
            text = f"<Instruct>: {instruction or INSTRUCTION}\n<Query>: {query}\n<Document>: {document}"
            item = self.tokenizer(
                text, padding=False, truncation="longest_first", return_attention_mask=False,
                max_length=self.max_length - len(self.prefix) - len(self.suffix))
            encoded.append(self.prefix + item["input_ids"] + self.suffix)
        scores, start = [], 0
        while start < len(encoded):
            end, total = start, 0
            while end < len(encoded) and end - start < max_batch:
                length = len(encoded[end])
                if end > start and total + length > token_budget:
                    break
                total += length; end += 1
            batch = self.tokenizer.pad(
                {"input_ids": encoded[start:end]}, padding=True, return_tensors="pt")
            batch = {key: value.cuda() for key, value in batch.items()}
            with self.torch.no_grad():
                logits = self.model(**batch, logits_to_keep=1).logits[:, -1, :]
                yes_no = self.torch.stack([logits[:, self.no], logits[:, self.yes]], dim=1)
                scores.extend(self.torch.softmax(yes_no.float(), dim=1)[:, 1].cpu().tolist())
            start = end
        return scores

    def score(self, query: str, document: str) -> float:
        return self.score_many([(query, document)], max_batch=1)[0]


def full_operative_score(child: list[str], parent: list[str], scorer: QwenReranker,
                         chunk_budget: int) -> tuple[float, int]:
    child_chunks = chunk_segments(child, scorer.tokenizer, chunk_budget)
    parent_chunks = chunk_segments(parent, scorer.tokenizer, chunk_budget)
    matrix = np.asarray([[scorer.score(c, p) for p in parent_chunks]
                         for c in child_chunks], dtype=np.float32)
    return bidirectional_matrix_mean(matrix), int(matrix.size)


def matched_pairs_score(child: list[str], parent: list[str], alignments: list,
                        scorer: QwenReranker, chunk_budget: int) -> tuple[float, int]:
    child_indices = sorted({int(item[0]) for item in alignments})
    parent_indices = sorted({int(item[1]) for item in alignments})
    return full_operative_score(
        [child[index] for index in child_indices],
        [parent[index] for index in parent_indices], scorer, chunk_budget,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=Path("data/parent_analysis"))
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--model-path", type=Path, default=Path(".cache/models/Qwen3-Reranker-0.6B"))
    parser.add_argument("--model-label", default="qwen3-reranker-0.6b")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child-id", action="append")
    parser.add_argument("--child-limit", type=int)
    parser.add_argument("--max-length", type=int, default=8192)
    parser.add_argument("--chunk-budget", type=int, default=3800)
    parser.add_argument("--matched-pair-limit", type=int, default=8)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    rows = []
    candidate_path = args.candidates or args.input_dir / "ranked_candidates.csv"
    with candidate_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    by_child = defaultdict(list)
    for row in rows:
        if row["selected_top_10"].lower() == "true":
            by_child[row["child_id"]].append(row)
    child_ids = sorted(by_child, key=int)
    if args.child_id:
        requested = set(args.child_id); child_ids = [item for item in child_ids if item in requested]
    if args.child_limit is not None:
        child_ids = child_ids[:args.child_limit]
    output = args.output or args.input_dir / "qwen_reranked_candidates.csv"
    completed = set()
    if args.resume and output.is_file():
        with output.open(newline="", encoding="utf-8") as handle:
            completed = {row["child_id"] for row in csv.DictReader(handle)}
        child_ids = [child_id for child_id in child_ids if child_id not in completed]
    segments = defaultdict(list)
    with (args.input_dir / "directive_operative_segments.jsonl").open(encoding="utf-8") as handle:
        for row in map(json.loads, handle):
            segments[row["document_id"]].append(row["text"])
    scorer = QwenReranker(args.model_path, args.max_length)
    output.parent.mkdir(parents=True, exist_ok=True)
    output_handle = output.open("a" if completed else "w", newline="", encoding="utf-8")
    writer = None
    result_count = 0
    for number, child_id in enumerate(child_ids, 1):
        child_rows = sorted(by_child[child_id], key=lambda row: int(row["rrf_rank"]))
        task_pairs, task_specs = [], []
        for row in child_rows:
            parent_id = row["parent_id"]
            alignments = json.loads(row["operative_alignments"])[:args.matched_pair_limit]
            representations = {
                "full": (segments[child_id], segments[parent_id]),
                "matched": (
                    [f"Match {number}: {segments[child_id][int(item[0])]}"
                     for number, item in enumerate(alignments, 1)],
                    [f"Match {number}: {segments[parent_id][int(item[1])]}"
                     for number, item in enumerate(alignments, 1)],
                ),
            }
            for mode, (child_texts, parent_texts) in representations.items():
                child_chunks = chunk_segments(child_texts, scorer.tokenizer, args.chunk_budget)
                parent_chunks = chunk_segments(parent_texts, scorer.tokenizer, args.chunk_budget)
                start = len(task_pairs)
                task_pairs.extend((child_chunk, parent_chunk) for child_chunk in child_chunks
                                  for parent_chunk in parent_chunks)
                task_specs.append((parent_id, mode, start, len(task_pairs),
                                   len(child_chunks), len(parent_chunks)))
        task_scores = scorer.score_many(task_pairs)
        full_scores, match_scores, calls = {}, {}, defaultdict(dict)
        for parent_id, mode, start, end, child_count, parent_count in task_specs:
            matrix = np.asarray(task_scores[start:end], dtype=np.float32).reshape(
                child_count, parent_count)
            score = bidirectional_matrix_mean(matrix)
            (full_scores if mode == "full" else match_scores)[parent_id] = score
            calls[parent_id][mode] = end - start
        prior = {row["parent_id"]: int(row["rrf_rank"]) for row in child_rows}
        full_ranks = ordinal_ranks(full_scores, prior); match_ranks = ordinal_ranks(match_scores, prior)
        for row in child_rows:
            parent_id = row["parent_id"]
            result = {**row, "qwen_full_operative_score": full_scores[parent_id],
                            "qwen_full_operative_rank": full_ranks[parent_id],
                            "qwen_full_model_calls": calls[parent_id]["full"],
                            "qwen_matched_pairs_score": match_scores[parent_id],
                            "qwen_matched_pairs_rank": match_ranks[parent_id],
                            "qwen_matched_pair_limit": args.matched_pair_limit,
                            "qwen_matched_model_calls": calls[parent_id]["matched"],
                            "reranker_model": args.model_label,
                            "reranker_instruction_version": "parent-reranker-v1"}
            if writer is None:
                writer = csv.DictWriter(output_handle, fieldnames=list(result))
                if not completed:
                    writer.writeheader()
            writer.writerow(result); result_count += 1
        output_handle.flush()
        print(f"reranked {number}/{len(child_ids)} children", flush=True)
    output_handle.close()
    print(f"{len(child_ids)} children processed; {result_count} pairs written; {output}")


if __name__ == "__main__":
    main()
