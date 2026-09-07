#!/usr/bin/env python3
"""Extract cited U.S. Code sections from an official OLRC XML release archive."""

from __future__ import annotations

import argparse
import csv
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NS = "{http://xml.house.gov/schemas/uslm/1.0}"
FIELDS = (
    "canonical_authority_id", "title", "section", "subsections", "heading", "operative_text",
    "source_credit", "amendment_notes", "olrc_identifier", "official_source_url",
    "release", "source_status",
)


def clean_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return re.sub(r"\s+", " ", "".join(element.itertext())).strip()


def section_operative_text(section: ET.Element) -> str:
    pieces = []
    excluded = {f"{NS}num", f"{NS}heading", f"{NS}sourceCredit", f"{NS}notes"}
    for child in section:
        if child.tag not in excluded:
            pieces.append(clean_text(child))
    return re.sub(r"\s+", " ", " ".join(filter(None, pieces))).strip()


def requested_sections(occurrences: Path) -> dict[tuple[str, str], set[str]]:
    requested: dict[tuple[str, str], set[str]] = {}
    with occurrences.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["citation_kind"] == "usc":
                requested.setdefault((row["title"], row["section"]), set()).add(
                    row["canonical_authority_id"]
                )
    return requested


def source_url(title: str, section: str) -> str:
    return f"https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title{title}-section{section}"


def extract(archive: Path, requested: dict[tuple[str, str], set[str]], release: str) -> list[dict]:
    by_title: dict[str, set[str]] = {}
    for title, section in requested:
        by_title.setdefault(title, set()).add(section)
    rows = []
    with zipfile.ZipFile(archive) as bundle:
        for title, sections in sorted(by_title.items(), key=lambda item: int(item[0])):
            member = f"usc{int(title):02d}.xml"
            if member not in bundle.namelist():
                for section in sections:
                    for authority in requested[(title, section)]:
                        rows.append({"canonical_authority_id": authority, "title": title,
                                     "section": section, "release": release,
                                     "source_status": "title_missing"})
                continue
            root = ET.fromstring(bundle.read(member))
            found = set()
            for element in root.iter(f"{NS}section"):
                identifier = element.attrib.get("identifier", "")
                match = re.fullmatch(rf"/us/usc/t{int(title)}/s([^/]+)", identifier)
                if not match or match.group(1).lower() not in {s.lower() for s in sections}:
                    continue
                section = match.group(1).lower()
                found.add(section)
                content = element.find(f"{NS}content")
                notes = element.find(f"{NS}notes")
                amendment_text = []
                if notes is not None:
                    for note in notes.iter(f"{NS}note"):
                        if note.attrib.get("topic") == "amendments":
                            amendment_text.append(clean_text(note))
                for authority in requested[(title, section)]:
                    locator = authority.split(":", 2)[2]
                    parts = re.findall(r"\(([^)]+)\)", locator)
                    target = content
                    target_identifier = identifier
                    status = "found"
                    if parts:
                        target_identifier = identifier + "".join(f"/{part}" for part in parts)
                        target = next((node for node in element.iter()
                                       if node.attrib.get("identifier") == target_identifier), None)
                        if target is None:
                            status = "subsection_missing"
                    rows.append({
                        "canonical_authority_id": authority, "title": title, "section": section,
                        "subsections": locator[len(section):],
                        "heading": clean_text(element.find(f"{NS}heading")),
                        "operative_text": clean_text(target) if parts else section_operative_text(element),
                        "source_credit": clean_text(element.find(f"{NS}sourceCredit")),
                        "amendment_notes": " | ".join(amendment_text),
                        "olrc_identifier": target_identifier,
                        "official_source_url": source_url(title, section),
                        "release": release, "source_status": status,
                    })
            for section in sections - found:
                for authority in requested[(title, section)]:
                    rows.append({"canonical_authority_id": authority, "title": title,
                                 "section": section, "official_source_url": source_url(title, section),
                                 "release": release, "source_status": "section_missing"})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--occurrences", type=Path, default=Path(__file__).with_name("outputs") / "citation_occurrences.csv")
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("outputs") / "current_uscode_sources.csv")
    parser.add_argument("--release", default="119-102not101")
    args = parser.parse_args()
    rows = extract(args.archive, requested_sections(args.occurrences), args.release)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)
    print(f"wrote {len(rows)} section records to {args.output}")


if __name__ == "__main__":
    main()
