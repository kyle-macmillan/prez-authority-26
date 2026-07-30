"""Build automatic executive-order parent edges.

Stage A intentionally operates on unmasked text.  Every resolvable reference to an
earlier EO creates an edge; relation cues near the reference provide optional labels.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from precedent_preprocess import preprocess_for_similarity
from segmenter import segment_ordering


# UCSB omits the "-A" suffix from seven duplicate-number URLs.  The corrected
# identifiers below are verified against the National Archives EO disposition tables.
EO_NUMBER_CORRECTIONS = {
    "3060": "11359-A",
    "3726": "10695-A",
    "3849": "10571-A",
    "4004": "10417-A",
    "4397": "10026-A",
    "4450": "9973-A",
    "4491": "9934-A",
}

EO_URL_RE = re.compile(r"/executive-order-(\d{4,5})(?:-|$)", re.IGNORECASE)
EO_REFERENCE_RE = re.compile(
    r"\b(?:Executive\s+Orders?|Exec(?:utive)?\.?\s+Orders?|E\.?\s*O\.?)"
    r"(?:\s+Nos?\.?)?\s+(?P<number>\d{4,5}(?:\s*-\s*A)?)\b",
    re.IGNORECASE,
)

# Relation labels are deliberately limited to the actions agreed for automatic edges.
# The closest cue in the containing sentence wins; citation_discussion is the fallback.
RELATION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("amends", re.compile(r"\bamend(?:s|ed|ing|ment)?\b|\brevis(?:e|es|ed|ing|ion)\b", re.I)),
    ("revokes", re.compile(r"\brevok(?:e|es|ed|ing|ation)\b|\brescind(?:s|ed|ing)?\b", re.I)),
    ("supersedes", re.compile(r"\bsupersed(?:e|es|ed|ing)\b", re.I)),
    ("modifies", re.compile(r"\bmodif(?:y|ies|ied|ying|ication)\b|\badjust(?:s|ed|ing|ment)?\b", re.I)),
    ("continues", re.compile(r"\bcontinu(?:e|es|ed|ing|ation)\b|\bextend(?:s|ed|ing)?\b", re.I)),
    ("replaces", re.compile(r"\breplac(?:e|es|ed|ing|ement)\b", re.I)),
    (
        "delegates_authority_under",
        re.compile(
            r"\bdelegat(?:e|es|ed|ing|ion)\b.{0,80}\b(?:authority\s+)?under\b"
            r"|\bauthority\s+under\b.{0,80}\bdelegat",
            re.I,
        ),
    ),
)

EDGE_FIELDS = (
    "child_id",
    "child_eo_number",
    "child_date",
    "parent_id",
    "parent_eo_number",
    "parent_date",
    "relation",
    "reference_text",
    "context",
    "reference_start",
)


@dataclass(frozen=True)
class EODocument:
    document_id: str
    eo_number: str
    date: datetime
    date_text: str
    url: str
    text: str


@dataclass(frozen=True)
class EOReference:
    eo_number: str
    text: str
    start: int
    context: str
    relation: str


def parse_date(value: str) -> datetime:
    return datetime.strptime(value.strip(), "%B %d, %Y")


def eo_number_from_url(url: str) -> str:
    match = EO_URL_RE.search(url)
    if not match:
        raise ValueError(f"cannot recover EO number from URL: {url}")
    return match.group(1)


def normalize_eo_number(value: str) -> str:
    return re.sub(r"\s*-\s*A$", "-A", value.strip(), flags=re.I).upper()


def eo_sort_key(value: str) -> tuple[int, int]:
    normalized = normalize_eo_number(value)
    return int(normalized.split("-", 1)[0]), 1 if normalized.endswith("-A") else 0


def load_eos(path: Path) -> list[EODocument]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        documents = [
            EODocument(
                document_id=row[""],
                eo_number=EO_NUMBER_CORRECTIONS.get(row[""], eo_number_from_url(row["url"])),
                date=parse_date(row["date"]),
                date_text=row["date"],
                url=row["url"],
                text=row["doc_text"],
            )
            for row in rows
            if row["doc_type"] == "executive_order"
        ]
    numbers = [normalize_eo_number(document.eo_number) for document in documents]
    if len(numbers) != len(set(numbers)):
        raise ValueError("EO numbers are not unique in the corpus")
    return documents


def _sentence_context(text: str, start: int, end: int) -> str:
    """Return the double-space paragraph containing a reference."""
    left = text.rfind("  ", 0, start)
    right = text.find("  ", end)
    return text[left + 2 if left >= 0 else 0 : right if right >= 0 else len(text)].strip()


def _relation_for_reference(context: str, relative_start: int) -> str:
    matches: list[tuple[int, str]] = []
    for label, pattern in RELATION_PATTERNS:
        for match in pattern.finditer(context):
            matches.append((abs(match.start() - relative_start), label))
    return min(matches)[1] if matches else "citation_discussion"


def extract_eo_references(text: str) -> list[EOReference]:
    references = []
    for match in EO_REFERENCE_RE.finditer(text):
        context = _sentence_context(text, match.start(), match.end())
        context_start = text.find(context, max(0, match.start() - len(context) - 2))
        relative_start = match.start() - max(0, context_start)
        references.append(
            EOReference(
                eo_number=normalize_eo_number(match.group("number")),
                text=match.group(0),
                start=match.start(),
                context=context,
                relation=_relation_for_reference(context, relative_start),
            )
        )
    return references


def is_earlier(parent: EODocument, child: EODocument) -> bool:
    """Chronology rule, using EO number to order documents issued on the same date."""
    return parent.date < child.date or (
        parent.date == child.date and eo_sort_key(parent.eo_number) < eo_sort_key(child.eo_number)
    )


def build_automatic_edges(
    documents: list[EODocument],
) -> tuple[list[dict[str, str | int]], list[dict[str, str | int]]]:
    by_number = {normalize_eo_number(document.eo_number): document for document in documents}
    edges: list[dict[str, str | int]] = []
    unresolved_references: list[dict[str, str | int]] = []
    seen: set[tuple[str, str, str]] = set()

    for child in documents:
        for reference in extract_eo_references(child.text):
            parent = by_number.get(reference.eo_number)
            if parent is None or not is_earlier(parent, child):
                unresolved_references.append(
                    {
                        "child_id": child.document_id,
                        "child_eo_number": child.eo_number,
                        "referenced_eo_number": reference.eo_number,
                        "reason": "outside_corpus" if parent is None else "not_earlier",
                        "reference_text": reference.text,
                        "context": reference.context,
                    }
                )
                continue

            key = (child.document_id, parent.document_id, reference.relation)
            if key in seen:
                continue
            seen.add(key)
            edges.append(
                {
                    "child_id": child.document_id,
                    "child_eo_number": child.eo_number,
                    "child_date": child.date_text,
                    "parent_id": parent.document_id,
                    "parent_eo_number": parent.eo_number,
                    "parent_date": parent.date_text,
                    "relation": reference.relation,
                    "reference_text": reference.text,
                    "context": reference.context,
                    "reference_start": reference.start,
                }
            )

    edges.sort(
        key=lambda row: (
            eo_sort_key(str(row["child_eo_number"])),
            eo_sort_key(str(row["parent_eo_number"])),
            str(row["relation"]),
        )
    )
    return edges, unresolved_references


def write_csv(path: Path, rows: list[dict], fields: tuple[str, ...] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(fields or (rows[0].keys() if rows else ()))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_similarity_artifacts(
    documents: list[EODocument], automatic_child_ids: set[str]
) -> tuple[list[dict], list[dict]]:
    document_rows = []
    segment_rows = []
    for document in documents:
        cleaned, masked_spans, removed = preprocess_for_similarity(document.text)
        segments = segment_ordering(cleaned, "executive_order")
        operative_index = 0
        for segment in segments:
            if segment.seg_type != "order_action":
                continue
            operative_index += 1
            segment_rows.append(
                {
                    "segment_id": f"{document.document_id}:oa:{operative_index:03d}",
                    "document_id": document.document_id,
                    "eo_number": document.eo_number,
                    "date": document.date_text,
                    "segment_index": operative_index,
                    "text": segment.text,
                    "chunk_indices": segment.chunk_indices,
                }
            )
        document_rows.append(
            {
                "document_id": document.document_id,
                "eo_number": document.eo_number,
                "date": document.date_text,
                "url": document.url,
                "has_automatic_parent": document.document_id in automatic_child_ids,
                "cleaned_masked_text": cleaned,
                "masked_authorities": [
                    {
                        "start": span.start,
                        "end": span.end,
                        "text": span.text,
                        "kind": span.kind,
                    }
                    for span in masked_spans
                ],
                "removed_boilerplate": removed,
                "operative_segment_count": operative_index,
            }
        )
    return document_rows, segment_rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=Path("data/4_28_2026_build_dev.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/parent_analysis"))
    args = parser.parse_args()

    documents = load_eos(args.corpus)
    edges, unresolved_references = build_automatic_edges(documents)
    automatic_child_ids = {str(row["child_id"]) for row in edges}
    unresolved_children = [
        {
            "document_id": document.document_id,
            "eo_number": document.eo_number,
            "date": document.date_text,
            "url": document.url,
        }
        for document in documents
        if document.document_id not in automatic_child_ids
    ]

    write_csv(args.output_dir / "automatic_edges.csv", edges, EDGE_FIELDS)
    write_csv(args.output_dir / "unresolved_references.csv", unresolved_references)
    write_csv(args.output_dir / "unresolved_children.csv", unresolved_children)
    document_rows, segment_rows = build_similarity_artifacts(documents, automatic_child_ids)
    write_jsonl(args.output_dir / "eo_similarity_documents.jsonl", document_rows)
    write_jsonl(args.output_dir / "eo_operative_segments.jsonl", segment_rows)
    print(
        f"{len(documents)} EOs; {len(edges)} automatic edges; "
        f"{len(automatic_child_ids)} children with automatic parents; "
        f"{len(unresolved_children)} unresolved children; "
        f"{len(unresolved_references)} unresolved references; "
        f"{len(segment_rows)} operative segments"
    )


if __name__ == "__main__":
    main()
