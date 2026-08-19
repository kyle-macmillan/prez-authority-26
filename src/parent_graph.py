"""Stable schemas for reviewed plausible-precedent edges."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


SIMILARITY_EDGE_FIELDS = (
    "child_id", "parent_id", "document_type", "child_date", "parent_date",
    "child_function_ids", "parent_function_ids", "evidence_segment_pairs",
    "retrieval_rank", "retrieval_score", "review_decision", "reviewer",
    "explanation", "claim_type",
)


def new_similarity_edge(**values: Any) -> dict[str, Any]:
    edge = {field: values.get(field, "") for field in SIMILARITY_EDGE_FIELDS}
    edge["claim_type"] = values.get("claim_type", "plausible_precedent")
    if edge["review_decision"] not in {"", "parent", "not_parent", "none_available", "not_reviewed"}:
        raise ValueError("invalid review_decision")
    return edge


def read_edges(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
