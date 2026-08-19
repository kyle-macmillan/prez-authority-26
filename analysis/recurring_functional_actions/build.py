#!/usr/bin/env python3
"""Build the recurring-functional-actions pilot and review queues."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS = ROOT / "data/4_28_2026_build_dev.csv"
DEFAULT_PROFILES = ROOT / "data/parent_analysis/canonical_profiles/profiles.jsonl"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "outputs"

EMERGENCY_ACTION = re.compile(
    r"\b(?:declar(?:e|es|ed|ing)|proclaim(?:s|ed|ing)?|continu(?:e|es|ed|ing)|"
    r"extend(?:s|ed|ing)?|expand(?:s|ed|ing)?|modif(?:y|ies|ied|ying)|"
    r"terminat(?:e|es|ed|ing)|revok(?:e|es|ed|ing))\b.{0,220}\b(?:national\s+)?emergency\b|"
    r"\b(?:national\s+)?emergency\b.{0,220}\b(?:is\s+hereby\s+declared|shall\s+continue|"
    r"continue\s+in\s+effect|is\s+terminated|is\s+hereby\s+revoked)\b",
    re.I | re.S,
)
PROPERTY_BLOCKING = re.compile(
    r"\b(?:block(?:ed|ing)?|freez(?:e|es|ing)|may\s+not\s+be\s+transferred)\b.{0,180}"
    r"\b(?:property|assets?|interests?\s+in\s+property)\b|"
    r"\b(?:property|interests?\s+in\s+property)\b.{0,180}\bblocked\b",
    re.I | re.S,
)
MONUMENT = re.compile(
    r"\b(?:designat(?:e|es|ed|ing)|proclaim(?:s|ed|ing)?|reserv(?:e|es|ed|ing)|"
    r"enlarg(?:e|es|ed|ing)|modif(?:y|ies|ied|ying))\b.{0,220}\bnational\s+monument\b|"
    r"\bnational\s+monument\b.{0,220}\b(?:designated|proclaimed|reserved|enlarged|modified)\b",
    re.I | re.S,
)
SEEDS = {
    "emergency_action": EMERGENCY_ACTION,
    "property_blocking": PROPERTY_BLOCKING,
    "national_monument_designation": MONUMENT,
}
ACTION_WORDS = (
    "establish", "designate", "delegate", "block", "freeze", "prohibit", "waive",
    "determine", "suspend", "revoke", "amend", "direct", "require", "authorize",
    "continue", "terminate", "impose", "appoint", "remove", "transfer", "report",
)
STOP = {"the", "a", "an", "of", "to", "and", "for", "in", "on", "by", "with",
        "from", "president", "secretary", "department", "agency", "federal"}


def read_corpus(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    seen: set[str] = set()
    output = []
    for row in rows:
        document_id = row.get("", "")
        if not document_id or document_id in seen:
            raise ValueError(f"missing or duplicate document ID: {document_id!r}")
        seen.add(document_id)
        row["document_id"] = document_id
        row["parsed_date"] = datetime.strptime(row["date"], "%B %d, %Y").date().isoformat()
        output.append(row)
    return output


def read_profiles(path: Path) -> dict[str, dict]:
    profiles = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            document_id = str(row["document_id"])
            if document_id in profiles:
                raise ValueError(f"duplicate canonical profile: {document_id}")
            profiles[document_id] = row["profile"]
    return profiles


def is_ceremonial(row: dict[str, str]) -> bool:
    # Keep this project runnable without importing the implementation tree.
    text = row["doc_text"]
    if re.search(r"\b(?:tariff|HTSUS|national emergency|suspend\w* entry)\b", text, re.I):
        return False
    return bool(
        re.search(r"\bhalf[- ]?(?:staff|mast)\b", text, re.I)
        or (row["doc_type"] == "proclamation" and re.search(
            r"\b(?:call upon|urge) (?:all )?(?:Americans|the people).*\b(?:observe|commemorate)\b",
            text, re.I | re.S))
    )


def stable_score(document_id: str, seed: int) -> str:
    return hashlib.sha256(f"{seed}:{document_id}".encode()).hexdigest()


def select_pilot(rows: list[dict[str, str]], profiles: dict[str, dict], per_stratum: int,
                 seed: int) -> list[dict[str, str]]:
    strata: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row["document_id"] in profiles and not is_ceremonial(row):
            strata[(row["president"], row["doc_type"])].append(row)
    selected = []
    for key in sorted(strata):
        selected.extend(sorted(strata[key], key=lambda r: stable_score(r["document_id"], seed))[:per_stratum])
    return sorted(selected, key=lambda r: (r["president"], r["doc_type"], r["parsed_date"], r["document_id"]))


def function_text(function: dict) -> str:
    # Authority is absent from canonical profiles by construction.
    return " | ".join(str(function.get(k, "")) for k in ("action", "target", "mechanism", "effect"))


def discovery_signature(function: dict) -> str:
    text = function_text(function).lower()
    action = next((word for word in ACTION_WORDS if re.search(rf"\b{word}\w*\b", text)), "other")
    tokens = [t for t in re.findall(r"[a-z][a-z-]+", str(function.get("target", "")).lower()) if t not in STOP]
    target = "_".join(tokens[:3]) or "unspecified"
    return f"{action}:{target}"


def seed_matches(function: dict) -> list[tuple[str, str]]:
    text = " ".join(str(function.get(k, "")) for k in ("label", "action", "target", "mechanism", "effect", "evidence"))
    matches = []
    for family, pattern in SEEDS.items():
        match = pattern.search(text)
        if match:
            subtype = ""
            if family == "emergency_action":
                lower = match.group(0).lower()
                subtype = ("termination" if re.search(r"terminat|revok", lower) else
                           "continuation" if re.search(r"continu|extend", lower) else
                           "modification" if re.search(r"expand|modif", lower) else "declaration")
            matches.append((family, subtype))
    return matches


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def build(corpus_path: Path, profiles_path: Path, output: Path, per_stratum: int = 10,
          seed: int = 20260817) -> dict:
    corpus = read_corpus(corpus_path); profiles = read_profiles(profiles_path)
    pilot = select_pilot(corpus, profiles, per_stratum, seed)
    pilot_rows = [{k: row[k] for k in ("document_id", "president", "parsed_date", "doc_type", "url")} for row in pilot]
    functions = []
    assignments = []
    for row in pilot:
        for function in profiles[row["document_id"]].get("operative_functions", []):
            item = {
                "document_id": row["document_id"], "function_id": function["function_id"],
                "president": row["president"], "date": row["parsed_date"], "document_type": row["doc_type"],
                "label": function.get("label", ""), "action": function.get("action", ""),
                "target": function.get("target", ""), "mechanism": function.get("mechanism", ""),
                "effect": function.get("effect", ""), "evidence": function.get("evidence", ""),
                "discovery_signature": discovery_signature(function),
            }
            functions.append(item)
            for family, subtype in seed_matches(function):
                assignments.append({**item, "family_id": family, "action_subtype": subtype,
                                    "assignment_status": "proposed", "review_decision": "", "review_notes": ""})
    groups = defaultdict(list)
    for item in functions: groups[item["discovery_signature"]].append(item)
    queue = []
    for signature, items in sorted(groups.items(), key=lambda pair: (-len(pair[1]), pair[0])):
        administrations = {x["president"] for x in items}
        if len(items) < 2 or len(administrations) < 2:
            continue
        for item in sorted(items, key=lambda x: stable_score(x["function_id"], seed))[:5]:
            queue.append({**item, "cluster_size": len(items), "administration_count": len(administrations),
                          "proposed_family_name": "", "coherent_family": "", "review_notes": ""})
    summary = []
    for family in SEEDS:
        matched = [x for x in assignments if x["family_id"] == family]
        summary.append({"family_id": family, "functions": len(matched),
                        "documents": len({x["document_id"] for x in matched}),
                        "administrations": len({x["president"] for x in matched}),
                        "review_status": "candidate"})
    write_csv(output / "pilot_documents.csv", pilot_rows, ["document_id", "president", "parsed_date", "doc_type", "url"])
    function_fields = ["document_id", "function_id", "president", "date", "document_type", "label", "action", "target", "mechanism", "effect", "evidence", "discovery_signature"]
    write_csv(output / "pilot_functions.csv", functions, function_fields)
    write_csv(output / "seed_family_assignments.csv", assignments, function_fields + ["family_id", "action_subtype", "assignment_status", "review_decision", "review_notes"])
    write_csv(output / "family_review_queue.csv", queue, function_fields + ["cluster_size", "administration_count", "proposed_family_name", "coherent_family", "review_notes"])
    write_csv(output / "family_summary.csv", summary, ["family_id", "functions", "documents", "administrations", "review_status"])
    manifest = {"schema_version": 1, "corpus": str(corpus_path), "profiles": str(profiles_path),
                "corpus_sha256": hashlib.sha256(corpus_path.read_bytes()).hexdigest(),
                "profiles_sha256": hashlib.sha256(profiles_path.read_bytes()).hexdigest(),
                "per_president_document_type": per_stratum, "seed": seed, "corpus_documents": len(corpus),
                "profile_documents": len(profiles), "pilot_documents": len(pilot), "pilot_functions": len(functions),
                "seed_assignments": len(assignments), "review_queue_rows": len(queue)}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--per-stratum", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260817)
    args = parser.parse_args()
    if args.per_stratum < 1: raise SystemExit("--per-stratum must be positive")
    print(json.dumps(build(args.corpus, args.profiles, args.output, args.per_stratum, args.seed), indent=2))


if __name__ == "__main__": main()
