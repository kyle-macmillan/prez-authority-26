"""Schemas and validation for directive policy/operative-function profiles.

The model-facing representation is deliberately authority-blind.  Authority
spans are replaced before requests are built, while the original spans are
stored separately by :mod:`parent_analysis` for the later divergence study.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


FUNCTION_FIELDS = (
    "function_id",
    "label",
    "actor",
    "action",
    "target",
    "mechanism",
    "effect",
    "condition",
    "timing",
    "evidence",
    "evidence_start",
    "evidence_end",
    "confidence",
)

FUNCTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["function_id", "label", "actor", "action", "target", "mechanism",
                  "effect", "condition", "timing", "evidence", "evidence_start",
                  "evidence_end", "confidence"],
    "properties": {
        "function_id": {"type": "string"},
        "label": {"type": "string"},
        "actor": {"type": "string"},
        "action": {"type": "string"},
        "target": {"type": "string"},
        "mechanism": {"type": "string"},
        "effect": {"type": "string"},
        "condition": {"type": "string"},
        "timing": {"type": "string"},
        "evidence": {"type": "string"},
        "evidence_start": {"type": ["integer", "null"]},
        "evidence_end": {"type": ["integer", "null"]},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
}

OPERATIVE_FUNCTION_SCHEMA: dict[str, Any] = {
    **FUNCTION_SCHEMA,
    "required": [*FUNCTION_SCHEMA["required"], "segment_id"],
    "properties": {**FUNCTION_SCHEMA["properties"], "segment_id": {"type": "string"}},
}

PROFILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["document_id", "policy_functions", "operative_functions", "notes"],
    "properties": {
        "document_id": {"type": "string"},
        "policy_functions": {"type": "array", "items": FUNCTION_SCHEMA},
        "operative_functions": {"type": "array", "items": OPERATIVE_FUNCTION_SCHEMA},
        "notes": {"type": "string"},
    },
}


@dataclass(frozen=True)
class ProfileValidation:
    profile: dict[str, Any] | None
    errors: tuple[str, ...]


def _text(value: Any, field: str, errors: list[str], *, required: bool = True) -> str:
    if not isinstance(value, str):
        errors.append(f"{field} must be a string")
        return ""
    if required and not value.strip():
        errors.append(f"{field} must not be empty")
    return value


def _parse_int(value: Any, field: str, errors: list[str]) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        errors.append(f"{field} must be an integer or null")
        return None
    if value < 0:
        errors.append(f"{field} must not be negative")
        return None
    return value


def _validate_function(raw: Any, *, prefix: str, source_text: str, seen: set[str],
                       extra_fields: set[str] | None = None,
                       parent_errors: list[str] | None = None) -> dict[str, Any] | None:
    errors: list[str] = []
    if not isinstance(raw, dict):
        return None
    unsupported = set(raw) - set(FUNCTION_FIELDS) - (extra_fields or set())
    if unsupported:
        errors.append(f"{prefix}: unsupported fields {sorted(unsupported)}")
    for field in FUNCTION_FIELDS:
        if field not in raw:
            errors.append(f"{prefix}: missing {field}")
    if errors:
        if parent_errors is not None:
            parent_errors.extend(errors)
        return None
    function = {field: raw[field] for field in FUNCTION_FIELDS}
    function["function_id"] = _text(function["function_id"], f"{prefix}.function_id", errors)
    if function["function_id"] in seen:
        errors.append(f"{prefix}.function_id is duplicated")
    seen.add(function["function_id"])
    for field in FUNCTION_FIELDS[1:9]:
        function[field] = _text(function[field], f"{prefix}.{field}", errors, required=False)
    function["evidence"] = _text(function["evidence"], f"{prefix}.evidence", errors)
    function["evidence_start"] = _parse_int(function["evidence_start"], f"{prefix}.evidence_start", errors)
    function["evidence_end"] = _parse_int(function["evidence_end"], f"{prefix}.evidence_end", errors)
    confidence = function["confidence"]
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        if not 0 <= confidence <= 1:
            errors.append(f"{prefix}.confidence numeric value must be between 0 and 1")
        else:
            function["confidence"] = (
                "high" if confidence >= 0.8 else
                "medium" if confidence >= 0.5 else "low"
            )
    elif confidence not in {"high", "medium", "low"}:
        errors.append(f"{prefix}.confidence must be high, medium, or low")
    evidence = function["evidence"]
    if evidence and source_text and evidence not in source_text:
        errors.append(f"{prefix}.evidence is not an exact substring of supplied text")
    if function["evidence_start"] is not None and function["evidence_end"] is not None:
        start, end = function["evidence_start"], function["evidence_end"]
        if end < start:
            errors.append(f"{prefix}.evidence_end precedes evidence_start")
        elif source_text:
            offset_text = source_text[start:end]
            if evidence in source_text:
                # Models often count a trailing space or punctuation boundary
                # differently.  The excerpt is authoritative; normalize offsets
                # to its exact occurrence for downstream joins.
                occurrence = source_text.find(evidence, max(0, start - 200))
                if occurrence >= 0:
                    function["evidence_start"] = occurrence
                    function["evidence_end"] = occurrence + len(evidence)
            elif offset_text.strip() != evidence.strip():
                errors.append(f"{prefix}.evidence offsets do not match evidence")
    if errors:
        if parent_errors is not None:
            parent_errors.extend(errors)
        return None
    return function


def parse_json_response(text: str) -> dict[str, Any]:
    """Parse JSON or a single fenced JSON object returned by a model."""
    candidate = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", candidate, re.I | re.S)
    if fenced:
        candidate = fenced.group(1)
    value = json.loads(candidate)
    if not isinstance(value, dict):
        raise ValueError("profile response must be a JSON object")
    return value


def validate_profile(raw: dict[str, Any], *, document_id: str, full_text: str,
                     segment_texts: dict[str, str]) -> ProfileValidation:
    errors: list[str] = []
    if raw.get("document_id") != document_id:
        errors.append("document_id does not match request metadata")
    policy: list[dict[str, Any]] = []
    operative: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw.get("policy_functions", [])):
        value = _validate_function(item, prefix=f"policy_functions[{index}]", source_text=full_text,
                                   seen=seen, parent_errors=errors)
        if value is None:
            errors.append(f"invalid policy_functions[{index}]")
        else:
            policy.append(value)
    for index, item in enumerate(raw.get("operative_functions", [])):
        if not isinstance(item, dict):
            errors.append(f"operative_functions[{index}] must be an object")
            continue
        segment_id = item.get("segment_id")
        if not isinstance(segment_id, str) or segment_id not in segment_texts:
            errors.append(f"operative_functions[{index}] has unknown segment_id")
            continue
        value = _validate_function(item, prefix=f"operative_functions[{index}]",
                                   source_text=segment_texts[segment_id], seen=seen,
                                   extra_fields={"segment_id"}, parent_errors=errors)
        if value is None:
            errors.append(f"invalid operative_functions[{index}]")
        else:
            value["segment_id"] = segment_id
            operative.append(value)
    notes = raw.get("notes")
    if not isinstance(notes, str):
        errors.append("notes must be a string")
        notes = ""
    if not isinstance(raw.get("policy_functions"), list):
        errors.append("policy_functions must be an array")
    if not isinstance(raw.get("operative_functions"), list):
        errors.append("operative_functions must be an array")
    if errors:
        return ProfileValidation(None, tuple(errors))
    return ProfileValidation({
        "document_id": document_id,
        "policy_functions": policy,
        "operative_functions": operative,
        "notes": notes,
    }, ())
