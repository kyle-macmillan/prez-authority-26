#!/usr/bin/env python3
"""Build Day 1 and Week 1 substantive-policy review inventories."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPORA = (
    ROOT / "data/4_28_2026_build_dev.csv",
    ROOT / "data/4_28_2026_build_holdout.csv",
)
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "outputs"

STARTS = (
    ("eisenhower_1953", "Dwight D. Eisenhower", "1953-01-20"),
    ("kennedy_1961", "John F. Kennedy", "1961-01-20"),
    ("nixon_1969", "Richard Nixon", "1969-01-20"),
    ("carter_1977", "Jimmy Carter", "1977-01-20"),
    ("reagan_1981", "Ronald Reagan", "1981-01-20"),
    ("ghwbush_1989", "George Bush", "1989-01-20"),
    ("clinton_1993", "William J. Clinton", "1993-01-20"),
    ("gwbush_2001", "George W. Bush", "2001-01-20"),
    ("obama_2009", "Barack Obama", "2009-01-20"),
    ("trump_2017", "Donald J. Trump", "2017-01-20"),
    ("biden_2021", "Joseph R. Biden, Jr.", "2021-01-20"),
    ("trump_2025", "Donald J. Trump", "2025-01-20"),
)
ISSUES = {
    "abortion_reproductive_policy": re.compile(r"\b(?:abortion|reproductive|family planning|Mexico City policy)\b", re.I),
    "climate_environment_energy": re.compile(r"\b(?:climate|environment|energy|oil|gas|coal|Paris Agreement|conservation)\b", re.I),
    "immigration_borders": re.compile(r"\b(?:immigra|border|refugee|asylum|visa|entry into the United States|deport)\w*\b", re.I),
    "health_public_health": re.compile(r"\b(?:health care|healthcare|Medicaid|Medicare|public health|pandemic|COVID|disease)\b", re.I),
    "foreign_security_policy": re.compile(r"\b(?:foreign policy|national security|military|defense|alliance|United Nations|sanction|international)\w*\b", re.I),
    "civil_rights_equity": re.compile(r"\b(?:civil rights|discrimination|equal protection|racial equity|gender identity|sexual orientation)\b", re.I),
    "economic_labor_policy": re.compile(r"\b(?:economy|economic|labor|worker|employment|wage|tax|tariff|trade)\w*\b", re.I),
}
CEREMONIAL = re.compile(r"\bhalf[- ]?(?:staff|mast)\b|\bnational day of (?:prayer|thanksgiving|renewal)\b", re.I)
INTERNAL = re.compile(r"\b(?:ethics commitment|standards of official conduct|hiring freeze|order of succession|noncareer employees?)\b", re.I)


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%B %d, %Y").date()


def window_membership(document_date: date, start: date) -> tuple[int, bool, bool]:
    days = (document_date - start).days
    return days, days == 0, 0 <= days <= 6


def proposed_issues(text: str) -> list[str]:
    return [issue for issue, pattern in ISSUES.items() if pattern.search(text)]


def eligibility_proposal(text: str) -> str:
    if CEREMONIAL.search(text): return "exclude_ceremonial"
    if INTERNAL.search(text): return "exclude_internal_management"
    return "review_substantive_policy"


def read_corpus(paths: list[Path] | tuple[Path, ...]) -> list[dict[str, str]]:
    rows = []
    for path in paths:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows.extend(csv.DictReader(handle))
    ids = [row.get("", "") for row in rows]
    if not all(ids) or len(ids) != len(set(ids)): raise ValueError("corpus IDs must be present and unique")
    return rows


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def build(corpus_paths: list[Path] | tuple[Path, ...], output: Path) -> dict:
    corpus = read_corpus(corpus_paths); inventory = []
    for administration_id, president, start_text in STARTS:
        start = date.fromisoformat(start_text)
        for row in corpus:
            if row["president"] != president: continue
            document_date = parse_date(row["date"])
            days, day1, week1 = window_membership(document_date, start)
            if not week1: continue
            text = row["doc_text"]
            issues = proposed_issues(text)
            inventory.append({
                "administration_id": administration_id, "president": president,
                "inauguration_date": start.isoformat(), "document_id": row[""],
                "document_date": document_date.isoformat(), "days_since_inauguration": days,
                "is_day_1": str(day1).lower(), "is_week_1": "true", "document_type": row["doc_type"],
                "url": row["url"], "eligibility_proposal": eligibility_proposal(text),
                "proposed_issue_ids": ";".join(issues), "substantive_policy_decision": "",
                "final_issue_ids": "", "position_summary": "", "action_summary": "",
                "evidence": "", "reviewer": "", "review_notes": "", "archive_check_status": "pending",
            })
    inventory.sort(key=lambda x: (x["inauguration_date"], x["document_date"], int(x["document_id"])))
    fields = ["administration_id", "president", "inauguration_date", "document_id", "document_date",
              "days_since_inauguration", "is_day_1", "is_week_1", "document_type", "url",
              "eligibility_proposal", "proposed_issue_ids", "substantive_policy_decision", "final_issue_ids",
              "position_summary", "action_summary", "evidence", "reviewer", "review_notes", "archive_check_status"]
    write_csv(output / "cohort_review.csv", inventory, fields)
    summary = []
    for administration_id, president, start_text in STARTS:
        rows = [x for x in inventory if x["administration_id"] == administration_id]
        summary.append({"administration_id": administration_id, "president": president,
                        "inauguration_date": start_text, "day_1_documents": sum(x["is_day_1"] == "true" for x in rows),
                        "week_1_documents": len(rows), "archive_check_status": "pending"})
    write_csv(output / "administration_summary.csv", summary,
              ["administration_id", "president", "inauguration_date", "day_1_documents", "week_1_documents", "archive_check_status"])
    issue_counts = Counter(issue for row in inventory for issue in row["proposed_issue_ids"].split(";") if issue)
    write_csv(output / "proposed_issue_summary.csv",
              [{"issue_id": issue, "documents": issue_counts.get(issue, 0)} for issue in ISSUES],
              ["issue_id", "documents"])
    manifest = {"schema_version": 1, "corpora": [str(path) for path in corpus_paths],
                "corpus_sha256": {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in corpus_paths},
                "window_definition": "inauguration date through six following calendar days",
                "administration_starts": len(STARTS), "cohort_documents": len(inventory),
                "day_1_documents": sum(x["is_day_1"] == "true" for x in inventory),
                "archive_audit_complete": False}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, action="append", dest="corpora",
                        help="Corpus CSV; repeat to combine partitions. Defaults to development plus holdout.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(); print(json.dumps(build(args.corpora or DEFAULT_CORPORA, args.output), indent=2))


if __name__ == "__main__": main()
