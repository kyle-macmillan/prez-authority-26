"""Shared representations and scoring utilities for the function-profile pilot."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

import numpy as np


TRADE_RE = re.compile(
    r"\b(?:tariff|trade agreement|trade relations|import(?:s|ed|ation)?|export(?:s|ed)?|"
    r"customs|duti(?:y|es)|quota|harmonized tariff schedule|free[- ]trade|"
    r"most[- ]favored[- ]nation|generalized system of preferences)\b", re.I,
)
FUNCTION_FIELDS = ("actor", "action", "target", "mechanism", "effect", "condition", "timing")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%B %d, %Y")


def is_trade_proclamation(document: dict) -> bool:
    return document["document_type"] == "proclamation" and bool(
        TRADE_RE.search(f"{document.get('title', '')} {document.get('cleaned_masked_text', '')}")
    )


def function_text(function: dict) -> str:
    """Serialize semantic fields only; evidence is retained separately for audit."""
    return "\n".join(
        f"{field.replace('_', ' ').title()}: {function.get(field, '')}"
        for field in FUNCTION_FIELDS if str(function.get(field, "")).strip()
    )


def profile_function_rows(profile_rows: list[dict]) -> list[dict]:
    output = []
    for row in profile_rows:
        document_id = str(row["document_id"])
        profile = row["profile"]
        for kind in ("policy_functions", "operative_functions"):
            for function in profile.get(kind, []):
                output.append({
                    "document_id": document_id,
                    "kind": "policy" if kind == "policy_functions" else "operative",
                    "function_id": function["function_id"],
                    "segment_id": function.get("segment_id", ""),
                    "text": function_text(function),
                    "function": function,
                })
    return output


def child_coverage_score(matrix: np.ndarray) -> float:
    """Mean best parent match for each child function; unmatched children score zero."""
    if matrix.shape[0] == 0:
        return 0.0
    if matrix.shape[1] == 0:
        return 0.0
    return float(np.mean(np.max(matrix, axis=1)))


def reciprocal_rank_fusion(ranks: dict[str, int | None], k: int = 60) -> float:
    return sum(1.0 / (k + rank) for rank in ranks.values() if rank is not None)


def one_to_one_alignment(matrix: np.ndarray) -> list[tuple[int, int, float]]:
    """Maximum-weight alignment with deterministic fallback when SciPy is unavailable."""
    if not matrix.size:
        return []
    try:
        from scipy.optimize import linear_sum_assignment
        rows, cols = linear_sum_assignment(-matrix)
        return sorted(
            ((int(i), int(j), float(matrix[i, j])) for i, j in zip(rows, cols)),
            key=lambda item: (item[0], item[1]),
        )
    except ImportError:
        choices = sorted(
            ((float(matrix[i, j]), i, j) for i in range(matrix.shape[0])
             for j in range(matrix.shape[1])), reverse=True,
        )
        used_rows, used_cols, output = set(), set(), []
        for score, i, j in choices:
            if i not in used_rows and j not in used_cols:
                used_rows.add(i); used_cols.add(j); output.append((i, j, score))
        return sorted(output)


def alignment_coverage(matrix: np.ndarray) -> tuple[float, list[tuple[int, int, float]]]:
    if matrix.shape[0] == 0:
        return 0.0, []
    aligned = one_to_one_alignment(matrix)
    return sum(score for _, _, score in aligned) / matrix.shape[0], aligned
