#!/usr/bin/env python3
"""Ask local Qwen whether each frozen top candidate is plausible in absolute terms."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_gemini_function_rank_requests import compact
from function_profile_pilot import canonical_json
from rerank_qwen_candidates import QwenReranker
from validate_function_profiles import _read_jsonl

ROOT = Path(__file__).resolve().parents[1]
INSTRUCTION = (
    "Judge in absolute terms whether the earlier directive is a plausible parent for the later directive. "
    "It must address the same specific policy problem and use a materially similar operative mechanism. "
    "The earlier directive was merely the best available candidate; answer no if it only has generic topical, "
    "actor, presidential-form, or boilerplate similarity."
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, default=ROOT / "data/parent_analysis/function_parent_pilot/provisional")
    parser.add_argument("--rankings", type=Path)
    parser.add_argument("--model-path", type=Path, default=ROOT / ".cache/models/Qwen3-Reranker-0.6B")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-batch", type=int, default=4)
    args = parser.parse_args()
    rankings = args.rankings or args.snapshot_dir / "qwen_rankings.jsonl"
    output = args.output or args.snapshot_dir / "qwen_decisions.jsonl"
    manifest = json.loads((args.snapshot_dir / "snapshot_manifest.json").read_text())
    profiles = {str(row["document_id"]): row for row in _read_jsonl(args.snapshot_dir / "profiles.jsonl")}
    top = sorted((row for row in _read_jsonl(rankings) if int(row["rank"]) == 1), key=lambda row: int(row["child_id"]))
    pairs = [(canonical_json(compact(profiles[str(row["child_id"])])),
              canonical_json(compact(profiles[str(row["parent_id"])]))) for row in top]
    scorer = QwenReranker(args.model_path)
    scores = scorer.score_many(pairs, max_batch=args.max_batch, instruction=INSTRUCTION)
    with output.open("w", encoding="utf-8") as handle:
        for ranking, score in zip(top, scores, strict=True):
            row = {"schema_version": 1, "child_id": str(ranking["child_id"]), "method": "qwen",
                   "best_candidate_id": str(ranking["parent_id"]), "ranking_score": float(ranking["score"]),
                   "decision": "candidate" if score >= .5 else "none", "acceptance_score": float(score),
                   "score_semantics": "qwen_yes_softmax_probability",
                   "decision_source": "absolute_top_pair_judgment", "reason": "",
                   "matches": {}, "model": "Qwen3-Reranker-0.6B",
                   "prompt_version": "function-parent-accept-v1", "threshold": .5,
                   "snapshot_hash": manifest["snapshot_hash"]}
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"decisions": len(top), "output": str(output), "snapshot_hash": manifest["snapshot_hash"]}, sort_keys=True))


if __name__ == "__main__": main()
