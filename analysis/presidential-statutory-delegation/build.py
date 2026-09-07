#!/usr/bin/env python3
"""Build the presidential statutory-delegation citation inventory and reports.

The builder is network-free.  It reuses the project's formal vesting-clause carve,
keeps the statutory portion of ``SPECIFIC_RULES``, normalizes parallel citations,
and prepares one source packet per unique legal authority.  Model execution lives
in ``run_gpt56.py`` and is intentionally a separate, explicit step.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SRC = ROOT / "src"
RECIPIENT_DIR = HERE.parent / "delegation-recipient"
DEFAULT_OUTPUT = HERE / "outputs"
DEFAULT_CORPORA = (
    ROOT / "data" / "4_28_2026_build_dev.csv",
    ROOT / "data" / "4_28_2026_build_holdout.csv",
)
sys.path.insert(0, str(SRC))

from ceremonial import ceremonial_reason  # noqa: E402
from vesting_authority_stats import (  # noqa: E402
    SPECIFIC_RULES,
    extract_vesting_clauses,
    find_matches,
    load_corpus,
)


def _load_recipient_builder():
    spec = importlib.util.spec_from_file_location(
        "delegation_recipient_build_for_presidential_delegation",
        RECIPIENT_DIR / "build.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


RECIPIENT = _load_recipient_builder()

STATUTORY_RULES = {
    "usc", "legal_section", "legal_title", "legal_chapter", "public_law",
    "statutes_at_large", "congressional_measure", "named_act", "referenced_act",
    "referenced_statutory_provisions", "joint_resolution",
}
NONSTATUTORY_RULES = {rule.name for rule in SPECIFIC_RULES} - STATUTORY_RULES
RESOLVED_CLASSES = {"delegation", "nondelegation"}
ALL_CLASSES = RESOLVED_CLASSES | {"too_broad", "cannot_verify"}

# Legislative citation punctuation is inconsistent in the source corpus.  In
# particular, a Public Law number is often printed as ``94 - 580`` rather than
# ``94-580``; retain the complete number in either form.
PUBLIC_LAW_RE = re.compile(r"\b(?:Pub\.?\s*L\.?|Public\s+Law)(?:\s+No\.?)?\s+(\d+)\s*[-–—]\s*(\d+)\b", re.I)
STAT_RE = re.compile(r"\b(\d+)\s+Stat\.?\s+(\d+)(?:\s*[-–—]\s*(\d+))?\b", re.I)
SECTION_SIGNAL_RE = re.compile(
    r"\bsections?\s+\d+[A-Za-z]?(?:\s*\([A-Za-z0-9]+\))*", re.I
)
REVISED_STATUTES_RE = re.compile(
    r"\bsections?\s+(\d+[A-Za-z]?(?:\s*\([A-Za-z0-9]+\))*)\s+of\s+the\s+Revised\s+Statutes\b",
    re.I,
)
# The recipient extractor's original pattern recognizes ``Act of 1974`` but
# stopped before a full enactment date (``Act of June 8, 1906``).  Use the same
# grammar locally, with that date form included, so a dated Act remains whole.
ACT_SECTION_RE = re.compile(
    r"\bsections?\s+(?P<locators>\d+[A-Za-z]?(?:\s*\([A-Za-z0-9]+\))*"
    r"(?:\s*(?:,|and|or)\s*\d+[A-Za-z]?(?:\s*\([A-Za-z0-9]+\))*)*)"
    r"\s+of\s+(?P<act>(?:the\s+)?[^,;:]{2,180}?\bAct"
    r"(?:\s+of\s+(?:(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},\s*\d{4}|\d{4}))?)",
    re.I,
)
# These descriptions do not identify a particular statute outside their local
# text.  Year-only references are also ambiguous across different Acts.
GENERIC_ACT_SLUG_RE = re.compile(r"^(?:(?:the|this|that|said|such|an|any)-act|the-\d{4}-act)$", re.I)
# The formal inventory's compact named-Act rule intentionally excludes lowercase
# connector words and can thus return only the tail of a title (``Recovery Act``
# instead of ``Resource Conservation and Recovery Act``).  This supplemental
# matcher retains the complete title without treating punctuation as its end.
FULL_NAMED_ACT_RE = re.compile(
    r"\b(?:the\s+)?[A-Z][A-Za-z0-9'&.-]*"
    r"(?:\s+(?:[A-Z][A-Za-z0-9'&.-]*|and|of|the|for|to|on|with|in|as)){0,17}"
    r"\s+Act(?:\s+of\s+\d{4})?\b"
)
# Make the reused extractor consume this complete form as well.
RECIPIENT.ACT_SECTION_RE = ACT_SECTION_RE

OCCURRENCE_FIELDS = (
    "occurrence_id", "document_id", "date", "president", "term", "doc_type", "url",
    "clause_index", "raw_clause", "raw_citation", "citation_kind", "canonical_authority_id",
    "is_broad", "parallel_aliases", "specific_rules", "extraction_status", "equivalence_basis",
    "pre_crosswalk_authority_id",
)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, rows: list[dict], fields) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _item_span(clause: str, item: dict) -> tuple[int, int]:
    candidates = [item.get("raw_citation", ""), item.get("_source_raw_citation", ""),
                  *item.get("parallel_aliases", "").split(" | ")]
    spans = []
    for candidate in candidates:
        if not candidate:
            continue
        start = clause.casefold().find(candidate.casefold())
        if start >= 0:
            spans.append((start, start + len(candidate)))
    return (min(start for start, _ in spans), max(end for _, end in spans)) if spans else (-1, -1)


def _nearest(items: list[dict], span: tuple[int, int], max_distance: int = 180) -> list[dict]:
    if not items:
        return []
    center = sum(span) / 2
    distances = []
    for item in items:
        other = item.get("_span", (-1, -1))
        if other[0] < 0:
            continue
        distance = abs(center - sum(other) / 2)
        distances.append((distance, item))
    if not distances:
        return []
    minimum = min(distance for distance, _ in distances)
    return [item for distance, item in distances if distance == minimum and distance <= max_distance]


def _add_alias(item: dict, alias: str) -> None:
    aliases = [value for value in item.get("parallel_aliases", "").split(" | ") if value]
    if alias != item.get("raw_citation") and alias not in aliases:
        aliases.append(alias)
    item["parallel_aliases"] = " | ".join(aliases)


def _following_parenthetical(clause: str, end: int, limit: int = 300) -> tuple[int, int] | None:
    """Return an immediately following balanced citation parenthetical.

    Subsection locators inside a citation make a regex-only closing-parenthesis
    test unsafe.  This small scanner therefore balances parentheses and accepts
    only the punctuation/amendment language customarily printed between an Act
    name and its source-law parenthetical.
    """
    tail = clause[end:end + limit]
    prefix = re.match(r"\s*(?:,\s*)?(?:(?:as\s+amended|as\s+modified)\s*)?", tail, re.I)
    cursor = end + (prefix.end() if prefix else 0)
    if cursor >= len(clause) or clause[cursor] != "(":
        return None
    depth = 0
    for position in range(cursor, min(len(clause), end + limit)):
        if clause[position] == "(":
            depth += 1
        elif clause[position] == ")":
            depth -= 1
            if depth == 0:
                return cursor, position + 1
    return None


def _source_forms(text: str, offset: int = 0) -> list[tuple[str, str, tuple[int, int]]]:
    """Identify formal source-law forms and their absolute spans."""
    found = []
    for match in RECIPIENT.USC_GROUP_RE.finditer(text):
        found.append(("usc", match.group(0), (offset + match.start(), offset + match.end())))
    for match in PUBLIC_LAW_RE.finditer(text):
        found.append(("public_law", match.group(0), (offset + match.start(), offset + match.end())))
    for match in STAT_RE.finditer(text):
        found.append(("statutes_at_large", match.group(0), (offset + match.start(), offset + match.end())))
    return sorted(found, key=lambda value: value[2])


def _append_basis(item: dict, basis: str) -> None:
    values = [value for value in item.get("equivalence_basis", "").split(" | ") if value]
    if basis not in values:
        values.append(basis)
    item["equivalence_basis"] = " | ".join(values)


def _precise_alias_ids(raw: str) -> set[str]:
    """Return provision-level IDs literally encoded by a printed alias.

    Bare Act names are deliberately excluded: an Act title is not equivalent to
    one section of that Act.  This function is used only to propagate an
    equivalence already established by an explicit parallel-citation bundle.
    """
    value = raw.strip(" ,;:()")
    ids = set()
    act_match = ACT_SECTION_RE.fullmatch(value)
    if act_match:
        act = slug(normalize_space(act_match.group("act")))
        if not _is_contextual_act_slug(act):
            for locator in re.findall(r"\d+[A-Za-z]?(?:\s*\([A-Za-z0-9]+\))*", act_match.group("locators")):
                ids.add(f"act:{act}:{re.sub(r'\s+', '', locator).lower()}")
    for item in RECIPIENT.parse_clause(value)[0]:
        if item.get("citation_kind") == "usc":
            ids.add(item["canonical_authority_id"])
    pl = PUBLIC_LAW_RE.fullmatch(value)
    if pl:
        ids.add(f"public-law:{pl.group(1)}-{pl.group(2)}")
    stat = STAT_RE.fullmatch(value)
    if stat:
        ids.add(f"stat:{stat.group(1)}:{stat.group(2)}")
    return ids


def _documented_act_alias(alias: str, authority_id: str) -> bool:
    """True only for a repository-documented Act-section → Code equivalence."""
    match = ACT_SECTION_RE.fullmatch(alias.strip(" ,;:"))
    if not match:
        return False
    act = slug(normalize_space(match.group("act")))
    for locator in re.findall(r"\d+[A-Za-z]?(?:\s*\([A-Za-z0-9]+\))*", match.group("locators")):
        compact = re.sub(r"\s+", "", locator).lower()
        act_id = f"act:{act}:{compact}"
        if RECIPIENT.ACT_TO_USC.get(act_id) == authority_id:
            return True
    return False


def _contextual_act_section_id(act_slug: str, locator: str, contextual_key: str) -> str:
    """Make an unexpanded reference such as ``section 2 of the Act`` local.

    ``the Act`` does not identify a single statute across directives (and often
    cannot be resolved from the vesting clause alone).  It therefore must never
    be pooled into a purported nationwide authority such as ``act:the-act:2``.
    """
    return f"contextual-act-section:{slug(contextual_key)}:{act_slug}:{locator}"


def _is_contextual_act_slug(act_slug: str) -> bool:
    return bool(GENERIC_ACT_SLUG_RE.fullmatch(act_slug))


def parse_statutory_clause(clause: str, contextual_key: str = "context") -> tuple[list[dict], list[dict]]:
    """Return normalized statutory units and an audit of every SPECIFIC_RULE match.

    The recipient parser supplies the transparent U.S.C./Act-section grammar.  This
    layer retains its broad units and the wider statutory forms recognized by the
    vesting analysis.  Proximity only joins source aliases; it never supplies a
    substantive classification.
    """
    pinpoint, broad = RECIPIENT.parse_clause(clause)
    # The legacy recipient parser optimistically associates a section-of-Act
    # phrase with a nearby Code cite.  Keep only its documented equivalences;
    # all other Act sections are reconstructed below as independent units.
    for item in pinpoint:
        item["_source_raw_citation"] = item["raw_citation"]
        generic_match = re.fullmatch(r"act:([^:]+):(.+)", item.get("canonical_authority_id", ""))
        if generic_match and _is_contextual_act_slug(generic_match.group(1)):
            item["canonical_authority_id"] = _contextual_act_section_id(
                generic_match.group(1), generic_match.group(2), contextual_key
            )
            item["citation_kind"] = "contextual_act_section"
        retained = []
        for alias in item.get("parallel_aliases", "").split(" | "):
            if alias and _documented_act_alias(alias, item["canonical_authority_id"]):
                retained.append(alias)
        item["parallel_aliases"] = " | ".join(retained)

        # A grouped Code cite (for example, ``3 U.S.C. 301 and 46``) supplies
        # multiple units.  Its literal group must not become the display cite for
        # every member; render a stable individual citation for this unit instead.
        if item.get("citation_kind") == "usc" and item.get("title") and item.get("section"):
            item["raw_citation"] = f"{item['title']} U.S.C. {item['section']}{item.get('subsections', '')}"
    # The reused parser intentionally casts a generous 80-character net when it
    # associates an Act-section phrase with following Code forms.  Trim aliases
    # back to the expected number of cited Act locators so a following, unrelated
    # Code citation cannot inherit the same parallel alias.
    alias_groups = defaultdict(list)
    for item in pinpoint:
        for alias in item.get("parallel_aliases", "").split(" | "):
            if alias:
                alias_groups[alias].append(item)
    for alias, candidates in alias_groups.items():
        if len(candidates) < 2 or not re.search(r"\bsections?\s+", alias, re.I):
            continue
        locator_part = re.split(r"\s+of\s+", alias, maxsplit=1, flags=re.I)[0]
        expected = max(1, len(re.findall(r"\d+[A-Za-z]?(?:\s*\([A-Za-z0-9]+\))*", locator_part)))
        alias_end = clause.casefold().find(alias.casefold()) + len(alias)
        ranked = sorted(candidates, key=lambda item: abs(clause.casefold().find(item["raw_citation"].casefold()) - alias_end))
        keep = {id(item) for item in ranked[:expected]}
        for item in candidates:
            if id(item) not in keep:
                item["parallel_aliases"] = " | ".join(
                    value for value in item.get("parallel_aliases", "").split(" | ") if value and value != alias
                )

    # A section-of-Act phrase is not an alias for the next Code citation merely
    # because it appears nearby.  Preserve it as its own statutory unit unless
    # the same punctuation-delimited citation phrase actually supplies a parallel
    # U.S.C. form (e.g., ``section 604 of the Trade Act (19 U.S.C. 2483)``).
    for match in ACT_SECTION_RE.finditer(clause):
        raw = match.group(0).strip(" ,;:")
        following = clause[match.end():match.end() + 140]
        has_parallel_usc = bool(re.match(
            r"\s*(?:,\s*(?:as\s+amended|as\s+modified)\s*)?\(?\s*\d+\s+U\.?\s*S\.?\s*C\.?",
            following,
            re.I,
        ))
        parallel_usc_match = RECIPIENT.USC_GROUP_RE.search(following) if has_parallel_usc else None
        act = slug(normalize_space(match.group("act")))
        for locator in re.findall(r"\d+[A-Za-z]?(?:\s*\([A-Za-z0-9]+\))*", match.group("locators")):
            compact = re.sub(r"\s+", "", locator).lower()
            act_id = f"act:{act}:{compact}"
            mapped_usc = RECIPIENT.ACT_TO_USC.get(act_id)
            if has_parallel_usc:
                # A printed parenthetical Code form is a textual parallel cite,
                # even where the repository's Act-to-Code map lacks that pair.
                # Preserve the complete section-of-Act phrase on the Code unit;
                # it is evidence of the pinpoint and prevents a duplicate,
                # truncated whole-Act item from being created later.
                for item in pinpoint:
                    item_span = _item_span(clause, item)
                    if parallel_usc_match and match.end() <= item_span[0] <= match.end() + parallel_usc_match.end():
                        _add_alias(item, raw)
                continue
            if mapped_usc:
                if not any(item.get("canonical_authority_id") == mapped_usc for item in pinpoint):
                    pinpoint.append({
                        "raw_citation": raw, "_source_raw_citation": raw, "citation_kind": "act_section",
                        "title": "", "section": compact, "subsections": "",
                        "canonical_authority_id": mapped_usc, "is_broad": "false", "parallel_aliases": raw,
                    })
                continue
            for item in pinpoint:
                item["parallel_aliases"] = " | ".join(
                    value for value in item.get("parallel_aliases", "").split(" | ") if value and value != raw
                )
            canonical = (
                _contextual_act_section_id(act, compact, contextual_key)
                if _is_contextual_act_slug(act) else act_id
            )
            if not any(item.get("canonical_authority_id") == canonical for item in pinpoint):
                pinpoint.append({
                    "raw_citation": raw,
                    "citation_kind": "contextual_act_section" if _is_contextual_act_slug(act) else "act_section",
                    "title": "", "section": compact,
                    "subsections": "", "canonical_authority_id": canonical, "is_broad": "false",
                    "parallel_aliases": "",
                })
    items: list[dict] = []
    for item in pinpoint:
        items.append({
            "raw_citation": item["raw_citation"],
            "_source_raw_citation": item.get("_source_raw_citation", item["raw_citation"]),
            "citation_kind": item["citation_kind"],
            "canonical_authority_id": item["canonical_authority_id"],
            "is_broad": "false",
            "parallel_aliases": item.get("parallel_aliases", ""),
            "specific_rules": "",
            "extraction_status": "normalized",
        })
    for item in broad:
        raw = item["raw_citation"]
        if item.get("title"):
            canonical = f"usc-broad:{int(item['title'])}:{slug(raw)}"
            kind = "usc_broad"
        else:
            canonical = f"statutory-broad:{slug(raw)}"
            kind = "statutory_broad"
        items.append({
                "raw_citation": raw, "citation_kind": kind,
            "canonical_authority_id": canonical, "is_broad": "true",
            "parallel_aliases": item.get("parallel_aliases", ""),
            "specific_rules": "", "extraction_status": "broad_normalized",
        })
    for item in items:
        item["_span"] = _item_span(clause, item)

    # Add complete, unsectioned Act titles before the formal-match audit.  A
    # title already contained in a section-level citation is not a second,
    # whole-Act citation.
    for match in FULL_NAMED_ACT_RE.finditer(clause):
        raw, span = match.group(0), match.span()
        # Bare referential labels (``the Act``, ``this Act``, ``the 1974 Act``)
        # do not independently identify a statute.  They may explain another
        # citation in the clause, but are not themselves units in this study.
        if _is_contextual_act_slug(slug(raw)):
            continue
        following = clause[span[1]:span[1] + 140]
        if re.match(r"\s*(?:,\s*as\s+amended\s*)?\(\s*\d+\s+U\.?\s*S\.?\s*C\.?", following, re.I):
            parallel_code = [
                item for item in items
                if item["citation_kind"] == "usc_broad" and span[1] <= item["_span"][0] <= span[1] + 140
            ]
            if parallel_code:
                for item in parallel_code:
                    _add_alias(item, raw)
                continue
        if any(item["_span"][0] <= span[0] and span[1] <= item["_span"][1] for item in items):
            continue
        canonical = f"act-broad:{slug(raw)}"
        if not any(item["canonical_authority_id"] == canonical for item in items):
            items.append({
                "raw_citation": raw, "citation_kind": "named_act",
                "canonical_authority_id": canonical, "is_broad": "true",
                "parallel_aliases": "", "specific_rules": "named_act",
                "extraction_status": "broad_normalized", "_span": span,
            })

    # Consolidate only citation forms that the directive itself prints as one
    # citation bundle.  These bindings are also used by the formal-signal audit,
    # so component source forms do not later reappear as separate occurrences.
    bundle_bindings = []
    act_section_spans = [match.span() for match in ACT_SECTION_RE.finditer(clause)]

    def source_target(kind: str, raw: str, span: tuple[int, int]) -> dict | None:
        candidates = [item for item in items if item.get("_span", (-1, -1))[0] >= span[0]
                      and item.get("_span", (-1, -1))[1] <= span[1]]
        if kind == "usc":
            candidates = [item for item in candidates if item["citation_kind"] in {"usc", "usc_broad"}]
            return candidates[0] if len(candidates) == 1 else None
        if kind == "public_law":
            match = PUBLIC_LAW_RE.search(raw)
            canonical = f"public-law:{match.group(1)}-{match.group(2)}" if match else ""
        else:
            match = STAT_RE.search(raw)
            canonical = f"stat:{match.group(1)}:{match.group(2)}" if match else ""
        existing = next((item for item in items if item["canonical_authority_id"] == canonical), None)
        if existing:
            return existing
        if not canonical:
            return None
        item = {
            "raw_citation": raw, "citation_kind": kind,
            "canonical_authority_id": canonical, "is_broad": "true",
            "parallel_aliases": "", "specific_rules": "",
            "extraction_status": "broad_normalized", "equivalence_basis": "", "_span": span,
        }
        items.append(item)
        return item

    for match in ACT_SECTION_RE.finditer(clause):
        parenthetical = _following_parenthetical(clause, match.end())
        if not parenthetical:
            continue
        forms = _source_forms(clause[parenthetical[0]:parenthetical[1]], parenthetical[0])
        if not forms:
            continue
        usc_targets = [item for item in items
                       if item["citation_kind"] in {"usc", "usc_broad"}
                       and parenthetical[0] <= item.get("_span", (-1, -1))[0]
                       and item.get("_span", (-1, -1))[1] <= parenthetical[1]]
        targets = usc_targets
        if not targets:
            raw_act = match.group(0).strip(" ,;:")
            targets = [item for item in items
                       if item["citation_kind"] in {"act_section", "contextual_act_section"}
                       and item["raw_citation"].casefold() == raw_act.casefold()]
        if not targets:
            continue
        raw_act = match.group(0).strip(" ,;:")
        for target in targets:
            _add_alias(target, raw_act)
            for _, raw, _ in forms:
                _add_alias(target, raw)
            _append_basis(target, "explicit_parenthetical")
        target_ids = {item["canonical_authority_id"] for item in targets}
        items = [item for item in items if not (
            item["citation_kind"] in {"act_section", "contextual_act_section", "statutes_at_large", "public_law"}
            and item["canonical_authority_id"] not in target_ids
            and match.start() <= item.get("_span", (-1, -1))[0] < parenthetical[1]
        )]
        bundle_bindings.append({"span": (match.start(), parenthetical[1]), "targets": targets,
                                "basis": "explicit_parenthetical"})

    # Apply the same rule to whole named Acts printed with a source-law
    # parenthetical.  A Public Law identifier is preferred to a Statutes-at-Large
    # page, and either is preferred to a bare Act-title identifier.
    for match in FULL_NAMED_ACT_RE.finditer(clause):
        if any(start <= match.start() and match.end() <= end for start, end in act_section_spans):
            continue
        parenthetical = _following_parenthetical(clause, match.end())
        if not parenthetical:
            continue
        forms = _source_forms(clause[parenthetical[0]:parenthetical[1]], parenthetical[0])
        if not forms:
            continue
        usc_targets = [item for item in items if item["citation_kind"] in {"usc", "usc_broad"}
                       and parenthetical[0] <= item.get("_span", (-1, -1))[0]
                       and item.get("_span", (-1, -1))[1] <= parenthetical[1]]
        targets = usc_targets
        if not targets:
            preferred = next((form for form in forms if form[0] == "public_law"), None)
            preferred = preferred or next((form for form in forms if form[0] == "statutes_at_large"), None)
            target = source_target(*preferred) if preferred else None
            targets = [target] if target else []
        if not targets:
            targets = [item for item in items if item["canonical_authority_id"] == f"act-broad:{slug(match.group(0))}"]
        if not targets:
            continue
        for target in targets:
            _add_alias(target, match.group(0))
            for _, raw, _ in forms:
                _add_alias(target, raw)
            _append_basis(target, "explicit_parenthetical")
        target_ids = {item["canonical_authority_id"] for item in targets}
        items = [item for item in items if not (
            item["canonical_authority_id"] not in target_ids
            and item["citation_kind"] in {"named_act", "statutory_broad", "statutes_at_large", "public_law"}
            and match.start() <= item.get("_span", (-1, -1))[0] < parenthetical[1]
        )]
        bundle_bindings.append({"span": (match.start(), parenthetical[1]), "targets": targets,
                                "basis": "explicit_parenthetical"})

    audits = []
    matches = [
        (rule.name, match.group(0), match.span())
        for rule in SPECIFIC_RULES for match in rule.pattern.finditer(clause)
    ]
    for ordinal, (rule_name, match_text, span) in enumerate(matches, 1):
        audit = {"rule": rule_name, "text": match_text, "disposition": "", "authority_ids": "",
                 "equivalence_basis": ""}
        if rule_name in NONSTATUTORY_RULES:
            audit["disposition"] = "excluded_nonstatutory_specific_authority"
            audits.append(audit)
            continue
        if rule_name in {"named_act", "referenced_act"} and _is_contextual_act_slug(slug(match_text)):
            audit["disposition"] = "excluded_nonidentifying_act_reference"
            audits.append(audit)
            continue
        covering = [item for item in items if item["_span"][0] <= span[0] and span[1] <= item["_span"][1]]
        binding = next((value for value in bundle_bindings
                        if value["span"][0] <= span[0] and span[1] <= value["span"][1]), None)
        if binding:
            targets = binding["targets"]
            audit["equivalence_basis"] = binding["basis"]
        elif covering:
            targets = covering
        else:
            targets = []
            raw, kind, canonical, is_broad = match_text, rule_name, "", "true"
            if rule_name == "named_act":
                canonical = f"act-broad:{slug(raw)}"
            elif rule_name == "usc":
                title_match = re.search(r"\d+", raw)
                title = title_match.group(0) if title_match else "unknown"
                canonical = f"usc-context:{title}:{slug(contextual_key)}:{ordinal}"
                kind = "usc_contextual"
            elif rule_name == "public_law":
                pl = PUBLIC_LAW_RE.search(clause, max(0, span[0] - 10), min(len(clause), span[1] + 40))
                raw = pl.group(0) if pl else raw
                canonical = f"public-law:{pl.group(1)}-{pl.group(2)}" if pl else f"public-law-context:{slug(contextual_key)}:{ordinal}"
            elif rule_name == "statutes_at_large":
                stat = STAT_RE.search(raw)
                canonical = f"stat:{stat.group(1)}:{stat.group(2)}" if stat else f"stat-context:{slug(contextual_key)}:{ordinal}"
            elif rule_name in {"legal_title", "legal_chapter"}:
                canonical = f"statutory-broad:{slug(raw)}:{slug(contextual_key)}"
            elif rule_name in {"referenced_act", "referenced_statutory_provisions", "legal_section"}:
                # A nearby normalized unit or named statute is its likely referent.
                targets = _nearest(items, span, 220)
                if not targets:
                    canonical = f"contextual-statute:{slug(contextual_key)}:{ordinal}"
                    kind = "contextual_statute"
            elif rule_name == "congressional_measure":
                canonical = f"congressional-measure:{slug(raw)}:{slug(contextual_key)}"
            elif rule_name == "joint_resolution":
                canonical = f"joint-resolution:{slug(contextual_key)}:{ordinal}"

            # Do not treat mere proximity as a parallel-citation relationship.
            # A named Act, Public Law, or Statutes-at-Large cite can occur beside a
            # separate U.S.C. authority in one vesting clause.  It is collapsed
            # only when it is textually contained in that authority's literal
            # citation or documented through an explicit Act-to-Code mapping.
            if not targets and rule_name == "named_act":
                following = clause[span[1]:span[1] + 140]
                if re.match(
                    r"\s*(?:,\s*as\s+amended\s*)?\(\s*\d+\s+U\.?\s*S\.?\s*C\.?",
                    following,
                    re.I,
                ):
                    targets = [
                        item for item in items
                        if span[1] <= item["_span"][0] <= span[1] + 140 and item["citation_kind"] == "usc_broad"
                    ]
            if not targets and canonical:
                new_item = {
                    "raw_citation": raw, "citation_kind": kind,
                    "canonical_authority_id": canonical, "is_broad": is_broad,
                    "parallel_aliases": "", "specific_rules": rule_name,
                    "extraction_status": "broad_normalized" if is_broad == "true" else "normalized",
                    "_span": span,
                }
                items.append(new_item)
                targets = [new_item]
        for item in targets:
            if rule_name in {"named_act", "statutes_at_large", "public_law", "congressional_measure"}:
                _add_alias(item, match_text)
            rules = [value for value in item.get("specific_rules", "").split(" | ") if value]
            if rule_name not in rules:
                rules.append(rule_name)
            item["specific_rules"] = " | ".join(rules)
        audit["disposition"] = "mapped_statutory_unit" if targets else "unmapped_statutory_signal"
        audit["authority_ids"] = " | ".join(dict.fromkeys(item["canonical_authority_id"] for item in targets))
        audits.append(audit)

    # Explicit Revised Statutes references are statutory even though the legacy
    # rule reports only their leading "section N" signal.
    for match in REVISED_STATUTES_RE.finditer(clause):
        raw = match.group(0)
        canonical = f"revised-statutes:{slug(match.group(1))}"
        if not any(item["canonical_authority_id"] == canonical for item in items):
            items.append({
                "raw_citation": raw, "citation_kind": "revised_statutes",
                "canonical_authority_id": canonical, "is_broad": "false",
                "parallel_aliases": "", "specific_rules": "legal_section",
                "extraction_status": "normalized", "_span": match.span(),
            })

    deduped = {}
    for item in items:
        key = item["canonical_authority_id"]
        if key not in deduped:
            deduped[key] = item
        else:
            _add_alias(deduped[key], item["raw_citation"])
            for alias in item.get("parallel_aliases", "").split(" | "):
                if alias:
                    _add_alias(deduped[key], alias)
    for item in deduped.values():
        item.pop("_span", None)
        item.pop("_source_raw_citation", None)
    return list(deduped.values()), audits


def load_current_sources() -> dict[str, dict]:
    path = RECIPIENT_DIR / "outputs" / "current_uscode_sources.csv"
    if not path.exists():
        return {}
    csv.field_size_limit(16 * 1024 * 1024)
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["canonical_authority_id"]: row for row in csv.DictReader(handle)}


def build_inventory(corpora=DEFAULT_CORPORA, output: Path = DEFAULT_OUTPUT) -> dict:
    corpus = load_corpus(list(corpora))
    retained = [row for row in corpus if ceremonial_reason(row) is None]
    occurrences, audit_rows = [], []
    for row in retained:
        for clause_index, raw_clause in enumerate(extract_vesting_clauses(row["doc_text"], row["doc_type"]), 1):
            clause = RECIPIENT.authority_core(raw_clause)
            if not clause:
                continue
            context_key = f"{row['']}:{clause_index}"
            items, audits = parse_statutory_clause(clause, context_key)
            for item in items:
                occurrence = {
                    "occurrence_id": f"{row['']}:{clause_index}:{len(occurrences) + 1}",
                    "document_id": row[""], "date": row["date"], "president": row["president"],
                    "term": row["term"], "doc_type": row["doc_type"], "url": row["url"],
                    "clause_index": clause_index, "raw_clause": clause, **item,
                }
                occurrences.append(occurrence)
            for ordinal, audit in enumerate(audits, 1):
                audit_rows.append({
                    "document_id": row[""], "date": row["date"], "doc_type": row["doc_type"],
                    "url": row["url"], "clause_index": clause_index, "signal_index": ordinal,
                    "raw_clause": clause, **audit,
                })

    # Propagate provision-level equivalences established by explicit printed
    # bundles to otherwise standalone occurrences of the same literal form.
    # Only one-to-one mappings are automatic; conflicting targets are retained
    # as separate authorities and written to the review artifact below.
    proposed_targets = defaultdict(set)
    proposed_evidence = defaultdict(list)
    for row in occurrences:
        if "explicit_parenthetical" not in row.get("equivalence_basis", ""):
            continue
        target = row["canonical_authority_id"]
        aliases = [row["raw_citation"], *row.get("parallel_aliases", "").split(" | ")]
        for alias in aliases:
            for source in _precise_alias_ids(alias):
                if source != target:
                    proposed_targets[source].add(target)
                    proposed_evidence[(source, target)].append({
                        "document_id": row["document_id"], "raw_clause": row["raw_clause"],
                        "printed_form": alias, "url": row["url"],
                    })
    crosswalk = {
        source: next(iter(targets)) for source, targets in proposed_targets.items()
        if len(targets) == 1
    }
    automatic_crosswalk_count = len(crosswalk)
    verified_path = output / "verified_equivalence_crosswalk.csv"
    verified_edges = []
    if verified_path.exists():
        with verified_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row.get("relationship") != "equivalent":
                    continue
                preferred = row.get("preferred_authority_id", "")
                left, right = row.get("left_authority_id", ""), row.get("right_authority_id", "")
                if preferred not in {left, right}:
                    continue
                source = right if preferred == left else left
                crosswalk[source] = preferred
                verified_edges.append((source, preferred))

    def resolved_id(authority_id: str) -> str:
        seen = set()
        while authority_id in crosswalk and authority_id not in seen:
            seen.add(authority_id)
            authority_id = crosswalk[authority_id]
        return authority_id

    crosswalk = {source: resolved_id(target) for source, target in crosswalk.items()}
    for row in occurrences:
        original = row["canonical_authority_id"]
        target = resolved_id(original)
        row["pre_crosswalk_authority_id"] = original if target != original else ""
        if target != original:
            row["canonical_authority_id"] = target
            bases = [value for value in row.get("equivalence_basis", "").split(" | ") if value]
            if "global_explicit_crosswalk" not in bases:
                bases.append("global_explicit_crosswalk")
            row["equivalence_basis"] = " | ".join(bases)
    for row in audit_rows:
        ids = [value for value in row.get("authority_ids", "").split(" | ") if value]
        row["authority_ids"] = " | ".join(dict.fromkeys(resolved_id(value) for value in ids))

    source_map = load_current_sources()
    grouped = defaultdict(list)
    for row in occurrences:
        grouped[row["canonical_authority_id"]].append(row)
    packets = []
    for authority_id, rows in sorted(grouped.items()):
        dates = sorted({datetime.strptime(row["date"], "%B %d, %Y").date().isoformat() for row in rows})
        aliases = sorted({value for row in rows for value in [row["raw_citation"], *row["parallel_aliases"].split(" | ")] if value})
        clauses = list(dict.fromkeys(row["raw_clause"] for row in rows))
        source = source_map.get(authority_id, {})
        packets.append({
            "canonical_authority_id": authority_id,
            "citation_kind": rows[0]["citation_kind"],
            "is_broad": rows[0]["is_broad"] == "true",
            "occurrence_count": len(rows),
            "document_count": len({row["document_id"] for row in rows}),
            "observed_dates": dates,
            "observed_date_range": [dates[0], dates[-1]],
            "observed_years": sorted({value[:4] for value in dates}),
            "citation_aliases": aliases,
            "sample_vesting_clauses": clauses[:5],
            "supplied_current_heading": source.get("heading", ""),
            "supplied_current_text": source.get("operative_text", ""),
            "supplied_amendment_notes": source.get("amendment_notes", ""),
            "supplied_official_url": source.get("official_source_url", ""),
            "source_status": source.get("source_status", "not_supplied"),
            "historical_text_warning": "Current text is not evidence of historical text unless the amendment record supports the observed date.",
        })

    write_csv(output / "citation_occurrences.csv", occurrences, OCCURRENCE_FIELDS)
    crosswalk_rows = []
    for source, target in sorted(crosswalk.items()):
        evidence = proposed_evidence.get((source, target), [])
        crosswalk_rows.append({
            "source_authority_id": source, "target_authority_id": target,
            "status": "automatic_unambiguous", "evidence_count": len(evidence),
            "sample_printed_form": evidence[0]["printed_form"] if evidence else "",
            "sample_document_id": evidence[0]["document_id"] if evidence else "",
            "sample_clause": evidence[0]["raw_clause"] if evidence else "",
            "sample_url": evidence[0]["url"] if evidence else "",
        })
    for source, targets in sorted(proposed_targets.items()):
        if len(targets) <= 1:
            continue
        crosswalk_rows.append({
            "source_authority_id": source, "target_authority_id": " | ".join(sorted(targets)),
            "status": "conflict_requires_review", "evidence_count": sum(
                len(proposed_evidence[(source, target)]) for target in targets
            ), "sample_printed_form": "", "sample_document_id": "", "sample_clause": "", "sample_url": "",
        })
    write_csv(output / "global_equivalence_crosswalk.csv", crosswalk_rows,
              ("source_authority_id", "target_authority_id", "status", "evidence_count",
               "sample_printed_form", "sample_document_id", "sample_clause", "sample_url"))
    write_csv(output / "specific_signal_audit.csv", audit_rows,
              ("document_id", "date", "doc_type", "url", "clause_index", "signal_index",
               "raw_clause", "rule", "text", "disposition", "authority_ids", "equivalence_basis"))
    equivalence_groups = defaultdict(list)
    for row in audit_rows:
        if row.get("equivalence_basis"):
            key = (row["document_id"], row["clause_index"], row["equivalence_basis"], row["authority_ids"])
            equivalence_groups[key].append(row)
    equivalence_review = []
    for (document_id, clause_index, basis, authority_ids), rows in equivalence_groups.items():
        equivalence_review.append({
            "document_id": document_id,
            "date": rows[0]["date"],
            "clause_index": clause_index,
            "equivalence_basis": basis,
            "target_authority_ids": authority_ids,
            "component_rules": " | ".join(dict.fromkeys(row["rule"] for row in rows)),
            "printed_forms": " | ".join(dict.fromkeys(row["text"] for row in rows)),
            "raw_clause": rows[0]["raw_clause"],
            "url": rows[0]["url"],
        })
    write_csv(output / "citation_equivalence_review.csv", equivalence_review,
              ("document_id", "date", "clause_index", "equivalence_basis", "target_authority_ids",
               "component_rules", "printed_forms", "raw_clause", "url"))
    with (output / "authority_packets.jsonl").open("w", encoding="utf-8") as handle:
        for packet in packets:
            handle.write(json.dumps(packet, ensure_ascii=False) + "\n")
    manifest = {
        "schema_version": 1,
        "corpus_documents": len(corpus),
        "ceremonial_exclusions": len(corpus) - len(retained),
        "nonceremonial_documents": len(retained),
        "directives_with_statutory_citations": len({row["document_id"] for row in occurrences}),
        "statutory_citation_occurrences": len(occurrences),
        "unique_statutory_authorities": len(packets),
        "broad_occurrences": sum(row["is_broad"] == "true" for row in occurrences),
        "explicit_equivalence_bundles": len(equivalence_review),
        "automatic_global_crosswalks": automatic_crosswalk_count,
        "web_verified_crosswalks": len(verified_edges),
        "crosswalk_conflicts": sum(len(targets) > 1 for targets in proposed_targets.values()),
        "specific_signal_dispositions": dict(sorted(Counter(row["disposition"] for row in audit_rows).items())),
        "source_files": [str(path.relative_to(ROOT)) for path in corpora],
        "source_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in corpora},
    }
    write_json(output / "inventory_manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", action="append", type=Path, dest="corpora")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(build_inventory(tuple(args.corpora or DEFAULT_CORPORA), args.output), indent=2))


if __name__ == "__main__":
    main()
