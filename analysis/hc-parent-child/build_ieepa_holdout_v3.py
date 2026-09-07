#!/usr/bin/env python3
"""Build a small disjoint holdout for the v3 IEEPA reporting-letter rule."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build import (
    DEFAULT_OUTPUT,
    assign_families,
    build_family_review,
    load_documents,
    read_csv,
    sha256,
    write_csv,
)


def ids(path: Path, field: str) -> set[str]:
    return {row[field] for row in read_csv(path)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT / "ieepa_holdout_v3")
    args = parser.parse_args()

    evidence = {
        "family_development": (
            DEFAULT_OUTPUT / "family_development" / "family_review_key.csv", "document_id"
        ),
        "family_holdout_v1": (
            DEFAULT_OUTPUT / "family_holdout" / "family_review_key.csv", "document_id"
        ),
        "family_parent_rule_development": (
            DEFAULT_OUTPUT / "family_parent_rule_development" / "parent_pair_review.csv", "child_id"
        ),
        "family_holdout_v2": (
            DEFAULT_OUTPUT / "family_holdout_v2" / "family_review_key.csv", "document_id"
        ),
    }
    excluded_by_source = {
        name: ids(path, field) for name, (path, field) in evidence.items()
    }
    excluded = set().union(*excluded_by_source.values())

    documents, source_audit = load_documents()
    assign_families(documents, {})
    all_families = build_family_review(
        documents,
        proposed_count=5,
        boundary_count=5,
        excluded_document_ids=excluded,
        sample_salt="ieepa_holdout_v3",
        review_id_prefix="H3",
    )
    queue = [row for row in all_families if row["family_id"] == "ieepa_action"]
    if len(queue) != 10:
        raise ValueError(f"expected 10 IEEPA holdout rows, found {len(queue)}")

    key = [
        {
            "review_id": row["review_id"],
            "family_id": row["family_id"],
            "document_id": row["document_id"],
            "queue_type": row["queue_type"],
        }
        for row in queue
    ]
    blinded = [
        {field: value for field, value in row.items() if field != "queue_type"}
        for row in queue
    ]
    args.output.mkdir(parents=True, exist_ok=True)
    write_csv(args.output / "family_review_queue.csv", blinded)
    write_csv(args.output / "family_review_key.csv", key)
    manifest = {
        "kind": "ieepa_reporting_rule_v3_holdout",
        "rows": len(queue),
        "proposed": 5,
        "boundary": 5,
        "excluded_documents_total": len(excluded),
        "excluded_documents_by_source": {
            name: len(values) for name, values in excluded_by_source.items()
        },
        "evidence_inputs": {
            name: sha256(path) for name, (path, _) in evidence.items()
        },
        "rule_inputs": {
            "build.py": sha256(Path(__file__).with_name("build.py")),
            "family_codebook.csv": sha256(Path(__file__).with_name("family_codebook.csv")),
        },
        "source_audit": source_audit,
    }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"rows": len(queue), "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
