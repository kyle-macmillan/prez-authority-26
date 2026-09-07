#!/usr/bin/env python3
"""Build the disjoint post-revision family-validation holdout."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from build import (
    DEFAULT_OUTPUT,
    FAMILY_ORDER,
    assign_families,
    build_family_review,
    load_documents,
    read_csv,
    sha256,
    write_csv,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--development-key", type=Path,
        default=DEFAULT_OUTPUT / "family_development" / "family_review_key.csv",
    )
    parser.add_argument(
        "--prior-holdout-key", type=Path,
        default=DEFAULT_OUTPUT / "family_holdout" / "family_review_key.csv",
    )
    parser.add_argument(
        "--parent-review", type=Path,
        default=DEFAULT_OUTPUT / "family_parent_rule_development" / "parent_pair_review.csv",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT / "family_holdout_v2")
    args = parser.parse_args()

    development_key = read_csv(args.development_key)
    prior_holdout_key = read_csv(args.prior_holdout_key)
    parent_review = read_csv(args.parent_review)
    development_ids = {row["document_id"] for row in development_key}
    prior_holdout_ids = {row["document_id"] for row in prior_holdout_key}
    parent_review_ids = {row["child_id"] for row in parent_review}
    reviewed_document_ids = development_ids | prior_holdout_ids | parent_review_ids
    documents, source_audit = load_documents()
    assign_families(documents, {})
    queue = build_family_review(
        documents,
        proposed_count=5,
        boundary_count=5,
        excluded_document_ids=reviewed_document_ids,
        sample_salt="family_holdout_v2",
        review_id_prefix="H2",
    )
    proposed_count = boundary_count = 5
    # The requested design is 5 proposed and 5 hard-boundary cases per family.
    # Do not reuse already reviewed documents merely to fill a depleted boundary pool.
    requested_rows = len(FAMILY_ORDER) * (proposed_count + boundary_count)
    by_family = Counter(row["family_id"] for row in queue)
    shortfalls = {
        family: proposed_count + boundary_count - by_family[family]
        for family in FAMILY_ORDER
        if by_family[family] < proposed_count + boundary_count
    }
    if not queue:
        raise ValueError("family holdout queue is empty")
    key = [
        {
            "review_id": row["review_id"], "family_id": row["family_id"],
            "document_id": row["document_id"], "queue_type": row["queue_type"],
        }
        for row in queue
    ]
    blinded = [{key: value for key, value in row.items() if key != "queue_type"} for row in queue]
    write_csv(args.output / "family_review_queue.csv", blinded)
    write_csv(args.output / "family_review_key.csv", key)
    manifest = {
        "kind": "post_revision_family_holdout",
        "rows": len(queue),
        "requested_rows": requested_rows,
        "proposed_per_family": proposed_count,
        "boundary_per_family": boundary_count,
        "sampling_shortfalls": shortfalls,
        "excluded_development_documents": len(development_ids),
        "excluded_prior_holdout_documents": len(prior_holdout_ids),
        "excluded_parent_review_children": len(parent_review_ids),
        "excluded_documents_total": len(reviewed_document_ids),
        "development_key_sha256": sha256(args.development_key),
        "prior_holdout_key_sha256": sha256(args.prior_holdout_key),
        "parent_review_sha256": sha256(args.parent_review),
        "source_audit": source_audit,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"rows": len(queue), "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
