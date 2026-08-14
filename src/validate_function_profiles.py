#!/usr/bin/env python3
"""Validate Gemini function-profile responses without making network calls."""

from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any

from function_profiles import parse_json_response, validate_profile


ROOT = Path(__file__).resolve().parents[1]


def _exact_excerpt(source: str, evidence: Any) -> tuple[str, int, int] | None:
    """Locate evidence exactly or across whitespace-only formatting differences."""
    if not isinstance(evidence, str) or not evidence.strip():
        return None
    start = source.find(evidence)
    if start >= 0:
        return evidence, start, start + len(evidence)
    stripped = evidence.strip()
    for candidate in (stripped, stripped.strip('"“”')):
        start = source.find(candidate)
        if start >= 0:
            return candidate, start, start + len(candidate)
        chunks = re.findall(r"\S+", candidate)
        if not chunks:
            continue
        match = re.search(r"\s+".join(re.escape(chunk) for chunk in chunks), source)
        if match:
            return match.group(0), match.start(), match.end()
    return None


def _unique_token_excerpt(source: str, evidence: Any) -> tuple[str, int, int] | None:
    """Locate a unique word-for-word excerpt despite case or punctuation changes.

    This deliberately does not use fuzzy matching: every Unicode word token must be
    identical after case folding, in the same order, and occur only once in the source.
    The returned evidence is always copied verbatim from the supplied source.
    """
    if not isinstance(evidence, str) or not evidence.strip():
        return None
    source_tokens = [
        (match.group(0).casefold(), match.start(), match.end())
        for match in re.finditer(r"\w+", source, re.UNICODE)
    ]
    evidence_tokens = [
        match.group(0).casefold()
        for match in re.finditer(r"\w+", evidence, re.UNICODE)
    ]
    if not evidence_tokens:
        return None
    values = [token for token, _, _ in source_tokens]
    matches = [
        index for index, token in enumerate(values)
        if token == evidence_tokens[0]
        and values[index:index + len(evidence_tokens)] == evidence_tokens
    ]
    if len(matches) != 1:
        return None
    index = matches[0]
    start = source_tokens[index][1]
    end = source_tokens[index + len(evidence_tokens) - 1][2]
    return source[start:end], start, end


def normalize_profile_response(raw: dict[str, Any], *, full_text: str,
                               segment_texts: dict[str, str]) -> tuple[dict[str, Any], list[str]]:
    """Apply auditable, non-substantive repairs grounded in supplied source text."""
    normalized = copy.deepcopy(raw)
    changes: list[str] = []
    for index, function in enumerate(normalized.get("policy_functions", [])):
        if not isinstance(function, dict):
            continue
        located = _exact_excerpt(full_text, function.get("evidence"))
        token_equivalent = False
        if located is None:
            located = _unique_token_excerpt(full_text, function.get("evidence"))
            token_equivalent = located is not None
        if located and located[0] != function.get("evidence"):
            function["evidence"], function["evidence_start"], function["evidence_end"] = located
            kind = "unique token-equivalent" if token_equivalent else "whitespace/boundary"
            changes.append(f"policy_functions[{index}]: normalized evidence {kind}")

    for index, function in enumerate(normalized.get("operative_functions", [])):
        if not isinstance(function, dict):
            continue
        segment_id = function.get("segment_id")
        if isinstance(segment_id, str) and segment_id.startswith("SEGMENT "):
            candidate = segment_id.removeprefix("SEGMENT ")
            if candidate in segment_texts:
                function["segment_id"] = segment_id = candidate
                changes.append(f"operative_functions[{index}]: removed SEGMENT prefix")
        located = _exact_excerpt(segment_texts.get(segment_id, ""), function.get("evidence"))
        token_equivalent = False
        if located is None:
            located = _unique_token_excerpt(
                segment_texts.get(segment_id, ""), function.get("evidence")
            )
            token_equivalent = located is not None
        if located is None:
            matches = [
                (candidate_id, match)
                for candidate_id, text in segment_texts.items()
                if (match := (
                    _exact_excerpt(text, function.get("evidence"))
                    or _unique_token_excerpt(text, function.get("evidence"))
                )) is not None
            ]
            if len(matches) == 1:
                candidate_id, located = matches[0]
                if candidate_id != segment_id:
                    function["segment_id"] = candidate_id
                    changes.append(
                        f"operative_functions[{index}]: reassigned to unique source segment {candidate_id}"
                    )
        if located and located[0] != function.get("evidence"):
            function["evidence"], function["evidence_start"], function["evidence_end"] = located
            kind = "unique token-equivalent" if token_equivalent else "whitespace/boundary"
            changes.append(f"operative_functions[{index}]: normalized evidence {kind}")
        if "action_type" in function:
            function.pop("action_type")
            changes.append(f"operative_functions[{index}]: removed unsupported action_type")
    return normalized, changes


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def validate_responses(responses: list[dict[str, Any]], documents: list[dict[str, Any]],
                       segments: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    docs = {str(row["document_id"]): row for row in documents}
    segment_map: dict[str, dict[str, str]] = {}
    for row in segments:
        segment_map.setdefault(str(row["document_id"]), {})[str(row["segment_id"])] = row["text"]
    profiles, errors = [], []
    seen_request_ids: set[str] = set()
    for response in responses:
        request_id = response.get("request_id")
        if request_id in seen_request_ids:
            errors.append({"request_id": request_id, "errors": ["duplicate response ignored"]})
            continue
        seen_request_ids.add(request_id)
        metadata = response.get("metadata", {})
        document_id = str(metadata.get("document_id", ""))
        document = docs.get(document_id)
        if document is None:
            errors.append({"request_id": request_id, "errors": ["unknown document_id"]})
            continue
        try:
            raw = parse_json_response(response.get("text", ""))
            known_segments = segment_map.get(document_id, {})
            raw, normalizations = normalize_profile_response(
                raw, full_text=document["cleaned_masked_text"], segment_texts=known_segments
            )
            result = validate_profile(raw, document_id=document_id,
                                      full_text=document["cleaned_masked_text"],
                                      segment_texts=segment_map.get(document_id, {}))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            errors.append({"request_id": request_id, "errors": [str(exc)]})
            continue
        if result.errors:
            errors.append({"request_id": request_id, "errors": list(result.errors)})
        else:
            profiles.append({
                "request_id": request_id,
                "document_id": document_id,
                "model": response.get("model"),
                "model_version": response.get("model_version"),
                "normalizations": normalizations,
                "profile": result.profile,
            })
    return profiles, errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("responses", type=Path)
    parser.add_argument("--documents", type=Path, required=True)
    parser.add_argument("--segments", type=Path, required=True)
    parser.add_argument("--profiles", type=Path, required=True)
    parser.add_argument("--errors", type=Path, required=True)
    args = parser.parse_args()
    profiles, errors = validate_responses(_read_jsonl(args.responses), _read_jsonl(args.documents),
                                          _read_jsonl(args.segments))
    for path, rows in ((args.profiles, profiles), (args.errors, errors)):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"profiles": len(profiles), "errors": len(errors)}, sort_keys=True))


if __name__ == "__main__":
    main()
