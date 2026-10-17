#!/usr/bin/env python3
"""Build the Round 3 annotation-comparison viewer with agreement statistics."""

from __future__ import annotations

from pathlib import Path

from build_annotation_comparison import build_html, extract_source_data
from build_round3_disagreement_review import ROUND3_DIR, SOURCE_VIEWER, load_results


OUTPUT = ROUND3_DIR / "annotation-comparison.html"
CONFIG = {
    "label": "Round 3",
    "schema": "round2",
    "fields": {
        "directive": ("code", "diplomacy", "military_ops"),
        "chunk": ("code", "diplomacy", "military_ops"),
    },
    "field_labels": {
        "code": "Code",
        "diplomacy": "Diplomacy / recognition",
        "military_ops": "Military / intel ops",
    },
    "value_labels": {
        "0": "0 - Outside scope",
        "1": "1 - Discretionary executive direction / internal management",
        "2": "2 - Dictated agency legal outcome",
        "3": "3 - Self-executing legal effect",
        "4": "4 - Unclear / inseparable mixed",
        "yes": "Yes",
        "no": "No",
    },
    "field_options": {
        "code": ("0", "1", "2", "3", "4"),
        "diplomacy": ("yes", "no"),
        "military_ops": ("yes", "no"),
    },
    "chunk_strategy": "wp",
}


def main() -> None:
    metadata, chunks, doc_texts = extract_source_data(
        SOURCE_VIEWER.read_text(), CONFIG["chunk_strategy"]
    )
    html = build_html(metadata, chunks, doc_texts, load_results(), CONFIG)
    OUTPUT.write_text(html)
    print(f"Wrote {OUTPUT.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()
