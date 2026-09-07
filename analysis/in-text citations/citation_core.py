"""Shared, network-free primitives for the in-text citation analysis."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
DEV = ROOT / "data" / "4_28_2026_build_dev.csv"
HOLDOUT_IDS = ROOT / "data" / "holdout_ids.json"
PARTITION_MANIFEST = ROOT / "data" / "corpus_partition_manifest.json"
EXPECTED_DEVELOPMENT = 18_418
EXPECTED_DEVELOPMENT_HASH = "212ebe5d8f9b454aa31bbb1008cea8c2bf8d35f5c3a2025a59283b6eca515a07"

SOURCE_TYPES = {
    "constitution", "statute_or_code", "legislative_measure", "regulation",
    "judicial_decision", "treaty_or_agreement", "presidential_directive",
    "other_legal_instrument", "generic_laws",
}
REGIONS = {"vesting", "body"}


@dataclass(frozen=True)
class TextSegment:
    segment_id: str
    region: str
    text: str
    source_type: str


def id_hash(ids: Iterable[str]) -> str:
    values = sorted({int(value) for value in ids})
    return hashlib.sha256("\n".join(map(str, values)).encode()).hexdigest()


def validate_development_rows(rows: list[dict[str, str]]) -> None:
    ids = [row[""] for row in rows]
    holdout = {str(value) for value in json.loads(HOLDOUT_IDS.read_text(encoding="utf-8"))}
    manifest = json.loads(PARTITION_MANIFEST.read_text(encoding="utf-8"))
    if len(rows) != EXPECTED_DEVELOPMENT or len(set(ids)) != EXPECTED_DEVELOPMENT:
        raise ValueError("development corpus must contain exactly 18,418 unique documents")
    if set(ids) & holdout:
        raise ValueError("development corpus contains a protected holdout document")
    actual_hash = id_hash(ids)
    expected_hash = manifest["sha256"]["development_ids"]
    if actual_hash != expected_hash or actual_hash != EXPECTED_DEVELOPMENT_HASH:
        raise ValueError("development corpus ID hash does not match the canonical partition")


def build_segments(text: str, doc_type: str) -> tuple[list[TextSegment], list[str]]:
    """Apply existing structural segmentation, retaining only analytic regions."""
    from segmenter import segment_ordering

    raw = segment_ordering(text, doc_type)
    segments: list[TextSegment] = []
    excluded: list[str] = []
    counters = {"vesting": 0, "body": 0, "excluded": 0}
    for segment in raw:
        if segment.seg_type == "metadata":
            excluded.append(segment.text)
            counters["excluded"] += 1
            continue
        region = "vesting" if segment.seg_type == "vesting_clause" else "body"
        counters[region] += 1
        segments.append(TextSegment(
            segment_id=f"{region[0].upper()}{counters[region]:03d}",
            region=region,
            text=segment.text,
            source_type=segment.seg_type,
        ))
    if not segments and text.strip():
        # Preserve anomalous short/legacy documents for review instead of silently
        # producing an empty analytic record.
        segments.append(TextSegment("B001", "body", text.strip(), "unclassified"))
        excluded.clear()
    return segments, excluded


def normalize_words(value: str) -> str:
    value = value.casefold().replace("’", "'")
    value = re.sub(r"\b(no|number)\.?\s+", "", value)
    value = re.sub(r"[^a-z0-9§]+", " ", value)
    return " ".join(value.split())


RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("statute_or_code", re.compile(
        r"\b(?:sections?\s+[\dA-Za-z().,\-–—\s]+?\s+of\s+title\s+\d+\s*,?\s*(?:of\s+the\s+)?United\s+States\s+Code"
        r"|\d+\s+U\.?\s*S\.?\s*C\.?\s*(?:§{1,2}\s*)?[\dA-Za-z().\-–—]+(?:\s+et\s+seq\.?)?)",
        re.I,
    )),
    ("regulation", re.compile(
        r"\b\d+\s+C\.?\s*F\.?\s*R\.?\s*(?:§{1,2}\s*)?[\dA-Za-z().\-–—]+"
        r"|\b\d+\s+Fed\.?\s+Reg\.?\s+\d+(?:[-–]\d+)?", re.I,
    )),
    ("legislative_measure", re.compile(
        r"\bPublic\s+Law\s+(?:No\.?\s*)?\d+(?:[-–]\d+)?"
        r"|\b\d+\s+Stat\.?\s+\d+(?:[-–]\d+)?"
        r"|\b(?:House|Senate)?\s*(?:Joint|Concurrent)\s+Resolution(?:\s+\d+)?\b", re.I,
    )),
    ("presidential_directive", re.compile(
        r"\bExecutive\s+Orders?(?:\s+Nos?\.?)?\s+\d{3,5}(?:\s*[-–]\s*A)?"
        r"|\bProclamation(?:\s+No\.?)?\s+\d+"
        r"|\bReorganization\s+Plan(?:\s+No\.?)?\s+\d+(?:\s+of\s+\d{4})?"
        r"|\b(?:NSD|PPD|PSD|NSDD|NSPD|HSPD|PDD|NSM|NSPM)\s*[-/]\s*\d+", re.I,
    )),
    ("constitution", re.compile(
        r"\b(?:(?:Article\s+[IVXLC\d]+|[A-Z][A-Za-z-]+\s+Clause)\s+of\s+)?"
        r"(?:the\s+)?Constitution(?:\s+of\s+the\s+United\s+States(?:\s+of\s+America)?)?\b", re.I,
    )),
    ("generic_laws", re.compile(
        r"\b(?:the\s+)?laws?\s+of\s+the\s+United\s+States(?:\s+of\s+America)?\b", re.I,
    )),
    ("judicial_decision", re.compile(
        r"\b[A-Z][A-Za-z.&'’\-]+(?:\s+[A-Z][A-Za-z.&'’\-]+){0,5}\s+v\.\s+"
        r"[A-Z][A-Za-z.&'’\-]+(?:\s+[A-Z][A-Za-z.&'’\-]+){0,5}"
        r"(?:,\s*\d+\s+[A-Z][A-Za-z.\d ]+\s+\d+)?", re.I,
    )),
    ("statute_or_code", re.compile(
        r"\b(?:the\s+)?(?:[A-Z][A-Za-z0-9'’&.\-]*\s+){1,12}Act(?:\s+of\s+\d{4})?\b"
    )),
    ("treaty_or_agreement", re.compile(
        r"\b(?:the\s+)?(?:[A-Z][A-Za-z0-9'’&.\-]*\s+){1,12}"
        r"(?:Treaty|Convention|Covenant|Agreement|Accord|Protocol)\b"
    )),
)

VAGUE_RE = re.compile(
    r"\b(?:applicable\s+law|statutory\s+authorit(?:y|ies)|authority\s+granted\s+by\s+law)\b",
    re.I,
)


def _keys(source_type: str, evidence: str) -> tuple[list[str], list[str]]:
    normalized = normalize_words(evidence)
    if source_type == "constitution":
        provision = re.search(r"\b(article\s+[ivxlcdm\d]+|[a-z-]+\s+clause)\b", normalized)
        return ["constitution:us"], [f"constitution:us:{provision.group(1).replace(' ', '-')}" ] if provision else []
    if source_type == "generic_laws":
        return ["laws:us"], []
    usc = re.search(r"\b(\d+)\s+u\.?\s*s\.?\s*c\.?\s*§?\s*([\dA-Za-z-]+)((?:\([^)]*\))*)", evidence, re.I)
    if usc:
        root = f"usc:{usc.group(1)}:{usc.group(2).casefold()}"
        return [root], [root + normalize_words(usc.group(3)).replace(" ", "-")] if usc.group(3) else [root]
    cfr = re.search(r"\b(\d+)\s+c\.?\s*f\.?\s*r\.?\s*§?\s*([\dA-Za-z.-]+)((?:\([^)]*\))*)", evidence, re.I)
    if cfr:
        root = f"cfr:{cfr.group(1)}:{cfr.group(2).casefold()}"
        return [root], [root + normalize_words(cfr.group(3)).replace(" ", "-")] if cfr.group(3) else [root]
    public_law = re.search(r"public\s+law\s+(?:no\.?\s*)?(\d+)[-–](\d+)", evidence, re.I)
    if public_law:
        return [f"pl:{public_law.group(1)}-{public_law.group(2)}"], []
    statutes = re.search(r"\b(\d+)\s+stat\.?\s+(\d+)", evidence, re.I)
    if statutes:
        return [f"stat:{statutes.group(1)}:{statutes.group(2)}"], []
    number = re.search(r"\b(Executive\s+Order|Proclamation)\s+(?:No\.?\s*)?(\d+)", evidence, re.I)
    if number:
        prefix = "eo" if number.group(1).casefold().startswith("executive") else "proclamation"
        return [f"{prefix}:{number.group(2)}"], []
    act = re.search(r"\b(?:the\s+)?(.+?\bAct(?:\s+of\s+\d{4})?)\b", evidence)
    if act:
        return [f"act:{normalize_words(act.group(1))}"], []
    return [f"{source_type}:{normalized}"], []


def regex_citations(document_id: str, segments: list[TextSegment]) -> list[dict]:
    """Transparent baseline extraction; benchmarked before any production use."""
    citations: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for segment in segments:
        candidates = []
        for source_type, pattern in RULES:
            for match in pattern.finditer(segment.text):
                candidates.append((match.start(), match.end(), source_type, match.group(0)))
        candidates.sort(key=lambda value: (value[0], -(value[1] - value[0])))
        selected = []
        for candidate in candidates:
            if selected and candidate[0] < selected[-1][1]:
                continue
            selected.append(candidate)
        for start, end, source_type, evidence in selected:
            key = (segment.region, source_type, normalize_words(evidence))
            if key in seen:
                continue
            seen.add(key)
            instrument_keys, provision_keys = _keys(source_type, evidence)
            citations.append({
                "document_id": document_id,
                "region": segment.region,
                "segment_id": segment.segment_id,
                "evidence": evidence,
                "start": start,
                "end": end,
                "source_type": source_type,
                "instrument_label": evidence,
                "instrument_keys": instrument_keys,
                "provision_keys": provision_keys,
                "generic": source_type in {"constitution", "generic_laws"},
                "excluded": False,
                "exclusion_reason": "",
                "method": "regex",
            })
        for match in VAGUE_RE.finditer(segment.text):
            citations.append({
                "document_id": document_id,
                "region": segment.region,
                "segment_id": segment.segment_id,
                "evidence": match.group(0),
                "start": match.start(),
                "end": match.end(),
                "source_type": "other_legal_instrument",
                "instrument_label": match.group(0),
                "instrument_keys": [],
                "provision_keys": [],
                "generic": True,
                "excluded": True,
                "exclusion_reason": "vague generic legal reference",
                "method": "regex",
            })
    return citations


def validate_citations(response: dict, request: dict) -> None:
    if str(response.get("document_id")) != str(request["document_id"]):
        raise ValueError("response document_id does not match request")
    segments = {segment["segment_id"]: segment for segment in request["segments"]}
    citations = response.get("citations")
    if not isinstance(citations, list):
        raise ValueError("citations must be a list")
    known_instrument_keys: set[str] = set()
    for index, citation in enumerate(citations):
        missing = {
            "region", "segment_id", "evidence", "source_type", "instrument_label",
            "instrument_keys", "provision_keys", "generic", "excluded", "exclusion_reason",
        } - set(citation)
        if missing:
            raise ValueError(f"citation {index} missing fields: {sorted(missing)}")
        segment = segments.get(citation["segment_id"])
        if not segment or citation["region"] != segment["region"]:
            raise ValueError(f"citation {index} has an invalid segment or region")
        if citation["evidence"] not in segment["text"]:
            raise ValueError(f"citation {index} evidence is not verbatim source text")
        if citation["source_type"] not in SOURCE_TYPES:
            raise ValueError(f"citation {index} has an invalid source type")
        if not isinstance(citation["generic"], bool) or not isinstance(citation["excluded"], bool):
            raise ValueError(f"citation {index} flags must be booleans")
        for field in ("instrument_keys", "provision_keys"):
            values = citation[field]
            if not isinstance(values, list) or not all(isinstance(value, str) and value for value in values):
                raise ValueError(f"citation {index} has invalid {field}")
            if len(values) != len(set(values)):
                raise ValueError(f"citation {index} has duplicate {field}")
        if citation["excluded"]:
            if citation["instrument_keys"] or citation["provision_keys"]:
                raise ValueError(f"excluded citation {index} cannot have identity keys")
            if not citation["exclusion_reason"].strip():
                raise ValueError(f"excluded citation {index} needs an exclusion reason")
        elif not citation["instrument_keys"]:
            raise ValueError(f"included citation {index} needs an instrument key")
        if not citation["excluded"] and not citation["instrument_label"]:
            raise ValueError(f"included citation {index} needs an instrument label")
        if "start" in citation or "end" in citation:
            start, end = citation.get("start"), citation.get("end")
            if not isinstance(start, int) or not isinstance(end, int):
                raise ValueError(f"citation {index} offsets must be integers")
            if start < 0 or end <= start or segment["text"][start:end] != citation["evidence"]:
                raise ValueError(f"citation {index} offsets do not locate its evidence")
        known_instrument_keys.update(citation["instrument_keys"])

    links = response.get("unresolved_identity_links")
    if not isinstance(links, list):
        raise ValueError("unresolved_identity_links must be a list")
    seen_links: set[tuple[str, str]] = set()
    for index, link in enumerate(links):
        if not isinstance(link, dict):
            raise ValueError(f"identity link {index} must be an object")
        missing = {"left_instrument_key", "right_instrument_key", "reason"} - set(link)
        if missing:
            raise ValueError(f"identity link {index} missing fields: {sorted(missing)}")
        left, right = link["left_instrument_key"], link["right_instrument_key"]
        if not all(isinstance(value, str) and value for value in (left, right, link["reason"])):
            raise ValueError(f"identity link {index} fields must be nonempty strings")
        if left == right or left not in known_instrument_keys or right not in known_instrument_keys:
            raise ValueError(f"identity link {index} must connect two distinct cited instrument keys")
        pair = tuple(sorted((left, right)))
        if pair in seen_links:
            raise ValueError(f"duplicate unresolved identity link at index {index}")
        seen_links.add(pair)


def entity_set(citations: list[dict], level: str) -> set[tuple[str, str]]:
    key = "instrument_keys" if level == "instrument" else "provision_keys"
    return {
        (citation["region"], value)
        for citation in citations if not citation.get("excluded")
        for value in citation.get(key, [])
    }
