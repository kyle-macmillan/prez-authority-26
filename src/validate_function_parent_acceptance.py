#!/usr/bin/env python3
"""Validate Gemini top-pair acceptance responses into common decision records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from validate_gemini_function_rankings import parsed

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("responses", type=Path, nargs="+")
    parser.add_argument("--snapshot-dir", type=Path, default=ROOT / "data/parent_analysis/canonical_profiles")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--errors", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.snapshot_dir / "snapshot_manifest.json").read_text())
    latest = {}
    for path in args.responses:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                row = json.loads(line); latest[str(row.get("metadata", {}).get("child_id", ""))] = (path, line_number, row)
    valid, errors = [], []
    for child_id, (path, line_number, row) in sorted(latest.items(), key=lambda item: int(item[0])):
        try:
            metadata = row["metadata"]
            if metadata["snapshot_hash"] != manifest["snapshot_hash"]: raise ValueError("snapshot hash mismatch")
            result = parsed(row["text"])
            parent_id = str(result["best_candidate_id"])
            if parent_id != str(metadata["best_candidate_id"]): raise ValueError("best candidate changed")
            plausible = result["best_candidate_is_plausible"]
            if type(plausible) is not bool: raise ValueError("plausibility decision must be boolean")
            score = float(result["plausibility_score"])
            if not 0 <= score <= 1: raise ValueError("plausibility score outside 0..1")
            if plausible != (score >= .5): raise ValueError("boolean and score disagree")
            valid.append({"schema_version": 1, "child_id": child_id, "method": metadata["method"],
                          "best_candidate_id": parent_id, "ranking_score": float(metadata["ranking_score"]),
                          "decision": "candidate" if plausible else "none", "acceptance_score": score,
                          "score_semantics": "gemini_self_reported_plausibility_0_1",
                          "decision_source": "absolute_top_pair_judgment", "reason": str(result["reason"]),
                          "matches": {"child": result.get("matched_child_function_ids", []),
                                      "parent": result.get("matched_parent_function_ids", [])},
                          "model": row.get("model"), "model_version": row.get("model_version"),
                          "prompt_version": metadata.get("prompt_version", "function-parent-accept-v1"),
                          "snapshot_hash": manifest["snapshot_hash"]})
        except Exception as exc:
            errors.append({"file": str(path), "line": line_number, "request_id": row.get("request_id"),
                           "child_id": child_id, "error": str(exc)})
    for path, rows in ((args.output, valid), (args.errors, errors)):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for row in rows: handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"valid": len(valid), "invalid": len(errors), "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__": main()
