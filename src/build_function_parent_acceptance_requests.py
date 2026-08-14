#!/usr/bin/env python3
"""Build Gemini top-pair candidate-or-none requests from frozen rankings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_gemini_function_rank_requests import compact
from validate_function_profiles import _read_jsonl

ROOT = Path(__file__).resolve().parents[1]
PROMPT_VERSION = "function-parent-accept-v3"

INSTRUCTION = """Judge whether the earlier candidate is a plausible drafting parent for the
later child. Put yourself in the position of the child's drafter: could the candidate have
provided a useful substantive precedent for drafting the child? The candidate was already
ranked best among a frozen pool, but being best available does not make it plausible.

A drafting parent may operate at any of three scopes:
1. Whole-document parent: it supplies much of the child's operative architecture.
2. Structural-framework parent: it supplies a domain-specific rule, amendment, delegation,
   exception, implementation, or institutional framework that the child adapts.
3. Material-provision parent: it supplies one or more concrete, substantive operative
   modules used within a broader child directive.
A candidate need not explain or template most of the child. A narrower candidate can parent
part of a broader child, and a broader candidate can parent a narrower child. Judge the
reusable portion directly; do not reject it merely because either document has substantial
unmatched provisions.

Identify concrete candidate-to-child mappings and ask whether a drafter could produce the
child provision by reusing the candidate's language, organization, legal mechanism,
institutional pathway, or sequence of actions with substitutions or localized edits. A
different target does not defeat a parent relationship. Nor does a different official,
date, country, product, personnel class, program, statutory source, scale, or ultimate
policy purpose when the operative machinery remains usefully parallel. Domain-specific
regulatory scaffolding can be substantive drafting architecture even when it is used for a
different policy task; do
not dismiss such scaffolding as generic merely because it is structural.

Strong evidence includes near-verbatim language; a distinctive parallel legal mechanism;
the same framework for amending related rules; or a coherent cluster such as delegation plus
exceptions, implementation, reporting, or review. Reversing, rescinding, narrowing,
expanding, or repurposing the candidate's policy does not itself defeat parenthood if the
child actually mirrors or adapts its operative machinery. Merely naming, implementing, or
repealing a policy created by the candidate, without such drafting reuse, is not enough.

Do not accept based only on generic topic, shared actors, the same broad statute, legal
boilerplate, ordinary executive-order form, isolated common verbs, or routine clauses such
as general agency cooperation, funding, reporting, or rulemaking. An isolated provision can
qualify only when it is a material and sufficiently distinctive drafting module, not an
incidental administrative clause. Require concrete reusable similarity, but do not require
the two directives to have the same overall policy objective or legal effect.

Calibrate the score as follows:
- 0.00-0.19: no concrete substantive or structural drafting reuse.
- 0.20-0.49: some concrete overlap, but it is incidental, routine, or too slight to make the
  candidate a plausible parent.
- 0.50-0.69: a plausible material-provision or structural-framework parent, even though much
  of the child was drafted independently.
- 0.70-0.89: strong reuse of a distinctive framework or multiple substantive provisions.
- 0.90-1.00: direct, extensive, or near-verbatim drafting reuse.

In the reason, identify the relationship scope, the concrete reusable mechanisms, and any
important limiting differences. List only function IDs that genuinely support those
mappings. Use the supplied profiles and, when useful, Google Search. Return JSON only:
{"best_candidate_id": string, "best_candidate_is_plausible": boolean,
 "plausibility_score": number 0..1, "reason": string,
 "matched_child_function_ids": [string], "matched_parent_function_ids": [string]}.
The boolean and score must agree: true requires score >= 0.5; false requires score < 0.5.
Never replace the supplied best_candidate_id."""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, default=ROOT / "data/parent_analysis/canonical_profiles")
    parser.add_argument("--profiles", type=Path)
    parser.add_argument("--documents", type=Path, default=ROOT / "data/parent_analysis_all_corpus/directive_similarity_documents.jsonl")
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
    if manifest.get("complete") is False:
        raise RuntimeError("canonical profile snapshot is incomplete")
    profile_path = args.profiles or args.snapshot_dir / "profiles.jsonl"
    profiles = {str(row["document_id"]): row for row in _read_jsonl(profile_path)}
    top = {str(row["child_id"]): row for row in _read_jsonl(args.rankings) if int(row["rank"]) == 1}
    wanted = set(top) | {str(row["parent_id"]) for row in top.values()}
    documents = {}
    source = args.documents
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
