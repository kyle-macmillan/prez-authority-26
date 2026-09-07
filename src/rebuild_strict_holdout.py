#!/usr/bin/env python3
"""Rebuild the development/holdout split after the historical off-by-one bug.

The segmentation and vesting holdout is defined as every row in the original master
corpus that was absent from both previously used partition CSVs. Every row that
appeared in either old CSV is treated as exposed and assigned to development.
Parent-relationship analysis may explicitly use both partitions as a separate task.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import subprocess
from pathlib import Path


EXPECTED_MASTER = 20_232
EXPECTED_DEVELOPMENT = 18_418
EXPECTED_HOLDOUT = 1_814


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def read_rows_from_git(spec: str) -> list[dict[str, str]]:
    result = subprocess.run(
        ["git", "show", spec], check=True, capture_output=True, text=True,
    )
    return list(csv.DictReader(io.StringIO(result.stdout)))


def row_ids(rows: list[dict[str, str]]) -> set[int]:
    return {int(row[""]) for row in rows}


def id_hash(ids: set[int]) -> str:
    payload = "\n".join(map(str, sorted(ids))).encode()
    return hashlib.sha256(payload).hexdigest()


def write_rows(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def verify_complete_partition(
    master: list[dict[str, str]],
    development: list[dict[str, str]],
    holdout: list[dict[str, str]],
) -> None:
    master_by_id = {row[""]: row for row in master}
    development_by_id = {row[""]: row for row in development}
    holdout_by_id = {row[""]: row for row in holdout}
    if len(master_by_id) != len(master):
        raise ValueError("master contains duplicate document IDs")
    if set(development_by_id) & set(holdout_by_id):
        raise ValueError("development and holdout overlap")
    if set(development_by_id) | set(holdout_by_id) != set(master_by_id):
        raise ValueError("development and holdout do not cover the complete master")
    if {**development_by_id, **holdout_by_id} != master_by_id:
        raise ValueError("a partition row differs from its master source row")


def rebuild(
    master_path: Path,
    old_dev_path: Path,
    old_holdout_path: Path,
    master_label: str | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]], dict]:
    master = read_rows(master_path)
    old_dev = read_rows(old_dev_path)
    old_holdout = read_rows(old_holdout_path)
    master_ids = row_ids(master)
    exposed_ids = row_ids(old_dev) | row_ids(old_holdout)

    if len(master) != EXPECTED_MASTER or len(master_ids) != EXPECTED_MASTER:
        raise ValueError(f"expected {EXPECTED_MASTER:,} unique master rows")
    if not exposed_ids <= master_ids:
        raise ValueError("an exposed document ID is absent from the master corpus")

    strict_holdout_ids = master_ids - exposed_ids
    development = [row for row in master if int(row[""]) in exposed_ids]
    holdout = [row for row in master if int(row[""]) in strict_holdout_ids]
    if len(development) != EXPECTED_DEVELOPMENT or len(holdout) != EXPECTED_HOLDOUT:
        raise ValueError(
            f"unexpected split: development={len(development):,}, holdout={len(holdout):,}"
        )

    manifest = {
        "schema_version": 1,
        "policy": (
            "task-specific segmentation and vesting holdout: no document present in either "
            "previously used CSV; parent-relationship analysis may use both partitions"
        ),
        "master_source": master_label or str(master_path),
        "counts": {
            "master": len(master),
            "development_exposed": len(development),
            "holdout_unexposed": len(holdout),
        },
        "sha256": {
            "master_ids": id_hash(master_ids),
            "development_ids": id_hash(exposed_ids),
            "holdout_ids": id_hash(strict_holdout_ids),
        },
        "invariants": {
            "development_holdout_overlap": 0,
            "development_plus_holdout_equals_master": True,
            "holdout_intersection_with_previously_used_partitions": 0,
        },
    }
    return development, holdout, manifest


def rebuild_from_holdout_ids(
    master: list[dict[str, str]],
    holdout_ids: set[int],
    master_label: str,
) -> tuple[list[dict[str, str]], list[dict[str, str]], dict]:
    """Rebuild the canonical split from the durable holdout-ID registry."""
    master_ids = row_ids(master)
    if len(master) != EXPECTED_MASTER or len(master_ids) != EXPECTED_MASTER:
        raise ValueError(f"expected {EXPECTED_MASTER:,} unique master rows")
    if len(holdout_ids) != EXPECTED_HOLDOUT:
        raise ValueError(f"expected {EXPECTED_HOLDOUT:,} unique holdout IDs")
    if not holdout_ids <= master_ids:
        raise ValueError("a holdout document ID is absent from the master corpus")

    development = [row for row in master if int(row[""]) not in holdout_ids]
    holdout = [row for row in master if int(row[""]) in holdout_ids]
    development_ids = row_ids(development)
    if (
        len(development) != EXPECTED_DEVELOPMENT
        or len(holdout) != EXPECTED_HOLDOUT
        or development_ids & holdout_ids
        or development_ids | holdout_ids != master_ids
    ):
        raise ValueError("rebuilt partitions are not the expected disjoint master partition")

    manifest = {
        "schema_version": 1,
        "policy": (
            "task-specific segmentation and vesting holdout: no document present in either "
            "previously used CSV; parent-relationship analysis may use both partitions"
        ),
        "master_source": master_label,
        "counts": {
            "master": len(master),
            "development_exposed": len(development),
            "holdout_unexposed": len(holdout),
        },
        "sha256": {
            "master_ids": id_hash(master_ids),
            "development_ids": id_hash(development_ids),
            "holdout_ids": id_hash(holdout_ids),
        },
        "invariants": {
            "development_holdout_overlap": 0,
            "development_plus_holdout_equals_master": True,
            "holdout_intersection_with_previously_used_partitions": 0,
        },
    }
    return development, holdout, manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    master_group = parser.add_mutually_exclusive_group(required=True)
    master_group.add_argument("--master", type=Path)
    master_group.add_argument("--master-git-spec")
    parser.add_argument("--master-label")
    parser.add_argument("--old-dev", type=Path)
    parser.add_argument("--old-holdout", type=Path)
    parser.add_argument("--holdout-ids", type=Path)
    parser.add_argument("--dev-output", type=Path, required=True)
    parser.add_argument("--holdout-output", type=Path, required=True)
    parser.add_argument("--holdout-ids-output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    args = parser.parse_args()

    if args.master_git_spec:
        master = read_rows_from_git(args.master_git_spec)
        master_label = args.master_label or f"git:{args.master_git_spec}"
    else:
        master = read_rows(args.master)
        master_label = args.master_label or str(args.master)

    if args.holdout_ids:
        holdout_ids = set(json.loads(args.holdout_ids.read_text(encoding="utf-8")))
        development, holdout, manifest = rebuild_from_holdout_ids(
            master, holdout_ids, master_label,
        )
    else:
        if not args.old_dev or not args.old_holdout or not args.master:
            parser.error("either --holdout-ids or --master with both prior partitions is required")
        development, holdout, manifest = rebuild(
            args.master, args.old_dev, args.old_holdout, master_label
        )
    fields = list(development[0])
    verify_complete_partition(master, development, holdout)
    write_rows(args.dev_output, development, fields)
    write_rows(args.holdout_output, holdout, fields)
    holdout_ids = sorted(row_ids(holdout))
    args.holdout_ids_output.write_text(json.dumps(holdout_ids) + "\n", encoding="utf-8")
    args.manifest_output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    verify_complete_partition(
        master, read_rows(args.dev_output), read_rows(args.holdout_output),
    )


if __name__ == "__main__":
    main()
