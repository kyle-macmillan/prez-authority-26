#!/usr/bin/env python3
"""Build the statutory delegation-recipient census.

Run from the repository root:
  python3 analysis/delegation-recipient/build.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from ceremonial import ceremonial_reason  # noqa: E402
from vesting_authority_stats import extract_vesting_clauses, load_corpus  # noqa: E402

ANALYSIS_DIR = Path(__file__).resolve().parent
DEFAULT_CORPORA = (
    ROOT / "data" / "4_28_2026_build_dev.csv",
    ROOT / "data" / "4_28_2026_build_holdout.csv",
)
DEFAULT_CENSUS = ANALYSIS_DIR / "provision_census.csv"
DEFAULT_OUTPUT = ANALYSIS_DIR / "outputs"

RECIPIENT_CLASSES = (
    "president_only",
    "agency_or_officer_only",
    "both",
    "other_recipient",
    "no_power_conferred",
    "unresolved",
)

# High-frequency parallel codifications observed in this corpus. These mappings
# are statutory identities, not recipient classifications; the recipient is still
# coded only from sourced statutory text.
ACT_TO_USC = {
    "act:the-trade-expansion-act-of-1962:232": "usc:19:1862",
    "act:the-trade-act-of-1974:604": "usc:19:2483",
    "act:the-trade-act:604": "usc:19:2483",
    "act:the-1974-act:604": "usc:19:2483",
    "act:the-agricultural-adjustment-act:22": "usc:7:624",
    "act:the-agricultural-adjustment-act-of-1933:22": "usc:7:624",
    "act:the-foreign-assistance-act-of-1961:621": "usc:22:2381",
    "act:the-tariff-act-of-1930:350": "usc:19:1351",
    "act:the-tariff-act-of-1930:350(a)": "usc:19:1351(a)",
}

# A deliberately bounded grammar. It parses section-level U.S.C. references and
# preserves ranges/et seq. as broad rather than pretending their first section is
# the entire cited authority.
USC_GROUP_RE = re.compile(
    r"(?P<title>\d+)\s+U\.?\s*S\.?\s*C\.?\s*(?:§{1,2}\s*)?"
    r"(?P<body>\d+[A-Za-z]?(?:\s*\([A-Za-z0-9]+\))*"
    r"(?:\s*(?:,|and|or)\s*\d+[A-Za-z]?(?:\s*\([A-Za-z0-9]+\))*)*"
    r"(?:\s*(?:et\s+seq\.?|[-–—]\s*\d+[A-Za-z]?(?:\s*\([A-Za-z0-9]+\))*))?)",
    re.I,
)
BARE_USC_RE = re.compile(r"\b\d+\s+U\.?\s*S\.?\s*C\.?\b", re.I)
TITLE_SECTION_RE = re.compile(
    r"\bsections?\s+(?P<locators>\d+[A-Za-z]?(?:\s*\([A-Za-z0-9]+\))*"
    r"(?:\s*(?:,|and|or)\s*\d+[A-Za-z]?(?:\s*\([A-Za-z0-9]+\))*)*)"
    r"\s+of\s+title\s+(?P<title>\d+)\s*,?\s*(?:of\s+the\s+)?United\s+States\s+Code",
    re.I,
)
ACT_SECTION_RE = re.compile(
    r"\bsections?\s+(?P<locators>\d+[A-Za-z]?(?:\s*\([A-Za-z0-9]+\))*"
    r"(?:\s*(?:,|and|or)\s*\d+[A-Za-z]?(?:\s*\([A-Za-z0-9]+\))*)*)"
    r"\s+of\s+(?P<act>(?:the\s+)?[^,;:]{2,180}?\bAct(?:\s+of\s+\d{4})?)",
    re.I,
)
BROAD_RE = re.compile(
    r"\b(?:chapter\s+\d+[A-Za-z]?\s+of\s+title\s+\d+|title\s+\d+\s+of\s+the\s+United\s+States\s+Code|"
    r"\d+\s+U\.?S\.?C\.?\s*,?\s*(?:App\.?|ch\.?\s*\d+))\b",
    re.I,
)
SPECIFIC_SIGNAL_RE = re.compile(
    r"\b(?:\d+\s+U\.?\s*S\.?\s*C\.?|sections?\s+\d+|Public\s+Law\s+\d|\d+\s+Stat\.\s+\d)",
    re.I,
)
FORMAL_AUTHORITY_RE = re.compile(
    r"\b(?:authority\s+(?:vested|conferred|granted)\s+(?:in|upon|to)\s+me|"
    r"by\s+virtue\s+of\s+(?:the|my)\s+authority|"
    r"I,\s+[^,]{2,80},\s+President\s+of\s+the\s+United\s+States)\b",
    re.I,
)
PURSUANT_FIRST_PERSON_RE = re.compile(
    r"\b(?:pursuant\s+to|under)\b.{0,1200}\bI\s+(?:hereby\s+)?"
    r"(?:determine|find|certify|designate|delegate|order|proclaim|waive|suspend|exempt|direct)\b",
    re.I,
)

CENSUS_FIELDS = (
    "canonical_authority_id", "version_start", "version_end", "recipient_class",
    "power_type", "operative_excerpt", "rationale", "official_source_url",
    "official_source_citation", "confidence", "review_status",
)
OCCURRENCE_FIELDS = (
    "occurrence_id", "document_id", "date", "president", "term", "doc_type", "url",
    "clause_index", "raw_clause", "raw_citation", "citation_kind", "title",
    "section", "subsections", "canonical_authority_id", "is_broad",
    "parallel_aliases", "recipient_class", "mapping_status",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_usc(title: str, section: str, subsections: str = "") -> str:
    subs = re.sub(r"\s+", "", subsections)
    return f"usc:{int(title)}:{section.lower()}{subs.lower()}"


def authority_core(clause: str) -> str | None:
    """Return only the asserted authority span, excluding preceding recitals."""
    formal = list(FORMAL_AUTHORITY_RE.finditer(clause))
    if formal:
        return clause[formal[-1].start():].strip()
    pursuant = PURSUANT_FIRST_PERSON_RE.search(clause)
    if pursuant:
        return clause[pursuant.start():].strip()
    return None


def parse_clause(clause: str) -> tuple[list[dict], list[dict]]:
    """Return (pinpoint authority units, broad references) from one clause."""
    pinpoint: list[dict] = []
    broad: list[dict] = []
    occupied: list[tuple[int, int]] = []
    for match in USC_GROUP_RE.finditer(clause):
        raw = match.group(0).strip(" ,;:")
        body = match.group("body")
        if re.search(r"\bet\s+seq\.?|[-–—]\s*\d", body, re.I):
            broad.append({
                "raw_citation": raw, "citation_kind": "usc", "title": str(int(match.group("title"))),
                "section": "", "subsections": "", "canonical_authority_id": "",
                "is_broad": "true", "parallel_aliases": "", "_span": match.span(),
            })
        else:
            locators = re.findall(r"\d+[A-Za-z]?(?:\s*\([A-Za-z0-9]+\))*", body)
            for locator in locators:
                section_match = re.match(r"(?P<section>\d+[A-Za-z]?)(?P<subs>.*)", locator.strip())
                assert section_match
                item = {
                    "raw_citation": raw, "citation_kind": "usc",
                    "title": str(int(match.group("title"))),
                    "section": section_match.group("section").lower(),
                    "subsections": re.sub(r"\s+", "", section_match.group("subs")),
                    "is_broad": "false", "parallel_aliases": "", "_span": match.span(),
                }
                item["canonical_authority_id"] = canonical_usc(
                    item["title"], item["section"], item["subsections"]
                )
                pinpoint.append(item)
        occupied.append(match.span())

    for match in TITLE_SECTION_RE.finditer(clause):
        if any(start <= match.start() < end or match.start() <= start < match.end()
               for start, end in occupied):
            continue
        raw = match.group(0).strip(" ,;:")
        for locator in re.findall(r"\d+[A-Za-z]?(?:\s*\([A-Za-z0-9]+\))*", match.group("locators")):
            section_match = re.match(r"(?P<section>\d+[A-Za-z]?)(?P<subs>.*)", locator.strip())
            assert section_match
            section = section_match.group("section").lower()
            subs = re.sub(r"\s+", "", section_match.group("subs"))
            pinpoint.append({
                "raw_citation": raw, "citation_kind": "usc", "title": str(int(match.group("title"))),
                "section": section, "subsections": subs,
                "canonical_authority_id": canonical_usc(match.group("title"), section, subs),
                "is_broad": "false", "parallel_aliases": "", "_span": match.span(),
            })
        occupied.append(match.span())

    # Act-section references are retained as pinpoint units only when they do not
    # immediately contain a parallel U.S.C. cite. The Act locator remains an alias
    # on the Code unit in that common citation form.
    for match in ACT_SECTION_RE.finditer(clause):
        nearby = [item for item in pinpoint + broad
                  if match.start() <= item.get("_span", (-1, -1))[0] <= match.end() + 80]
        raw = match.group(0).strip(" ,;:")
        if nearby:
            for item in nearby:
                item["parallel_aliases"] = raw
            continue
        act = re.sub(r"\s+", " ", match.group("act")).strip().lower()
        locators = re.findall(r"\d+[A-Za-z]?(?:\s*\([A-Za-z0-9]+\))*", match.group("locators"))
        for locator in locators:
            compact = re.sub(r"\s+", "", locator).lower()
            pinpoint.append({
                "raw_citation": raw,
                "citation_kind": "act_section",
                "title": "", "section": compact, "subsections": "",
                "canonical_authority_id": f"act:{re.sub(r'[^a-z0-9]+', '-', act).strip('-')}:{compact}",
                "is_broad": "false", "parallel_aliases": "",
            })

    for match in BROAD_RE.finditer(clause):
        if any(start <= match.start() < end for start, end in occupied):
            continue
        broad.append({
            "raw_citation": match.group(0).strip(" ,;:"), "citation_kind": "broad",
            "title": "", "section": "", "subsections": "",
            "canonical_authority_id": "", "is_broad": "true", "parallel_aliases": "",
        })

    # Deduplicate the same normalized authority within a clause, retaining literal
    # spellings as aliases so drafting style cannot inflate the denominator.
    deduped: dict[str, dict] = {}
    for item in pinpoint:
        original = item["canonical_authority_id"]
        key = ACT_TO_USC.get(original, original)
        if key != original:
            item["parallel_aliases"] = " | ".join(filter(None, [item.get("parallel_aliases", ""), item["raw_citation"]]))
            item["canonical_authority_id"] = key
            _, title, locator = key.split(":", 2)
            parsed = re.match(r"(?P<section>\d+[a-z]?)(?P<subs>.*)", locator)
            assert parsed
            item.update({"citation_kind": "usc", "title": title,
                         "section": parsed.group("section"), "subsections": parsed.group("subs")})
        if key not in deduped:
            deduped[key] = item
        elif item["raw_citation"] != deduped[key]["raw_citation"]:
            aliases = filter(None, [deduped[key].get("parallel_aliases", ""), item["raw_citation"]])
            deduped[key]["parallel_aliases"] = " | ".join(dict.fromkeys(aliases))
    for item in list(deduped.values()) + broad:
        item.pop("_span", None)
    return list(deduped.values()), broad


def read_census(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if rows and tuple(rows[0]) != CENSUS_FIELDS:
        raise ValueError(f"unexpected census schema: {list(rows[0])}")
    for row in rows:
        if row["recipient_class"] not in RECIPIENT_CLASSES:
            raise ValueError(f"invalid recipient class for {row['canonical_authority_id']}")
        if row["recipient_class"] != "unresolved":
            required = ("operative_excerpt", "rationale", "official_source_url", "review_status")
            if any(not row[field].strip() for field in required):
                raise ValueError(f"incomplete evidence for {row['canonical_authority_id']}")
    return rows


def census_match(census: list[dict], authority_id: str, date_text: str) -> dict | None:
    target = datetime.strptime(date_text, "%B %d, %Y").date()
    matches = []
    for row in census:
        if row["canonical_authority_id"] != authority_id:
            continue
        start = datetime.strptime(row["version_start"], "%Y-%m-%d").date()
        end = datetime.strptime(row["version_end"], "%Y-%m-%d").date() if row["version_end"] else None
        if start <= target and (end is None or target <= end):
            matches.append(row)
    if len(matches) > 1:
        raise ValueError(f"overlapping census versions for {authority_id} on {target}")
    return matches[0] if matches else None


def write_csv(path: Path, rows: list[dict], fields: tuple[str, ...] | list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def recipient_metrics(rows: list[dict]) -> dict:
    counts = Counter(row["recipient_class"] for row in rows)
    total = len(rows)
    president = counts["president_only"]
    agency = counts["agency_or_officer_only"]
    both = counts["both"]
    unresolved = counts["unresolved"]
    exclusive = president + agency
    power_resolved = exclusive + both
    resolved = total - unresolved
    percent = lambda numerator, denominator: 100 * numerator / denominator if denominator else None
    return {
        "pinpoint_occurrences": total,
        "resolved_occurrences": resolved,
        "resolved_coverage_percent": percent(resolved, total),
        "recipient_counts": dict(sorted(counts.items())),
        "exclusive_recipient_presidential_percent": percent(president, exclusive),
        "president_only_share_resolved_power_conferrals_percent": percent(president, power_resolved),
        "any_presidential_share_resolved_power_conferrals_percent": percent(president + both, power_resolved),
        "agency_only_share_resolved_power_conferrals_percent": percent(agency, power_resolved),
        "shared_share_resolved_power_conferrals_percent": percent(both, power_resolved),
        "strict_presidential_percent_all_pinpoint": percent(president, total),
        "observed_any_presidential_percent_all_pinpoint": percent(president + both, total),
        "president_only_lower_bound_all_pinpoint_percent": percent(president, total),
        "president_only_upper_bound_all_pinpoint_percent": percent(president + unresolved, total),
        "any_presidential_lower_bound_all_pinpoint_percent": percent(president + both, total),
        "any_presidential_upper_bound_all_pinpoint_percent": percent(president + both + unresolved, total),
    }


def build(corpora: tuple[Path, ...] | list[Path], census_path: Path, output: Path) -> dict:
    corpus = load_corpus(list(corpora))
    retained = [row for row in corpus if ceremonial_reason(row) is None]
    census = read_census(census_path)
    occurrences: list[dict] = []
    broad_rows: list[dict] = []
    unmatched_signal_rows: list[dict] = []

    for row in retained:
        clauses = extract_vesting_clauses(row["doc_text"], row["doc_type"])
        seen_clause_units: set[tuple[str, ...]] = set()
        for clause_index, clause in enumerate(clauses, start=1):
            clause = authority_core(clause)
            if not clause:
                continue
            pinpoint, broad = parse_clause(clause)
            signature = tuple(sorted(item["canonical_authority_id"] for item in pinpoint)) + tuple(
                sorted(item["raw_citation"].lower() for item in broad)
            )
            if signature and signature in seen_clause_units:
                continue
            if signature:
                seen_clause_units.add(signature)
            if SPECIFIC_SIGNAL_RE.search(clause) and not pinpoint and not broad:
                unmatched_signal_rows.append({
                    "document_id": row[""], "date": row["date"], "doc_type": row["doc_type"],
                    "url": row["url"], "clause_index": clause_index, "raw_clause": clause,
                })
            for item in pinpoint:
                match = census_match(census, item["canonical_authority_id"], row["date"])
                occurrence = {
                    "occurrence_id": f"{row['']}:{clause_index}:{len(occurrences) + 1}",
                    "document_id": row[""], "date": row["date"], "president": row["president"],
                    "term": row["term"], "doc_type": row["doc_type"], "url": row["url"], "clause_index": clause_index,
                    "raw_clause": clause, **item,
                    "recipient_class": match["recipient_class"] if match else "unresolved",
                    "mapping_status": "resolved" if match else "missing_census_version",
                }
                occurrences.append(occurrence)
            for item in broad:
                broad_rows.append({
                    "document_id": row[""], "date": row["date"], "president": row["president"],
                    "term": row["term"], "doc_type": row["doc_type"], "url": row["url"], "clause_index": clause_index,
                    "raw_clause": clause, **item,
                })

    metrics = recipient_metrics(occurrences)
    counts = Counter(row["recipient_class"] for row in occurrences)
    summary = {
        **metrics,
        "distinct_authorities": len({row["canonical_authority_id"] for row in occurrences}),
        "broad_references": len(broad_rows),
        "unmatched_specific_signal_clauses": len(unmatched_signal_rows),
    }

    write_csv(output / "citation_occurrences.csv", occurrences, OCCURRENCE_FIELDS)
    broad_fields = tuple(field for field in OCCURRENCE_FIELDS if field not in {"occurrence_id", "recipient_class", "mapping_status"})
    write_csv(output / "broad_references.csv", broad_rows, broad_fields)
    write_csv(output / "unmatched_specific_signals.csv", unmatched_signal_rows,
              ("document_id", "date", "doc_type", "url", "clause_index", "raw_clause"))
    write_csv(output / "recipient_summary.csv",
              [{"recipient_class": key, "occurrences": counts.get(key, 0)} for key in RECIPIENT_CLASSES],
              ("recipient_class", "occurrences"))
    breakdowns = []
    groups = [("all", "all", occurrences)]
    groups += [("directive_type", value, [row for row in occurrences if row["doc_type"] == value])
               for value in sorted({row["doc_type"] for row in occurrences})]
    groups += [("administration", f"{president} ({term})",
                [row for row in occurrences if row["president"] == president and row["term"] == term])
               for president, term in sorted({(row["president"], row["term"]) for row in occurrences})]
    metric_fields = [key for key in metrics if key != "recipient_counts"]
    for group_type, group, rows in groups:
        item = recipient_metrics(rows)
        breakdowns.append({"group_type": group_type, "group": group, **item,
                           **{f"count_{key}": item["recipient_counts"].get(key, 0)
                              for key in RECIPIENT_CLASSES}})
    write_csv(output / "recipient_breakdowns.csv", breakdowns,
              ["group_type", "group", *metric_fields, *[f"count_{key}" for key in RECIPIENT_CLASSES]])
    manifest = {
        "schema_version": 1,
        "source_files": [str(path.relative_to(ROOT)) for path in corpora],
        "source_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in corpora},
        "corpus_documents": len(corpus),
        "ceremonial_exclusions": len(corpus) - len(retained),
        "nonceremonial_documents": len(retained),
        "census_file": str(census_path.relative_to(ROOT)),
        "census_sha256": sha256(census_path) if census_path.exists() else None,
        "olrc_source_extract": "analysis/delegation-recipient/outputs/current_uscode_sources.csv",
        "olrc_source_extract_sha256": sha256(output / "current_uscode_sources.csv")
        if (output / "current_uscode_sources.csv").exists() else None,
        "reviewed_overrides_sha256": sha256(ANALYSIS_DIR / "reviewed_overrides.csv"),
        **summary,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", action="append", type=Path, dest="corpora")
    parser.add_argument("--census", type=Path, default=DEFAULT_CENSUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(build(args.corpora or DEFAULT_CORPORA, args.census, args.output), indent=2))


if __name__ == "__main__":
    main()
