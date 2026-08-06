"""Build the National Emergencies Act candidate-similarity HTML report."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from ieepa_candidate_similarity import ROOT, build_analysis, build_html

EMERGENCY_RE = re.compile(r"National Emergencies Act", re.I)


def is_emergency_authority(text: str) -> bool:
    return bool(EMERGENCY_RE.search(text))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "data/parent_analysis/emergency_similarity/emergency_candidate_similarity.html",
    )
    args = parser.parse_args()
    rows, summary = build_analysis(
        [ROOT / "data/4_28_2026_build_dev.csv", ROOT / "data/4_28_2026_build_holdout.csv"],
        ROOT / "data/parent_analysis/ranked_candidates.csv",
        ROOT / "data/parent_analysis/automatic_edges.csv",
        ROOT / "data/parent_analysis/directive_similarity_documents.jsonl",
        ROOT / "data/parent_analysis/directive_operative_segments.jsonl",
        matcher=is_emergency_authority,
        ceremonial_path=ROOT / "data/parent_analysis/ceremonial_exclusions.csv",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_html(
        rows, summary, topic="National Emergencies Act",
        definition="the full name “National Emergencies Act” (including uses that subsequently abbreviate it as “NEA”)",
    ), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(args.output)


if __name__ == "__main__":
    main()
