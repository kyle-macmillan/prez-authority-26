#!/usr/bin/env python3
"""Build Gemini top-pair candidate-or-none requests from frozen rankings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_gemini_function_rank_requests import compact
from validate_function_profiles import _read_jsonl

ROOT = Path(__file__).resolve().parents[1]
PROMPT_VERSION = "function-parent-accept-v2"

INSTRUCTION = """Judge whether the earlier candidate is a plausible drafting parent for the
later child. Put yourself in the position of the child's drafter: would the candidate
provide a useful substantive template for drafting the child's operative provisions?
The candidate was already ranked best among a frozen pool, but being best available does
not make it a plausible parent. Consider together whether the directives perform the same
or a closely related governmental function; whether the candidate supplies reusable
operative language, organization, legal effects, or a sequence of actions; and whether
their differences could largely be handled by substituting targets, dates, officials,
countries, products, or other case-specific details.

A different target does not defeat a parent relationship. Operative mechanisms can be
reused across different targets and somewhat different policies. Near-verbatim or
structurally parallel substantive operative provisions are strong evidence that a drafter
could have used the candidate. Treat the target as a parameter when substituting it leaves
the directive's governmental function, operative structure, and legal effect substantially
unchanged. Treat it as substantive when the change produces a meaningfully different policy
task, mechanism, or legal effect.

Generic topic, actor, legal boilerplate, broad presidential form, or isolated common verbs
are insufficient. The reusable similarity must concern provisions that accomplish
substantive work. Ask how much of the candidate's substantive drafting architecture could
reasonably be reused after replacing case-specific details. Use the supplied profiles and,
when useful, Google Search. Return JSON only:
{"best_candidate_id": string, "best_candidate_is_plausible": boolean,
 "plausibility_score": number 0..1, "reason": string,
 "matched_child_function_ids": [string], "matched_parent_function_ids": [string]}.
The boolean and score must agree: true requires score >= 0.5; false requires score < 0.5.
Never replace the supplied best_candidate_id."""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, default=ROOT / "data/parent_analysis/function_parent_pilot/provisional")
    parser.add_argument("--rankings", type=Path, required=True)
    parser.add_argument("--method", required=True)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--last", type=int,
        help="Build requests for only the last N children in numeric child-ID order.",
    )
    args = parser.parse_args()
    manifest = json.loads((args.snapshot_dir / "snapshot_manifest.json").read_text())
    profiles = {str(row["document_id"]): row for row in _read_jsonl(args.snapshot_dir / "profiles.jsonl")}
    top = {str(row["child_id"]): row for row in _read_jsonl(args.rankings) if int(row["rank"]) == 1}
    wanted = set(top) | {str(row["parent_id"]) for row in top.values()}
    documents = {}
    source = ROOT / "data/parent_analysis_full/directive_similarity_documents.jsonl"
    with source.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line); document_id = str(row["document_id"])
            if document_id in wanted:
                documents[document_id] = {key: row.get(key, "") for key in ("document_id", "document_type", "title", "date", "url")}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(top.items(), key=lambda item: int(item[0]))
    if args.last is not None:
        if args.last < 1:
            parser.error("--last must be positive")
        ordered = ordered[-args.last:]
    with args.output.open("w", encoding="utf-8") as handle:
        for child_id, ranking in ordered:
            parent_id = str(ranking["parent_id"])
            payload = {
                "child": {**documents[child_id], "profile": compact(profiles[child_id])},
                "best_candidate": {**documents[parent_id], "profile": compact(profiles[parent_id])},
            }
            row = {
                "request_id": f"{PROMPT_VERSION}:{args.run_label}:{manifest['snapshot_hash'][:12]}:{child_id}",
                "contents": INSTRUCTION + "\n\nINPUT:\n" + json.dumps(payload, ensure_ascii=False),
                "metadata": {"child_id": child_id, "best_candidate_id": parent_id, "method": args.method,
                             "ranking_score": ranking["score"], "run_label": args.run_label,
                             "prompt_version": PROMPT_VERSION,
                             "snapshot_hash": manifest["snapshot_hash"]},
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"requests": len(ordered), "method": args.method, "output": str(args.output), "snapshot_hash": manifest["snapshot_hash"]}, sort_keys=True))


if __name__ == "__main__": main()
