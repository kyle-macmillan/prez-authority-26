#!/usr/bin/env python3
"""Compile valid web-verification answers into an auditable crosswalk file."""
from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"


def main() -> None:
    responses = OUTPUTS / "equivalence_responses.jsonl"
    answers = {}
    if responses.exists():
        for line in responses.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("ok") and row.get("answer"):
                answers[row["pair_id"]] = row["answer"]
    rows = []
    for pair_id, answer in sorted(answers.items()):
        rows.append({
            "pair_id": pair_id, "left_authority_id": answer["left_authority_id"],
            "right_authority_id": answer["right_authority_id"], "relationship": answer["relationship"],
            "preferred_authority_id": answer.get("preferred_authority_id") or "",
            "rationale": answer["rationale"],
            "official_sources": " | ".join(answer.get("official_sources", [])),
        })
    output = OUTPUTS / "verified_equivalence_crosswalk.csv"
    fields = ("pair_id", "left_authority_id", "right_authority_id", "relationship",
              "preferred_authority_id", "rationale", "official_sources")
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    print(json.dumps({"responses": len(rows), "equivalent": sum(r["relationship"] == "equivalent" for r in rows),
                      "output": str(output)}, indent=2))


if __name__ == "__main__":
    main()
