#!/usr/bin/env python3
"""Build the authority-safe high-confidence parent-child pilot."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from precedent_preprocess import (  # noqa: E402
    mask_authorities,
    remove_similarity_boilerplate,
    remove_vesting_clauses,
)


CORPORA = (
    ROOT / "data/4_28_2026_build_dev.csv",
    ROOT / "data/4_28_2026_build_holdout.csv",
)
DOCUMENTS = ROOT / "data/parent_analysis_all_corpus/directive_similarity_documents.jsonl"
EXCLUSIONS = ROOT / "data/parent_analysis_all_corpus/ceremonial_exclusions.csv"
AUTOMATIC_EDGES = ROOT / "data/parent_analysis_all_corpus/automatic_edges.csv"
PROFILES = ROOT / "data/parent_analysis/canonical_profiles/profiles.jsonl"
PROFILE_MANIFEST = ROOT / "data/parent_analysis/canonical_profiles/snapshot_manifest.json"
FUNCTION_EMBEDDINGS = ROOT / "data/parent_analysis/canonical_profiles/function_embeddings.npz"
DOCUMENT_EMBEDDINGS = ROOT / "data/parent_analysis/embeddings/directive_document_embeddings.npz"
PRIOR_REVIEW = (
    ROOT / "data/parent_analysis/function_parent_pilot/eo_pilot_20_v2/"
    "function-parent-review-06814d11698b.json"
)
DEFAULT_OUTPUT = HERE / "outputs"

EXPECTED_NONCEREMONIAL = 13_461
SHINGLE_SIZE = 10
SEED = 20260823
DESCRIPTIVE_CUTOFFS = (0.90, 0.95, 0.975)
# These relation labels identify an explicit transition from a named earlier
# directive. Such edges are observed parent-child relationships, not candidates
# for inference from copied distinctive language.
EXPLICIT_PARENT_RELATIONS = frozenset({
    "amends", "continues", "modifies", "replaces", "revokes", "supersedes",
})

TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)*")
IEEPA_RE = re.compile(r"\b(?:IEEPA|International Emergency Economic Powers Act)\b", re.I)
IEEPA_LIFECYCLE_RE = re.compile(
    r"\b(?:block|freeze|prohibit|restrict|regulate|suspend|impose|sanction|tariff|"
    r"terminate|revoke|declare|proclaim|report|notify|transmit)\w*\b",
    re.I,
)
IEEPA_REPORTING_RE = re.compile(
    r"\bI\s+(?:hereby\s+)?(?:report|transmit|notify)\b",
    re.I,
)
BLOCK_RE = re.compile(
    r"\b(?:block|freeze)\w*\b.{0,180}\b(?:property|interests? in property|assets?)\b|"
    r"\b(?:property|interests? in property|assets?)\b.{0,180}"
    r"\b(?:blocked|frozen|may not be transferred)\b",
    re.I | re.S,
)
BLOCK_NONACTION_RE = re.compile(
    r"\bif\b.{0,100}\b(?:property|assets?|interests?\s+in\s+property)\b.{0,80}"
    r"\b(?:are|is|were|was|be)\s+(?:blocked|frozen)\b|"
    r"\b(?:risk|could|would|might|may)\b.{0,100}\b(?:blocking|freezing|blocked|frozen)\b",
    re.I | re.S,
)
SANCTIONS_RESTRICTION_RE = re.compile(
    r"\b(?:I\s+(?:hereby\s+)?(?:prohibit|ban|restrict|suspend|block|freeze)|"
    r"(?:all|any|the\s+following|covered|specified)\s+(?:property|interests?\s+in\s+property|"
    r"assets?|imports?|exports?|transactions?|transfers?|investments?|trade|entry|dealings?|"
    r"goods|articles|products)\b.{0,180}\b(?:are|is|shall\s+be)\s+"
    r"(?:prohibited|banned|restricted|suspended|blocked|frozen)|"
    r"\b(?:importation|exportation|entry|transfer|dealing(?:s)?|transaction(?:s)?)\b.{0,180}"
    r"\b(?:are|is|shall\s+be)\s+(?:prohibited|banned|restricted|suspended|blocked|frozen))\b",
    re.I | re.S,
)
FORMAL_EMERGENCY_RE = re.compile(
    r"\b(?:I\s+(?:hereby\s+)?(?:declare|proclaim|continue|extend|renew|terminate|revoke|"
    r"modify|amend)|(?:hereby\s+)?(?:declare|proclaim|continue|extend|renew|terminate|revoke|"
    r"modify|amend))\b.{0,120}\b(?:national\s+)?emergency\b|"
    r"\b(?:national\s+)?emergency\b.{0,120}\b(?:is|are)\s+(?:hereby\s+)?"
    r"(?:declared|proclaimed|continued|extended|renewed|terminated|revoked|modified|amended)\b|"
    r"\b(?:notice|report|transmit|Congress|Federal\s+Register)\b.{0,500}"
    r"\b(?:national\s+)?emergency\b.{0,180}"
    r"\b(?:is\s+to\s+)?continu\w*(?:\s+in\s+effect)?\b",
    re.I | re.S,
)
EMERGENCY_NONACTION_RE = re.compile(
    r"\b(?:was|(?:(?:exclusive\s+of|except\s+for)\s+)?the\s+authority)\s+to\s+"
    r"declare\b.{0,80}\b(?:national\s+)?emergency\b|"
    r"\b(?:extend|continue)\w*\b.{0,120}\bemergency\s+"
    r"(?:assistance|relief|credit|situations?|programs?|basis)\b|"
    r"\bcontinue\w*\b.{0,120}\b(?:assist(?:ing)?\s+in|cope\s+with)\s+the\s+emergency\b",
    re.I | re.S,
)
MONUMENT_RE = re.compile(
    r"\b(?:establish|proclaim|designat|reserv|enlarg|reduc|modif)\w*\b.{0,180}"
    r"\bnational monument\b|\bnational monument\b.{0,180}"
    r"\b(?:established|proclaimed|designated|reserved|enlarged|reduced|modified)\b",
    re.I | re.S,
)
TRADE_MECHANISM_RE = re.compile(
    r"\b(?:tariff|HTSUS|harmonized tariff schedule|dut(?:y|ies)|quota|"
    r"quantitative limitation|generalized system of preferences|trade agreement|"
    r"import treatment|duty-free)\b",
    re.I,
)
TRADE_ACTION_RE = re.compile(
    r"\b(?:adjust|modify|impose|increase|decrease|suspend|continue|terminate|withdraw|"
    r"designate|exclude|include|implement|proclaim|provide)\w*\b",
    re.I,
)
STRICT_VESTING_START_RE = re.compile(
    r"\b(?:by\s+(?:virtue\s+of\s+)?|under\s+(?:and\s+by\s+virtue\s+of\s+)?|"
    r"acting\s+under\s+|pursuant\s+to\s+|consistent\s+with\s+)"
    r"(?:the\s+)?authority\s+vested\s+in\s+me\b",
    re.I,
)
EXTENDED_VESTING_CONNECTOR_RE = re.compile(
    r"\bI\s+(?:do\s+)?(?:(?:hereby|thereby)\s+)?"
    r"(?:amend|approve|proclaim|order|declare|direct|continue|extend|terminate|modify|"
    r"determine|find|establish|designate|reserve)\w*\b|"
    r"\b(?:(?:do\s+)(?:(?:hereby|thereby)\s+)?|(?:hereby|thereby)\s+)"
    r"(?:amend|approve|proclaim|order|declare|direct|continue|extend|terminate|modify|"
    r"determine|find|establish|designate|reserve)\w*\b",
    re.I,
)
LOOSE_TERMS = {
    "ieepa_action": IEEPA_RE,
    "property_blocking": re.compile(
        r"\b(?:block\w*|freez\w*|property interests?|sanction\w*|"
        r"prohibit\w*\s+(?:certain\s+)?imports?)\b", re.I,
    ),
    "emergency_action": re.compile(r"\b(?:national\s+)?emergency\b", re.I),
    "national_monument_action": re.compile(r"\bnational monument\b", re.I),
    "trade_proclamation": TRADE_MECHANISM_RE,
}
FAMILY_ORDER = tuple(LOOSE_TERMS)
PERSONAL_CORRESPONDENCE_TITLE_RE = re.compile(
    r"\b(?:birthday|congratul|condolen|sympath|greetings?|best\s+wishes|"
    r"personal\s+message|invitation|exchange\s+(?:of\s+)?letters?|expressing\s+confidence|"
    r"letter\s+of\s+(?:thanks|appreciation)|(?:accepting|acceptance\s+of)\s+"
    r"(?:the\s+)?resignation|united\s+nations|secretary\s+general|prime\s+minister|"
    r"foreign\s+minister|ambassador|\b(?:king|queen|pope)\b)\b",
    re.I,
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def explicit_parent_edges(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep resolved direct-transition references as automatic parent-child edges."""
    return [row for row in rows if row.get("relation") in EXPLICIT_PARENT_RELATIONS]


def explicit_parent_child_ids(rows: list[dict[str, str]]) -> set[str]:
    return {row["child_id"] for row in explicit_parent_edges(rows)}


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_key(value: str, seed: int = SEED) -> str:
    return hashlib.sha256(f"{seed}:{value}".encode()).hexdigest()


def parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%B %d, %Y")


def words(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN_RE.findall(text)]


def shingles(text: str, size: int = SHINGLE_SIZE) -> set[tuple[str, ...]]:
    tokens = words(text)
    return {tuple(tokens[i : i + size]) for i in range(len(tokens) - size + 1)}


def remove_residual_formal_vesting(text: str) -> tuple[str, list[str]]:
    """Remove formal clauses missed by the conservative shared preprocessor.

    The shared parent pipeline deliberately preserves possible historical mentions.
    Here we remove a residual span only when an authority formula is followed in the same
    source paragraph by a presidential performative such as ``I continue``, ``do
    proclaim``.  The shared preprocessor also removes statutory lead-ins common in
    congressional reporting letters.  Historical text such as ``I issued Executive Order
    ...`` remains permitted outside-clause authority language.
    """
    parts = re.split(r"( {2,})", text)
    removed = []
    for index in range(0, len(parts), 2):
        paragraph = parts[index]
        while True:
            start = STRICT_VESTING_START_RE.search(paragraph)
            if not start:
                break
            connector = EXTENDED_VESTING_CONNECTOR_RE.search(paragraph, start.end())
            if not connector:
                break
            removed.append(paragraph[start.start() : connector.start()].strip(" ,;:"))
            paragraph = (
                paragraph[: start.start()] + "[VESTING_CLAUSE_REMOVED] "
                + paragraph[connector.start() :]
            )
        parts[index] = paragraph
    return "".join(parts).strip(), removed


def preprocess_text(text: str) -> tuple[str, str, list[str], list[str]]:
    """Return primary, robustness, vesting removals, and boilerplate removals."""
    # Apply the extended connector set first so older ``do proclaim`` formulas retain
    # their operative connector rather than looking malformed to the shared parser.
    text, residual = remove_residual_formal_vesting(text)
    without_vesting, vesting = remove_vesting_clauses(text)
    vesting = residual + vesting
    primary, boilerplate = remove_similarity_boilerplate(without_vesting)
    robustness, _ = mask_authorities(primary)
    return primary, robustness, vesting, boilerplate


def function_windows(profile: dict | None) -> list[str]:
    if not profile:
        return []
    output = []
    for function in profile.get("operative_functions", []):
        output.append(" | ".join(str(function.get(field, "")) for field in (
            "label", "action", "target", "mechanism", "effect", "evidence"
        )))
    return output


def body_windows(text: str) -> list[str]:
    return [part.strip() for part in re.split(r" {2,}|(?<=[.;])\s+", text) if part.strip()]


def analysis_scope_reason(document: dict) -> str:
    """Return a conservative exclusion for correspondence outside directive drafting."""
    if document["document_type"] != "letter":
        return ""
    if PERSONAL_CORRESPONDENCE_TITLE_RE.search(document["title"]):
        return "personal_or_diplomatic_correspondence"
    return ""


def _same_window(windows: Iterable[str], first: re.Pattern, second: re.Pattern) -> bool:
    return any(first.search(window) and second.search(window) for window in windows)


def family_matches(document: dict, profile: dict | None) -> dict[str, str]:
    """Return overlapping proposed family labels and action subtypes."""
    title = document["title"]
    text = document["primary_text"]
    # Family coding is text-based.  Frozen profiles remain a parent-score input, but
    # inferred profile actions are not evidence that a directive belongs to a family.
    windows = [title] + body_windows(text)
    all_allowed = f"{title} {text}"
    labels: dict[str, str] = {}
    ieepa_same_window = any(
        IEEPA_RE.search(window) and IEEPA_LIFECYCLE_RE.search(window)
        for window in windows
    )
    ieepa_reporting_letter = (
        document["document_type"] == "letter"
        and IEEPA_RE.search(all_allowed)
        and IEEPA_REPORTING_RE.search(all_allowed)
    )
    if ieepa_same_window or ieepa_reporting_letter:
        labels["ieepa_action"] = (
            "ieepa_reporting_action" if ieepa_reporting_letter else "ieepa_lifecycle_action"
        )
    blocking_window = next((
        x for x in windows
        if (
            BLOCK_RE.search(BLOCK_NONACTION_RE.sub("[NONACTION]", x))
            or SANCTIONS_RESTRICTION_RE.search(BLOCK_NONACTION_RE.sub("[NONACTION]", x))
        )
    ), "")
    if blocking_window:
        labels["property_blocking"] = (
            "property_blocking" if BLOCK_RE.search(blocking_window) else "sanctions_restriction"
        )
    # Remove two adjudicated non-action constructions before applying the broad
    # historical grammar.  This preserves older reporting and declaration forms.
    emergency_window = next((
        x for x in windows
        if FORMAL_EMERGENCY_RE.search(EMERGENCY_NONACTION_RE.sub("[NONACTION]", x))
    ), "")
    if emergency_window:
        lower = emergency_window.casefold()
        labels["emergency_action"] = (
            "termination" if re.search(r"terminat|revok", lower) else
            "continuation" if re.search(r"continu|extend", lower) else
            "modification" if re.search(r"expand|modif", lower) else
            "declaration"
        )
    monument_window = next((x for x in windows if MONUMENT_RE.search(x)), "")
    if monument_window:
        lower = monument_window.casefold()
        labels["national_monument_action"] = (
            "modification" if re.search(r"enlarg|reduc|modif", lower) else "establishment"
        )
    if document["document_type"] == "proclamation" and _same_window(
        windows, TRADE_ACTION_RE, TRADE_MECHANISM_RE
    ):
        labels["trade_proclamation"] = "trade_adjustment"
    return labels


def loose_family_matches(document: dict) -> set[str]:
    allowed = f"{document['title']} {document['primary_text']}"
    return {
        family for family, pattern in LOOSE_TERMS.items()
        if (family != "trade_proclamation" or document["document_type"] == "proclamation")
        and pattern.search(allowed)
    }


def excerpt(text: str, pattern: re.Pattern | None = None, width: int = 1200) -> str:
    match = pattern.search(text) if pattern else None
    start = max(0, match.start() - width // 3) if match else 0
    return text[start : start + width].strip()


def balanced_sample(rows: list[dict], count: int, group_fields: tuple[str, ...], salt: str) -> list[dict]:
    groups: dict[tuple[str, ...], list[dict]] = defaultdict(list)
    for row in rows:
        groups[tuple(str(row.get(field, "")) for field in group_fields)].append(row)
    for key in groups:
        groups[key].sort(key=lambda row: stable_key(f"{salt}:{row['document_id']}"))
    selected: list[dict] = []
    keys = sorted(groups)
    while len(selected) < count and keys:
        remaining = []
        for key in keys:
            if groups[key] and len(selected) < count:
                selected.append(groups[key].pop(0))
            if groups[key]:
                remaining.append(key)
        keys = remaining
    return selected


def midrank_percentiles(values: np.ndarray) -> np.ndarray:
    if not len(values):
        return np.asarray([], dtype=np.float64)
    ordered = np.sort(values)
    left = np.searchsorted(ordered, values, side="left")
    right = np.searchsorted(ordered, values, side="right")
    return (left + right) / (2.0 * len(values))


def build_lexical_scores(
    documents: list[dict], child_ids: list[str], text_field: str, size: int = SHINGLE_SIZE,
) -> dict[str, np.ndarray]:
    """Compute exact IDF-weighted shingle containment for selected children."""
    child_sets = {did: shingles(documents_by_id(documents)[did][text_field], size) for did in child_ids}
    wanted: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for did, grams in child_sets.items():
        for gram in sorted(grams):
            wanted[gram].append(did)
    df = Counter()
    for document in documents:
        for gram in sorted(shingles(document[text_field], size)):
            if gram in wanted:
                df[gram] += 1
    n = len(documents)
    weights = {gram: math.log((n + 1) / (freq + 1)) + 1.0 for gram, freq in df.items()}
    denominators = {
        did: sum(weights.get(gram, math.log((n + 1) / 2) + 1.0) for gram in sorted(grams))
        for did, grams in child_sets.items()
    }
    output = {did: np.zeros(n, dtype=np.float32) for did in child_ids}
    for document_index, document in enumerate(documents):
        totals: dict[str, float] = defaultdict(float)
        for gram in sorted(shingles(document[text_field], size)):
            weight = weights.get(gram)
            if weight is None:
                continue
            for child_id in wanted[gram]:
                totals[child_id] += weight
        for child_id, total in totals.items():
            denominator = denominators[child_id]
            if denominator:
                output[child_id][document_index] = total / denominator
    return output


def documents_by_id(documents: list[dict]) -> dict[str, dict]:
    return {str(row["document_id"]): row for row in documents}


class FunctionSimilarity:
    def __init__(self, path: Path):
        with np.load(path) as cache:
            self.snapshot_hash = str(cache["snapshot_hash"].item())
            document_ids = cache["document_ids"].astype(str)
            kinds = cache["kinds"].astype(str)
            self.query = cache["query_embeddings"].astype(np.float32)
            self.parent = cache["document_embeddings"].astype(np.float32)
        self.child_indices: dict[str, list[int]] = defaultdict(list)
        parent_groups: dict[str, list[int]] = defaultdict(list)
        for index, (document_id, kind) in enumerate(zip(document_ids, kinds, strict=True)):
            if kind == "operative":
                self.child_indices[document_id].append(index)
                parent_groups[document_id].append(index)
        self.parent_ids = sorted(parent_groups, key=int)
        groups = [parent_groups[did] for did in self.parent_ids]
        self.flat_indices = np.asarray([i for group in groups for i in group], dtype=np.int64)
        self.starts = np.cumsum([0] + [len(group) for group in groups[:-1]], dtype=np.int64)

    def scores(self, child_id: str) -> tuple[list[str], np.ndarray] | None:
        child = self.child_indices.get(child_id, [])
        if not child or not len(self.flat_indices):
            return None
        matrix = self.query[child] @ self.parent[self.flat_indices].T
        values = np.maximum.reduceat(matrix, self.starts, axis=1).mean(axis=0)
        return self.parent_ids, values.astype(np.float32)


class DocumentSimilarity:
    def __init__(self, path: Path):
        with np.load(path) as cache:
            self.ids = cache["ids"].astype(str).tolist()
            self.query = cache["query_embeddings"].astype(np.float32)
            self.parent = cache["document_embeddings"].astype(np.float32)
        self.index = {did: i for i, did in enumerate(self.ids)}

    def scores(self, child_id: str) -> tuple[list[str], np.ndarray] | None:
        child_index = self.index.get(child_id)
        if child_index is None:
            return None
        return self.ids, self.parent @ self.query[child_index]


def load_documents() -> tuple[list[dict], dict]:
    excluded = {row["document_id"] for row in read_csv(EXCLUSIONS)}
    metadata = documents_by_id(read_jsonl(DOCUMENTS))
    corpus = []
    for path in CORPORA:
        corpus.extend(read_csv(path))
    if len({row[""] for row in corpus}) != len(corpus):
        raise ValueError("combined corpus contains duplicate document IDs")
    output = []
    vesting_removed = 0
    for row in corpus:
        document_id = row[""]
        if document_id in excluded:
            continue
        primary, robustness, vesting, boilerplate = preprocess_text(row["doc_text"])
        if vesting:
            vesting_removed += 1
        meta = metadata[document_id]
        output.append({
            "document_id": document_id,
            "document_type": row["doc_type"],
            "date": row["date"],
            "parsed_date": parse_date(row["date"]),
            "president": row["president"],
            "term": row["term"],
            "url": row["url"],
            "title": meta["title"],
            "primary_text": primary,
            "robustness_text": robustness,
            "vesting_removed_count": len(vesting),
            "boilerplate_removed_count": len(boilerplate),
            "analysis_scope_reason": "",
        })
    output.sort(key=lambda row: int(row["document_id"]))
    for document in output:
        document["analysis_scope_reason"] = analysis_scope_reason(document)
    if len(output) != EXPECTED_NONCEREMONIAL:
        raise ValueError(f"expected {EXPECTED_NONCEREMONIAL} non-ceremonial documents, found {len(output)}")
    return output, {"source_documents": len(corpus), "vesting_removed_documents": vesting_removed}


def load_profiles() -> dict[str, dict]:
    profiles = {}
    for row in read_jsonl(PROFILES):
        did = str(row["document_id"])
        if did in profiles:
            raise ValueError(f"duplicate profile {did}")
        profiles[did] = row["profile"]
    return profiles


def assign_families(documents: list[dict], profiles: dict[str, dict]) -> None:
    for document in documents:
        labels = family_matches(document, profiles.get(document["document_id"]))
        document["families"] = labels
        document["loose_families"] = loose_family_matches(document)


def build_family_review(
    documents: list[dict], *, proposed_count: int = 12, boundary_count: int = 8,
    excluded_document_ids: set[str] | None = None, sample_salt: str = "family_development_v1",
    review_id_prefix: str = "F",
) -> list[dict]:
    """Build a blinded family-review queue with deterministic stratified sampling."""
    excluded_document_ids = excluded_document_ids or set()
    rows = []
    for family in FAMILY_ORDER:
        proposed = [
            row for row in documents
            if str(row["document_id"]) not in excluded_document_ids and family in row["families"]
        ]
        boundary = [
            row for row in documents
            if str(row["document_id"]) not in excluded_document_ids
            and family in row["loose_families"] and family not in row["families"]
        ]
        chosen = [
            ("proposed", row) for row in balanced_sample(
                proposed, proposed_count, ("president", "document_type"),
                f"{sample_salt}:{family}:proposed",
            )
        ] + [
            ("boundary", row) for row in balanced_sample(
                boundary, boundary_count, ("president", "document_type"),
                f"{sample_salt}:{family}:boundary",
            )
        ]
        for queue_type, row in chosen:
            rows.append({
                "review_id": f"{review_id_prefix}-{family}-{row['document_id']}",
                "family_id": family,
                "queue_type": queue_type,
                "document_id": row["document_id"],
                "president": row["president"],
                "date": row["date"],
                "document_type": row["document_type"],
                "title": row["title"],
                "url": row["url"],
                # Family membership often turns on context outside a short keyword
                # window.  The reviewer receives the full already-preprocessed
                # primary text: no vesting clause and no generic-form boilerplate.
                "non_vesting_text": row["primary_text"],
                "decision": "",
                "review_notes": "",
            })
    return rows


def scorable_ids(function: FunctionSimilarity, document: DocumentSimilarity) -> set[str]:
    return set(function.child_indices) | set(document.index)


def select_pilot(
    documents: list[dict], scorable: set[str], eligible_document_ids: set[str],
    inference_child_ids: set[str],
) -> list[str]:
    family_dates: dict[str, list[datetime]] = defaultdict(list)
    for row in documents:
        if row["document_id"] not in eligible_document_ids:
            continue
        for family in row["families"]:
            family_dates[family].append(row["parsed_date"])
    selected: set[str] = set()
    for family in FAMILY_ORDER:
        candidates = [
            row for row in documents
            if family in row["families"] and row["document_id"] in scorable
            and row["document_id"] in inference_child_ids
            and any(date < row["parsed_date"] for date in family_dates[family])
        ]
        for row in balanced_sample(
            candidates, 50, ("president", "document_type"), f"pilot:{family}"
        ):
            selected.add(row["document_id"])
    earliest_date = min(
        row["parsed_date"] for row in documents if row["document_id"] in eligible_document_ids
    )
    noncontrol = [
        row for row in documents
        if not row["families"] and row["document_id"] in scorable
        and row["document_id"] in inference_child_ids
        and earliest_date < row["parsed_date"]
    ]
    for row in balanced_sample(
        noncontrol, 250, ("document_type", "president"), "pilot:noncontrol"
    ):
        selected.add(row["document_id"])
    return sorted(selected, key=int)


def semantic_array(
    child_id: str,
    documents: list[dict],
    scorer: FunctionSimilarity | DocumentSimilarity,
) -> np.ndarray | None:
    result = scorer.scores(child_id)
    if result is None:
        return None
    candidate_ids, values = result
    index = {row["document_id"]: i for i, row in enumerate(documents)}
    output = np.full(len(documents), np.nan, dtype=np.float32)
    for did, value in zip(candidate_ids, values, strict=True):
        position = index.get(did)
        if position is not None:
            output[position] = value
    return output


def score_children(
    documents: list[dict],
    child_ids: list[str],
    lexical_by_spec: dict[str, dict[str, np.ndarray]],
    function: FunctionSimilarity,
    document: DocumentSimilarity,
    eligible_parent_ids: set[str],
) -> list[dict]:
    by_id = documents_by_id(documents)
    dates = np.asarray([row["parsed_date"].timestamp() for row in documents])
    ids = np.asarray([row["document_id"] for row in documents])
    parent_scope_mask = np.asarray([row["document_id"] in eligible_parent_ids for row in documents])
    rows = []
    for child_id in child_ids:
        child = by_id[child_id]
        if child_id in function.child_indices:
            stratum = "operative_profile"
            semantic = semantic_array(child_id, documents, function)
        else:
            stratum = "document_semantic"
            semantic = semantic_array(child_id, documents, document)
        if semantic is None:
            rows.append({
                "child_id": child_id, "parent_id": "", "specification": "primary",
                "score_stratum": "unscored", "unscored_reason": "no compatible frozen embedding",
            })
            continue
        eligible = (
            (dates < child["parsed_date"].timestamp()) & np.isfinite(semantic) & parent_scope_mask
        )
        if not eligible.any():
            rows.append({
                "child_id": child_id, "parent_id": "", "specification": "primary",
                "score_stratum": "unscored", "unscored_reason": "no strictly earlier embedded parent",
            })
            continue
        eligible_positions = np.flatnonzero(eligible)
        semantic_percentiles = midrank_percentiles(semantic[eligible])
        for specification in ("primary", "robustness"):
            lexical = lexical_by_spec[specification][child_id]
            lexical_percentiles = midrank_percentiles(lexical[eligible])
            combined = 0.5 * lexical_percentiles + 0.5 * semantic_percentiles
            order = np.lexsort((ids[eligible_positions].astype(int), -combined))
            best_local = int(order[0])
            parent_position = int(eligible_positions[best_local])
            parent = documents[parent_position]
            child_families = set(child["families"])
            parent_families = set(parent["families"])
            within = {}
            for family in sorted(child_families):
                family_local = [
                    i for i, position in enumerate(eligible_positions)
                    if family in documents[int(position)]["families"]
                ]
                if family_local:
                    winner = min(
                        family_local,
                        key=lambda i: (-float(combined[i]), int(ids[eligible_positions[i]])),
                    )
                    within[family] = {
                        "parent_id": str(ids[eligible_positions[winner]]),
                        "score": float(combined[winner]),
                    }
            rows.append({
                "child_id": child_id,
                "parent_id": parent["document_id"],
                "specification": specification,
                "score_stratum": stratum,
                "child_date": child["date"],
                "parent_date": parent["date"],
                "child_document_type": child["document_type"],
                "parent_document_type": parent["document_type"],
                "child_president": child["president"],
                "parent_president": parent["president"],
                "lexical_score": float(lexical[parent_position]),
                "lexical_percentile": float(lexical_percentiles[best_local]),
                "semantic_score": float(semantic[parent_position]),
                "semantic_percentile": float(semantic_percentiles[best_local]),
                "combined_score": float(combined[best_local]),
                "eligible_parent_count": int(eligible.sum()),
                "child_families": "|".join(sorted(child_families)),
                "parent_families": "|".join(sorted(parent_families)),
                "shared_families": "|".join(sorted(child_families & parent_families)),
                "within_family_best": json.dumps(within, sort_keys=True),
                "child_link_status": "inferred_no_explicit_transition",
                "unscored_reason": "",
            })
    return rows


def build_top_candidate_sets(
    documents: list[dict], child_ids: list[str], lexical10: dict[str, np.ndarray],
    lexical5: dict[str, np.ndarray], function: FunctionSimilarity,
    document: DocumentSimilarity, eligible_parent_ids: set[str], top_k: int = 5,
) -> list[dict]:
    """Return top-k candidates under the three frozen deterministic specifications."""
    by_id = documents_by_id(documents)
    dates = np.asarray([row["parsed_date"].timestamp() for row in documents])
    ids = np.asarray([row["document_id"] for row in documents])
    parent_scope = np.asarray([row["document_id"] in eligible_parent_ids for row in documents])
    output = []
    for child_id in child_ids:
        child = by_id[child_id]
        scorer = function if child_id in function.child_indices else document
        stratum = "operative_profile" if scorer is function else "document_semantic"
        semantic = semantic_array(child_id, documents, scorer)
        if semantic is None:
            continue
        eligible = (
            (dates < child["parsed_date"].timestamp()) & np.isfinite(semantic) & parent_scope
        )
        positions = np.flatnonzero(eligible)
        if not len(positions):
            continue
        lex5_raw, lex10_raw, semantic_raw = (
            lexical5[child_id][eligible], lexical10[child_id][eligible], semantic[eligible]
        )
        lex5_pct = midrank_percentiles(lex5_raw)
        lex10_pct = midrank_percentiles(lex10_raw)
        semantic_pct = midrank_percentiles(semantic_raw)
        methods = {
            "word_5_shingle": lex5_raw,
            "hybrid_10_semantic": 0.5 * lex10_pct + 0.5 * semantic_pct,
            "hybrid_5_semantic": 0.5 * lex5_pct + 0.5 * semantic_pct,
        }
        child_families = set(child["families"])
        for method, values in methods.items():
            order = np.lexsort((ids[positions].astype(int), -values))[:top_k]
            for rank, local in enumerate(order, 1):
                parent = documents[int(positions[int(local)])]
                parent_families = set(parent["families"])
                output.append({
                    "child_id": child_id, "child_date": child["date"],
                    "child_title": child["title"], "child_families": "|".join(sorted(child_families)),
                    "score_stratum": stratum, "method": method, "candidate_rank": rank,
                    "parent_id": parent["document_id"], "parent_date": parent["date"],
                    "parent_title": parent["title"],
                    "parent_families": "|".join(sorted(parent_families)),
                    "shared_families": "|".join(sorted(child_families & parent_families)),
                    "method_score": float(values[int(local)]),
                    "lexical_5_score": float(lex5_raw[int(local)]),
                    "lexical_10_score": float(lex10_raw[int(local)]),
                    "semantic_score": float(semantic_raw[int(local)]),
                    "parent_url": parent["url"],
                })
    return output


def assign_quantile_bands(rows: list[dict], bands: int = 8) -> None:
    """Assign approximately equal-sized, deterministic bands within each score stratum."""
    by_stratum: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_stratum[row["score_stratum"]].append(row)
    for items in by_stratum.values():
        ordered = sorted(items, key=lambda row: (float(row["combined_score"]), int(row["child_id"])))
        for rank, row in enumerate(ordered):
            band = min(bands - 1, rank * bands // len(ordered))
            row["score_band"] = f"{band + 1:02d}_of_{bands:02d}"


def load_prior_reviews() -> dict[tuple[str, str], str]:
    if not PRIOR_REVIEW.is_file():
        return {}
    payload = json.loads(PRIOR_REVIEW.read_text())
    output = {}
    for child_id, case in payload.get("cases", {}).items():
        parent_id = str(case.get("selected_parent_id") or "")
        decision = case.get("decision", "")
        if parent_id and decision in {"candidate", "none"}:
            output[(str(child_id), parent_id)] = "parent" if decision == "candidate" else "not_parent"
    return output


def build_parent_review(
    scores: list[dict], documents: list[dict], count: int = 20
) -> tuple[list[dict], list[dict]]:
    by_id = documents_by_id(documents)
    prior = load_prior_reviews()
    candidates = []
    for row in scores:
        if row.get("specification") != "primary" or row.get("score_stratum") == "unscored":
            continue
        # The current phase tests retrieved parents only for the independently
        # identified high-confidence action families.  Non-family directives are
        # reserved for a later family-discovery workflow, not treated as failures.
        if not row.get("child_families"):
            continue
        item = dict(row)
        item["document_id"] = row["child_id"]
        candidates.append(item)
    assign_quantile_bands(candidates)
    selected = balanced_sample(
        candidates, count, ("score_stratum", "child_document_type", "score_band"), "parent-review"
    )
    group_totals = Counter(
        (row["score_stratum"], row["child_document_type"], row["score_band"])
        for row in candidates
    )
    group_selected = Counter(
        (row["score_stratum"], row["child_document_type"], row["score_band"])
        for row in selected
    )
    blinded, key = [], []
    for number, row in enumerate(selected, 1):
        child = by_id[row["child_id"]]
        parent = by_id[row["parent_id"]]
        pair_id = f"P{number:03d}"
        group = (row["score_stratum"], row["child_document_type"], row["score_band"])
        probability = group_selected[group] / group_totals[group]
        old = prior.get((row["child_id"], row["parent_id"]), "")
        blinded.append({
            "pair_id": pair_id,
            "child_id": child["document_id"],
            "child_title": child["title"],
            "child_date": child["date"],
            "child_type": child["document_type"],
            "child_url": child["url"],
            "child_non_vesting_text": child["primary_text"],
            "parent_id": parent["document_id"],
            "parent_title": parent["title"],
            "parent_date": parent["date"],
            "parent_type": parent["document_type"],
            "parent_url": parent["url"],
            "parent_non_vesting_text": parent["primary_text"],
            "decision": old,
            "review_notes": "",
        })
        key.append({
            "pair_id": pair_id,
            "child_id": row["child_id"],
            "parent_id": row["parent_id"],
            "score_stratum": row["score_stratum"],
            "score_band": row["score_band"],
            "combined_score": row["combined_score"],
            "sampling_probability": probability,
            "prior_compatible_review": old,
        })
    return blinded, key


def calibrate_thresholds(review_rows: list[dict], review_key: list[dict]) -> list[dict]:
    decisions = {row["pair_id"]: row.get("decision", "").strip().casefold() for row in review_rows}
    joined = []
    for row in review_key:
        decision = decisions.get(row["pair_id"], "")
        if decision not in {"parent", "not_parent"}:
            continue
        joined.append({**row, "is_parent": decision == "parent"})
    output = []
    for stratum in sorted({row["score_stratum"] for row in joined}):
        subset = [row for row in joined if row["score_stratum"] == stratum]
        thresholds = sorted({float(row["combined_score"]) for row in subset})
        for target in (0.90, 0.95):
            qualifying = []
            for threshold in thresholds:
                above = [row for row in subset if float(row["combined_score"]) >= threshold]
                if len(above) < 25:
                    continue
                weights = [1.0 / float(row["sampling_probability"]) for row in above]
                precision = sum(w * row["is_parent"] for w, row in zip(weights, above)) / sum(weights)
                if precision >= target:
                    qualifying.append((threshold, precision, len(above)))
            if qualifying:
                threshold, precision, reviewed = min(qualifying, key=lambda item: item[0])
                above = [row for row in subset if float(row["combined_score"]) >= threshold]
                rng = np.random.default_rng(SEED)
                bootstrap = []
                bands = defaultdict(list)
                for row in above:
                    bands[row.get("score_band", "all")].append(row)
                for _ in range(1000):
                    sample = []
                    for items in bands.values():
                        chosen = rng.integers(0, len(items), size=len(items))
                        sample.extend(items[int(index)] for index in chosen)
                    weights = [1.0 / float(row["sampling_probability"]) for row in sample]
                    bootstrap.append(
                        sum(w * row["is_parent"] for w, row in zip(weights, sample)) / sum(weights)
                    )
                output.append({
                    "score_stratum": stratum,
                    "target_precision": target,
                    "threshold": threshold,
                    "weighted_observed_precision": precision,
                    "precision_ci_low": float(np.quantile(bootstrap, 0.025)),
                    "precision_ci_high": float(np.quantile(bootstrap, 0.975)),
                    "reviewed_above_threshold": reviewed,
                    "status": "pilot_calibrated",
                })
            else:
                output.append({
                    "score_stratum": stratum,
                    "target_precision": target,
                    "threshold": "",
                    "weighted_observed_precision": "",
                    "precision_ci_low": "",
                    "precision_ci_high": "",
                    "reviewed_above_threshold": 0,
                    "status": "insufficient_review",
                })
    return output


def threshold_rows(calibration: list[dict], scores: list[dict]) -> list[tuple[str, str, float]]:
    rows = []
    for row in calibration:
        if row["status"] == "pilot_calibrated":
            rows.append((
                row["score_stratum"],
                f"observed_precision_{int(100 * float(row['target_precision']))}",
                float(row["threshold"]),
            ))
    if not rows:
        for stratum in ("operative_profile", "document_semantic"):
            values = [
                float(row["combined_score"])
                for row in scores
                if row.get("specification") == "primary" and row.get("score_stratum") == stratum
            ]
            for quantile in DESCRIPTIVE_CUTOFFS:
                if values:
                    cutoff = float(np.quantile(values, quantile))
                    rows.append((stratum, f"descriptive_top_score_quantile_{quantile:g}", cutoff))
    return rows


def family_parent_diagnostic_rows(scores: list[dict]) -> list[dict]:
    """State explicitly that the family-focused parent screen cannot calibrate population tiers."""
    strata = sorted({
        row["score_stratum"] for row in scores
        if row.get("score_stratum") not in {"", "unscored"}
    })
    return [
        {
            "score_stratum": stratum,
            "target_precision": target,
            "threshold": "",
            "weighted_observed_precision": "",
            "precision_ci_low": "",
            "precision_ci_high": "",
            "reviewed_above_threshold": 0,
            "status": "family_focused_diagnostic_not_calibration_sample",
        }
        for stratum in strata
        for target in (0.90, 0.95)
    ]


def build_summaries(
    scores: list[dict], documents: list[dict], calibration: list[dict],
    scoped_denominator: int, inference_child_ids: set[str],
) -> tuple[list[dict], list[dict]]:
    by_id = documents_by_id(documents)
    thresholds = threshold_rows(calibration, scores)
    coverage = []
    for specification in ("primary", "robustness"):
        for stratum, tier, cutoff in thresholds:
            qualifying = [
                row for row in scores
                if row.get("specification") == specification
                and row.get("score_stratum") == stratum
                and float(row.get("combined_score", -1)) >= cutoff
            ]
            coverage.append({
                "coverage_scope": "pilot_lower_bound_not_population_estimate",
                "specification": specification,
                "score_stratum": stratum,
                "tier": tier,
                "threshold": cutoff,
                "qualified_pilot_children": len(qualifying),
                "nonceremonial_denominator": EXPECTED_NONCEREMONIAL,
                "lower_bound_proportion": len(qualifying) / EXPECTED_NONCEREMONIAL,
                "scoped_directive_denominator": scoped_denominator,
                "scoped_lower_bound_proportion": len(qualifying) / scoped_denominator,
                "inference_eligible_directive_denominator": len(inference_child_ids),
                "inference_eligible_lower_bound_proportion": (
                    len(qualifying) / len(inference_child_ids)
                ),
            })
    validation = []
    primary = [row for row in scores if row.get("specification") == "primary"]
    for family in FAMILY_ORDER:
        family_members = [
            row for row in documents
            if family in row["families"] and not row["analysis_scope_reason"]
        ]
        for stratum, tier, cutoff in thresholds:
            eligible = []
            for row in primary:
                child = by_id[row["child_id"]]
                if (
                    row.get("score_stratum") != stratum or family not in child["families"]
                    or child["analysis_scope_reason"]
                    or child["document_id"] not in inference_child_ids
                ):
                    continue
                if any(
                    family in candidate["families"] and candidate["parsed_date"] < child["parsed_date"]
                    for candidate in family_members
                ):
                    eligible.append(row)
            recovered = [
                row for row in eligible
                if float(row.get("combined_score", -1)) >= cutoff
                and family in by_id[row["parent_id"]]["families"]
            ]
            validation.append({
                "family_id": family,
                "score_stratum": stratum,
                "tier": tier,
                "threshold": cutoff,
                "proposed_family_documents": len(family_members),
                "eligible_pilot_children": len(eligible),
                "same_family_recoveries": len(recovered),
                "recovery_rate": len(recovered) / len(eligible) if eligible else "",
                "administrations": len({row["president"] for row in family_members}),
                "first_date": min(family_members, key=lambda row: row["parsed_date"])["date"] if family_members else "",
                "last_date": max(family_members, key=lambda row: row["parsed_date"])["date"] if family_members else "",
                "label_status": "proposed_pending_blind_codebook_review",
            })
    return coverage, validation


def build_hc_union_summary(
    scores: list[dict], documents: list[dict], calibration: list[dict],
    scoped_denominator: int, inference_child_ids: set[str],
) -> list[dict]:
    """Primary diagnostic: recover any earlier HC-union member, irrespective of tag."""
    by_id = documents_by_id(documents)
    union_members = [
        row for row in documents if row["families"] and not row["analysis_scope_reason"]
    ]
    primary = [row for row in scores if row.get("specification") == "primary"]
    rows = []
    for stratum, tier, cutoff in threshold_rows(calibration, scores):
        eligible = []
        for score in primary:
            child = by_id[score["child_id"]]
            if (
                score.get("score_stratum") != stratum or not child["families"]
                or child["analysis_scope_reason"]
                or child["document_id"] not in inference_child_ids
            ):
                continue
            if any(parent["parsed_date"] < child["parsed_date"] for parent in union_members):
                eligible.append(score)
        recovered = [
            score for score in eligible
            if float(score.get("combined_score", -1)) >= cutoff
            and bool(by_id[score["parent_id"]]["families"])
        ]
        rows.append({
            "estimand": "any_high_confidence_category",
            "score_stratum": stratum,
            "tier": tier,
            "threshold": cutoff,
            "proposed_hc_union_documents": len(union_members),
            "nonceremonial_denominator": EXPECTED_NONCEREMONIAL,
            "scoped_directive_denominator": scoped_denominator,
            "inference_eligible_directive_denominator": len(inference_child_ids),
            "eligible_pilot_hc_union_children": len(eligible),
            "union_parent_recoveries": len(recovered),
            "union_recovery_rate": len(recovered) / len(eligible) if eligible else "",
            "administrations": len({row["president"] for row in union_members}),
            "first_date": min(union_members, key=lambda row: row["parsed_date"])["date"] if union_members else "",
            "last_date": max(union_members, key=lambda row: row["parsed_date"])["date"] if union_members else "",
            "label_status": "proposed_union_pending_blind_codebook_validation",
        })
    return rows


def build_components(scores: list[dict], documents: list[dict], quantile: float = 0.90) -> list[dict]:
    primary = [
        row for row in scores
        if row.get("specification") == "primary" and row.get("score_stratum") != "unscored"
    ]
    cutoffs = {
        stratum: float(np.quantile([
            float(row["combined_score"]) for row in primary if row["score_stratum"] == stratum
        ], quantile))
        for stratum in {row["score_stratum"] for row in primary}
    }
    edges = [
        (row["child_id"], row["parent_id"], float(row["combined_score"]))
        for row in primary
        if float(row["combined_score"]) >= cutoffs[row["score_stratum"]]
    ]
    adjacency: dict[str, set[str]] = defaultdict(set)
    edge_score = {}
    for child, parent, score in edges:
        adjacency[child].add(parent); adjacency[parent].add(child)
        edge_score[(child, parent)] = score
    seen, components = set(), []
    for node in sorted(adjacency, key=int):
        if node in seen:
            continue
        stack, members = [node], []
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current); members.append(current)
            stack.extend(adjacency[current] - seen)
        components.append(sorted(members, key=int))
    rows = []
    by_id = documents_by_id(documents)
    for number, members in enumerate(sorted(components, key=lambda x: (-len(x), int(x[0]))), 1):
        member_set = set(members)
        administrations = {by_id[did]["president"] for did in members}
        component_edges = [e for e in edges if e[0] in member_set and e[1] in member_set]
        for child, parent, score in component_edges:
            rows.append({
                "component_id": f"C{number:04d}", "component_size": len(members),
                "administration_count": len(administrations),
                "review_priority": str(len(members) >= 3 and len(administrations) >= 2).lower(),
                "child_id": child, "parent_id": parent, "combined_score": score,
            })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reviewed-pairs", type=Path)
    parser.add_argument("--parent-review-count", type=int, default=20)
    args = parser.parse_args()
    if not 20 <= args.parent_review_count <= 120:
        parser.error("--parent-review-count must be between 20 and 120")
    args.output.mkdir(parents=True, exist_ok=True)

    documents, source_audit = load_documents()
    profiles = load_profiles()
    assign_families(documents, profiles)
    eligible_document_ids = {
        row["document_id"] for row in documents if not row["analysis_scope_reason"]
    }
    all_reference_edges = read_csv(AUTOMATIC_EDGES)
    observed_parent_edges = explicit_parent_edges(all_reference_edges)
    observed_parent_children = explicit_parent_child_ids(all_reference_edges)
    inference_child_ids = eligible_document_ids - observed_parent_children
    function = FunctionSimilarity(FUNCTION_EMBEDDINGS)
    document = DocumentSimilarity(DOCUMENT_EMBEDDINGS)
    child_ids = select_pilot(
        documents, scorable_ids(function, document), eligible_document_ids, inference_child_ids
    )

    lexical_by_spec = {}
    for specification, field in (("primary", "primary_text"), ("robustness", "robustness_text")):
        lexical_by_spec[specification] = build_lexical_scores(documents, child_ids, field)
    lexical5_primary = build_lexical_scores(
        documents, child_ids, "primary_text", size=5
    )

    scores = score_children(
        documents, child_ids, lexical_by_spec, function, document, eligible_document_ids,
    )
    top_candidates = build_top_candidate_sets(
        documents, child_ids, lexical_by_spec["primary"], lexical5_primary,
        function, document, eligible_document_ids, top_k=5,
    )
    family_review = build_family_review(documents)
    family_review_key = [
        {
            "review_id": row["review_id"], "family_id": row["family_id"],
            "document_id": row["document_id"], "queue_type": row["queue_type"],
        }
        for row in family_review
    ]
    blinded_family_review = [
        {key: value for key, value in row.items() if key != "queue_type"}
        for row in family_review
    ]
    parent_review, parent_key = build_parent_review(scores, documents, args.parent_review_count)
    if args.reviewed_pairs:
        reviewed = read_csv(args.reviewed_pairs)
        completed = {row["pair_id"]: row for row in reviewed if row.get("pair_id")}
        for row in parent_review:
            prior = completed.get(row["pair_id"])
            if prior:
                row["decision"] = prior.get("decision", row["decision"])
                row["review_notes"] = prior.get("review_notes", row["review_notes"])
    else:
        reviewed = parent_review
    # The parent queue is deliberately sampled only from high-confidence families,
    # so its parent judgments cannot calibrate population-wide score thresholds.
    calibration = family_parent_diagnostic_rows(scores)
    coverage, validation = build_summaries(
        scores, documents, calibration, len(eligible_document_ids), inference_child_ids
    )
    union_summary = build_hc_union_summary(
        scores, documents, calibration, len(eligible_document_ids), inference_child_ids
    )
    components = build_components(scores, documents)

    score_fields = [
        "child_id", "parent_id", "specification", "score_stratum", "child_date", "parent_date",
        "child_document_type", "parent_document_type", "child_president", "parent_president",
        "lexical_score", "lexical_percentile", "semantic_score", "semantic_percentile",
        "combined_score", "eligible_parent_count", "child_families", "parent_families",
        "shared_families", "within_family_best", "child_link_status", "unscored_reason",
    ]
    write_csv(args.output / "document_scores.csv", scores, score_fields)
    write_csv(args.output / "top5_candidate_sets.csv", top_candidates)
    write_csv(args.output / "explicit_parent_child_edges.csv", observed_parent_edges)
    write_csv(args.output / "family_review_queue.csv", blinded_family_review)
    write_csv(args.output / "family_review_key.csv", family_review_key)
    write_csv(args.output / "parent_pair_review.csv", parent_review)
    write_csv(args.output / "parent_pair_review_key.csv", parent_key)
    write_csv(args.output / "threshold_calibration.csv", calibration, [
        "score_stratum", "target_precision", "threshold", "weighted_observed_precision",
        "precision_ci_low", "precision_ci_high", "reviewed_above_threshold", "status",
    ])
    write_csv(args.output / "coverage_summary.csv", coverage)
    write_csv(args.output / "family_validation.csv", validation)
    write_csv(args.output / "hc_union_summary.csv", union_summary)
    write_csv(args.output / "candidate_components.csv", components, [
        "component_id", "component_size", "administration_count", "review_priority",
        "child_id", "parent_id", "combined_score"
    ])

    output_files = sorted(path for path in args.output.iterdir() if path.is_file() and path.name != "manifest.json")
    snapshot = json.loads(PROFILE_MANIFEST.read_text())
    family_counts = Counter(family for row in documents for family in row["families"])
    manifest = {
        "schema_version": 1,
        "status": "family_parent_diagnostic",
        "seed": SEED,
        "nonceremonial_denominator": len(documents),
        "eligible_directive_denominator": len(eligible_document_ids),
        "inference_eligible_directive_denominator": len(inference_child_ids),
        "explicit_parent_child_edges": len(observed_parent_edges),
        "explicit_parent_child_children": len(observed_parent_children),
        "explicit_parent_child_relations": dict(sorted(Counter(
            row["relation"] for row in observed_parent_edges
        ).items())),
        "scope_exclusions": dict(Counter(
            row["analysis_scope_reason"] for row in documents if row["analysis_scope_reason"]
        )),
        "pilot_children": len(child_ids),
        "pilot_score_rows": len(scores),
        "family_review_rows": len(family_review),
        "parent_review_rows": len(parent_review),
        "family_counts_proposed": dict(sorted(family_counts.items())),
        "source_audit": source_audit,
        "profile_snapshot_hash": snapshot["snapshot_hash"],
        "profile_snapshot_complete": snapshot["complete"],
        "canonical_profiles": snapshot["canonical_profiles"],
        "operative_directives": snapshot["operative_directives"],
        "profiles_remaining": snapshot["requests_remaining"],
        "parameters": {
            "shingle_size": SHINGLE_SIZE,
            "score": "0.5 * lexical_midrank_percentile + 0.5 * semantic_midrank_percentile",
            "candidate_set_methods": [
                "word_5_shingle", "hybrid_10_semantic", "hybrid_5_semantic"
            ],
            "candidate_set_size": 5,
            "same_day_parents": "excluded",
            "parent_document_type": "unrestricted",
            "inference_child_scope": (
                "excludes children with resolved direct-transition references: "
                + ", ".join(sorted(EXPLICIT_PARENT_RELATIONS))
            ),
            "parent_review_scope": (
                "current high-confidence-family children only; not a population "
                "threshold-calibration sample"
            ),
            "descriptive_top_score_quantiles_when_uncalibrated": DESCRIPTIVE_CUTOFFS,
        },
        "inputs": {str(path.relative_to(ROOT)): sha256(path) for path in (
            *CORPORA, DOCUMENTS, EXCLUSIONS, AUTOMATIC_EDGES, PROFILES,
            PROFILE_MANIFEST, FUNCTION_EMBEDDINGS, DOCUMENT_EMBEDDINGS,
            HERE / "family_codebook.csv",
        )},
        "implementation": {
            "build_py_sha256": sha256(HERE / "build.py"),
        },
        "outputs": {path.name: sha256(path) for path in output_files},
    }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "documents": len(documents), "pilot_children": len(child_ids),
        "family_review": len(family_review), "parent_review": len(parent_review),
        "output": str(args.output),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
