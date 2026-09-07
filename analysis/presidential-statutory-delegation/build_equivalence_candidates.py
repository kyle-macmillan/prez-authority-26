#!/usr/bin/env python3
"""Build pairwise web-verification packets from unresolved crosswalk conflicts."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"


def main() -> None:
    packets = {json.loads(line)["canonical_authority_id"]: json.loads(line)
               for line in (OUTPUTS / "authority_packets.jsonl").read_text(encoding="utf-8").splitlines() if line}
    with (OUTPUTS / "global_equivalence_crosswalk.csv").open(newline="", encoding="utf-8") as handle:
        conflicts = [row for row in csv.DictReader(handle) if row["status"] == "conflict_requires_review"]
    rows, seen = [], set()
    for conflict in conflicts:
        left = conflict["source_authority_id"]
        for right in conflict["target_authority_id"].split(" | "):
            key = tuple(sorted((left, right)))
            if left == right or key in seen:
                continue
            seen.add(key)
            pair_id = "eq:" + hashlib.sha256("\0".join(key).encode()).hexdigest()[:12]
            rows.append({
                "pair_id": pair_id, "candidate_reason": "conflicting_explicit_bundle_targets",
                "left_authority_id": left, "right_authority_id": right,
                "left_packet": packets.get(left, {"canonical_authority_id": left}),
                "right_packet": packets.get(right, {"canonical_authority_id": right}),
            })
    path = OUTPUTS / "equivalence_candidate_packets.jsonl"
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(json.dumps({"candidate_pairs": len(rows), "output": str(path)}, indent=2))


if __name__ == "__main__":
    main()
