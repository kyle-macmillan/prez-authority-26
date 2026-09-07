#!/usr/bin/env python3
"""Build two replacements for explicit-link cases in the final HC-union holdout."""

from __future__ import annotations

import json
from pathlib import Path

from build import (
    AUTOMATIC_EDGES,
    DEFAULT_OUTPUT,
    assign_families,
    balanced_sample,
    explicit_parent_child_ids,
    load_documents,
    load_profiles,
    read_csv,
    sha256,
    write_csv,
)


HERE = Path(__file__).resolve().parent
OUTPUT = DEFAULT_OUTPUT / "hc_union_holdout_v2_replacements"


def ids(path: Path, *fields: str) -> set[str]:
    return {
        row[field] for row in read_csv(path) for field in fields if row.get(field)
    }


def main() -> None:
    evidence = {
        "family_development": (DEFAULT_OUTPUT / "family_development/family_review_key.csv", ("document_id",)),
        "family_holdout_v1": (DEFAULT_OUTPUT / "family_holdout/family_review_key.csv", ("document_id",)),
        "family_holdout_v2": (DEFAULT_OUTPUT / "family_holdout_v2/family_review_key.csv", ("document_id",)),
        "ieepa_holdout_v3": (DEFAULT_OUTPUT / "ieepa_holdout_v3/family_review_key.csv", ("document_id",)),
        "hc_union_development": (DEFAULT_OUTPUT / "hc_union_holdout/family_review_key.csv", ("document_id",)),
        "hc_union_confirmatory_initial": (DEFAULT_OUTPUT / "hc_union_holdout_v2/family_review_key.csv", ("document_id",)),
        "family_parent_rule_development": (DEFAULT_OUTPUT / "family_parent_rule_development/parent_pair_review.csv", ("child_id", "parent_id")),
        "noncontrol_scope_screen": (DEFAULT_OUTPUT / "parent_pair_noncontrol_scope_screen.csv", ("child_id", "parent_id")),
    }
    excluded_by_source = {name: ids(path, *fields) for name, (path, fields) in evidence.items()}
    reviewed = set().union(*excluded_by_source.values())
    explicit_children = explicit_parent_child_ids(read_csv(AUTOMATIC_EDGES))

    documents, source_audit = load_documents()
    assign_families(documents, load_profiles())
    pool = [
        row for row in documents
        if row["document_id"] not in reviewed
        and row["document_id"] not in explicit_children
        and not row["analysis_scope_reason"]
        and row["families"]
    ]
    selected = balanced_sample(
        pool, 2, ("president", "document_type"), "hc_union_holdout_v2:explicit_link_replacements"
    )
    if len(selected) != 2:
        raise ValueError(f"expected two replacement cases, found {len(selected)}")

    queue, key = [], []
    for number, row in enumerate(selected, 1):
        review_id = f"R{number:02d}"
        queue.append({
            "review_id": review_id, "family_id": "hc_union",
            "document_id": row["document_id"], "president": row["president"],
            "date": row["date"], "document_type": row["document_type"],
            "title": row["title"], "url": row["url"],
            "non_vesting_text": row["primary_text"], "decision": "", "review_notes": "",
        })
        key.append({
            "review_id": review_id, "document_id": row["document_id"],
            "queue_type": "proposed", "matched_families": "|".join(row["families"]),
            "loose_families": "|".join(row["loose_families"]),
        })

    OUTPUT.mkdir(parents=True, exist_ok=True)
    queue_path, key_path = OUTPUT / "family_review_queue.csv", OUTPUT / "family_review_key.csv"
    write_csv(queue_path, queue); write_csv(key_path, key)
    manifest = {
        "kind": "hc_union_confirmatory_explicit_link_replacements",
        "status": "frozen_pending_review", "rows": 2, "proposed": 2,
        "replaces_review_ids": ["V01", "V04"],
        "reason": "initial cases are children with resolved direct-transition edges",
        "explicit_parent_child_children_excluded": len(explicit_children),
        "excluded_documents_total": len(reviewed | explicit_children),
        "evidence_inputs": {name: sha256(path) for name, (path, _) in evidence.items()},
        "automatic_edges_sha256": sha256(AUTOMATIC_EDGES),
        "rule_inputs": {"build.py": sha256(HERE / "build.py"), "family_codebook.csv": sha256(HERE / "family_codebook.csv")},
        "outputs": {queue_path.name: sha256(queue_path), key_path.name: sha256(key_path)},
        "source_audit": source_audit,
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"rows": 2, "output": str(OUTPUT)}, sort_keys=True))


if __name__ == "__main__":
    main()
