#!/usr/bin/env python3
"""Build a 20-case, category-blind holdout for HC-union membership."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build import (
    DEFAULT_OUTPUT,
    assign_families,
    balanced_sample,
    load_documents,
    load_profiles,
    read_csv,
    sha256,
    write_csv,
)


HERE = Path(__file__).resolve().parent


def ids(path: Path, *fields: str) -> set[str]:
    return {
        row[field]
        for row in read_csv(path)
        for field in fields
        if row.get(field)
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT / "hc_union_holdout")
    args = parser.parse_args()

    evidence = {
        "family_development": (
            DEFAULT_OUTPUT / "family_development" / "family_review_key.csv",
            ("document_id",),
        ),
        "family_holdout_v1": (
            DEFAULT_OUTPUT / "family_holdout" / "family_review_key.csv",
            ("document_id",),
        ),
        "family_holdout_v2": (
            DEFAULT_OUTPUT / "family_holdout_v2" / "family_review_key.csv",
            ("document_id",),
        ),
        "ieepa_holdout_v3": (
            DEFAULT_OUTPUT / "ieepa_holdout_v3" / "family_review_key.csv",
            ("document_id",),
        ),
        "family_parent_rule_development": (
            DEFAULT_OUTPUT / "family_parent_rule_development" / "parent_pair_review.csv",
            ("child_id", "parent_id"),
        ),
        "noncontrol_scope_screen": (
            DEFAULT_OUTPUT / "parent_pair_noncontrol_scope_screen.csv",
            ("child_id", "parent_id"),
        ),
    }
    excluded_by_source = {
        name: ids(path, *fields) for name, (path, fields) in evidence.items()
    }
    excluded = set().union(*excluded_by_source.values())

    documents, source_audit = load_documents()
    assign_families(documents, load_profiles())
    available = [
        row for row in documents
        if row["document_id"] not in excluded and not row["analysis_scope_reason"]
    ]
    proposed_pool = [row for row in available if row["families"]]
    boundary_pool = [
        row for row in available if not row["families"] and row["loose_families"]
    ]
    proposed = balanced_sample(
        proposed_pool, 10, ("president", "document_type"), "hc_union_holdout:proposed"
    )
    boundary = balanced_sample(
        boundary_pool, 10, ("president", "document_type"), "hc_union_holdout:boundary"
    )
    if len(proposed) != 10 or len(boundary) != 10:
        raise ValueError(
            f"expected 10 proposed and 10 boundary cases; got {len(proposed)} and {len(boundary)}"
        )

    queue, key = [], []
    for number, (queue_type, row) in enumerate(
        [("proposed", row) for row in proposed] + [("boundary", row) for row in boundary],
        start=1,
    ):
        review_id = f"U{number:02d}"
        queue.append({
            "review_id": review_id,
            "family_id": "hc_union",
            "document_id": row["document_id"],
            "president": row["president"],
            "date": row["date"],
            "document_type": row["document_type"],
            "title": row["title"],
            "url": row["url"],
            "non_vesting_text": row["primary_text"],
            "decision": "",
            "review_notes": "",
        })
        key.append({
            "review_id": review_id,
            "document_id": row["document_id"],
            "queue_type": queue_type,
            "matched_families": "|".join(row["families"]),
            "loose_families": "|".join(row["loose_families"]),
        })

    args.output.mkdir(parents=True, exist_ok=True)
    queue_path = args.output / "family_review_queue.csv"
    key_path = args.output / "family_review_key.csv"
    write_csv(queue_path, queue)
    write_csv(key_path, key)
    manifest = {
        "kind": "hc_union_category_blind_holdout",
        "rows": 20,
        "proposed": 10,
        "boundary": 10,
        "primary_estimand": "membership_in_any_high_confidence_category",
        "blinding": "sampling category and proposed/boundary status hidden",
        "excluded_documents_total": len(excluded),
        "excluded_documents_by_source": {
            name: len(values) for name, values in excluded_by_source.items()
        },
        "evidence_inputs": {
            name: sha256(path) for name, (path, _) in evidence.items()
        },
        "rule_inputs": {
            "build.py": sha256(HERE / "build.py"),
            "family_codebook.csv": sha256(HERE / "family_codebook.csv"),
        },
        "outputs": {
            queue_path.name: sha256(queue_path),
            key_path.name: sha256(key_path),
        },
        "source_audit": source_audit,
    }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"rows": len(queue), "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
