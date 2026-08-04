"""Build presidential-directive parent-analysis artifacts.

Stage A operates on unmasked text. Resolvable references create automatic parent
edges only when the referenced document has the same type as the child. Cross-type
and ambiguous references are retained separately for audit.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

from ceremonial import ceremonial_reason
from precedent_preprocess import preprocess_for_similarity
from segmenter import segment_ordering


DIRECTIVE_TYPES = ("executive_order", "memorandum", "proclamation", "letter")
DEFAULT_CORPORA = (
    Path("data/4_28_2026_build_dev.csv"),
    Path("data/4_28_2026_build_holdout.csv"),
)
EXPECTED_FULL_CORPUS_SIZE = 18_418

# UCSB omits the "-A" suffix from seven duplicate-number EO URLs.
EO_NUMBER_CORRECTIONS = {
    "3060": "11359-A",
    "3726": "10695-A",
    "3849": "10571-A",
    "4004": "10417-A",
    "4397": "10026-A",
    "4450": "9973-A",
    "4491": "9934-A",
}

EO_URL_RE = re.compile(r"/executive-order-(\d{4,5})(?:-|$)", re.I)
PROCLAMATION_URL_RE = re.compile(r"/proclamation-(\d+)(?:-|$)", re.I)
EO_REFERENCE_RE = re.compile(
    r"\b(?:Executive\s+Orders?|Exec(?:utive)?\.?\s+Orders?|E\.?\s*O\.?)"
    r"(?:\s+Nos?\.?)?\s+(?P<identifier>\d{4,5}(?:\s*-\s*A)?)\b",
    re.I,
)
PROCLAMATION_REFERENCE_RE = re.compile(
    r"\bProclamations?(?:\s+Nos?\.?)?\s+(?P<identifier>\d+)\b", re.I
)
MEMORANDUM_IDENTIFIER_RE = re.compile(
    r"\b(?:(?:National\s+Security|Homeland\s+Security|Presidential\s+Policy|"
    r"Presidential\s+Study|National\s+Security\s+Presidential)\s+Directive\s*/?\s*)?"
    r"(?P<identifier>(?:NSD|PPD|PSD|NSDD|NSPD|HSPD|PDD|NSM|NSPM)-\s*\d+)\b"
    r"|\bPresidential\s+Determination(?:\s+No\.?)?\s+"
    r"(?P<determination>\d{4}\s*[-–—]\s*\d+)\b",
    re.I,
)
DATE_TEXT = (
    r"(?:January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+\d{1,2},\s+\d{4}"
)
UNNUMBERED_DATE_REFERENCE_RE = re.compile(
    rf"\b(?P<kind>memorandum|letter)(?:\s+(?:to|for|from)\b.{{0,100}}?)?"
    rf"\s+(?:of|dated|on)\s+(?P<date>{DATE_TEXT})\b",
    re.I,
)
UNNUMBERED_TITLE_REFERENCE_RE = re.compile(
    r"\b(?P<kind>memorandum|letter)(?:\s+(?:titled|entitled|regarding|concerning))?"
    r"\s*[\"“](?P<title>[^\"”]{4,300})[\"”]",
    re.I,
)

REFERENCE_PATTERNS = (
    ("executive_order", EO_REFERENCE_RE),
    ("proclamation", PROCLAMATION_REFERENCE_RE),
    ("memorandum", MEMORANDUM_IDENTIFIER_RE),
)

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
    "parent_id",
    "document_type",
    "child_identifier",
    "parent_identifier",
    "child_date",
    "parent_date",
    "relation",
    "reference_text",
    "context",
    "reference_start",
)

UNRESOLVED_REFERENCE_FIELDS = (
    "child_id",
    "child_document_type",
    "child_identifier",
    "referenced_document_type",
    "referenced_identifier",
    "referenced_title",
    "referenced_date",
    "reason",
    "reference_text",
    "context",
)

CEREMONIAL_EXCLUSION_FIELDS = (
    "document_id",
    "document_type",
    "identifier",
    "title",
    "date",
    "url",
    "exclusion_reason",
)


@dataclass(frozen=True)
class DirectiveDocument:
    document_id: str
    document_type: str
    identifier: str
    title: str
    date: datetime
    date_text: str
    url: str
    text: str


@dataclass(frozen=True)
class DirectiveReference:
    document_type: str
    identifier: str
    title: str
    date_text: str
    text: str
    start: int
    context: str
    relation: str


def parse_date(value: str) -> datetime:
    return datetime.strptime(value.strip(), "%B %d, %Y")


def normalize_identifier(value: str) -> str:
    value = re.sub(r"\s*[-–—]\s*", "-", value.strip())
    return re.sub(r"\s+", "", value).upper()


def normalize_title(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def title_from_url(url: str, document_type: str, identifier: str = "") -> str:
    slug = unquote(url.rstrip("/").rsplit("/", 1)[-1])
    prefixes = {
        "executive_order": rf"^executive-order-{re.escape(identifier)}-?",
        "proclamation": rf"^proclamation-{re.escape(identifier)}-?",
        "memorandum": r"^(?:memorandum|directive)-",
        "letter": r"^letter-",
    }
    title_slug = re.sub(prefixes[document_type], "", slug, flags=re.I)
    return title_slug.replace("-", " ").strip()


def eo_number_from_url(url: str) -> str:
    match = EO_URL_RE.search(url)
    if not match:
        raise ValueError(f"cannot recover EO number from URL: {url}")
    return match.group(1)


def _identifier_from_row(row: dict[str, str]) -> str:
    document_type = row["doc_type"]
    if document_type == "executive_order":
        return EO_NUMBER_CORRECTIONS.get(row[""], eo_number_from_url(row["url"]))
    if document_type == "proclamation":
        match = PROCLAMATION_URL_RE.search(row["url"])
        return match.group(1) if match else ""
    if document_type == "memorandum":
        match = MEMORANDUM_IDENTIFIER_RE.search(row["doc_text"][:500])
        if match:
            return normalize_identifier(match.group("identifier") or match.group("determination"))
    return ""


def load_directives(path: Path) -> list[DirectiveDocument]:
    documents = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["doc_type"] not in DIRECTIVE_TYPES:
                continue
            identifier = _identifier_from_row(row)
            documents.append(
                DirectiveDocument(
                    document_id=row[""],
                    document_type=row["doc_type"],
                    identifier=identifier,
                    title=title_from_url(row["url"], row["doc_type"], identifier),
                    date=parse_date(row["date"]),
                    date_text=row["date"],
                    url=row["url"],
                    text=row["doc_text"],
                )
            )
    return documents


def load_directive_corpus(paths: Iterable[Path]) -> list[DirectiveDocument]:
    """Load multiple corpus partitions while requiring unique document IDs."""
    documents = [document for path in paths for document in load_directives(path)]
    document_ids = [document.document_id for document in documents]
    if len(document_ids) != len(set(document_ids)):
        raise ValueError("corpus partitions contain duplicate document IDs")
    return documents


def load_eos(path: Path) -> list[DirectiveDocument]:
    """Compatibility helper for callers that still need the EO subset."""
    return [doc for doc in load_directives(path) if doc.document_type == "executive_order"]


def _sentence_context(text: str, start: int, end: int) -> str:
    left = text.rfind("  ", 0, start)
    right = text.find("  ", end)
    return text[left + 2 if left >= 0 else 0 : right if right >= 0 else len(text)].strip()


def _relation_for_reference(context: str, relative_start: int) -> str:
    matches = [
        (abs(match.start() - relative_start), label)
        for label, pattern in RELATION_PATTERNS
        for match in pattern.finditer(context)
    ]
    return min(matches)[1] if matches else "citation_discussion"


def _reference(
    text: str,
    match: re.Match[str],
    document_type: str,
    *,
    identifier: str = "",
    title: str = "",
    date_text: str = "",
) -> DirectiveReference:
    context = _sentence_context(text, match.start(), match.end())
    context_start = text.find(context, max(0, match.start() - len(context) - 2))
    relative_start = match.start() - max(0, context_start)
    return DirectiveReference(
        document_type=document_type,
        identifier=normalize_identifier(identifier) if identifier else "",
        title=title.strip(),
        date_text=date_text.strip(),
        text=match.group(0),
        start=match.start(),
        context=context,
        relation=_relation_for_reference(context, relative_start),
    )


def extract_directive_references(text: str) -> list[DirectiveReference]:
    references = []
    for document_type, pattern in REFERENCE_PATTERNS:
        for match in pattern.finditer(text):
            identifier = match.groupdict().get("identifier") or match.groupdict().get("determination")
            references.append(_reference(text, match, document_type, identifier=identifier or ""))
    for match in UNNUMBERED_DATE_REFERENCE_RE.finditer(text):
        references.append(
            _reference(
                text,
                match,
                "memorandum" if match.group("kind").lower().startswith("memo") else "letter",
                date_text=match.group("date"),
            )
        )
    for match in UNNUMBERED_TITLE_REFERENCE_RE.finditer(text):
        references.append(
            _reference(
                text,
                match,
                "memorandum" if match.group("kind").lower().startswith("memo") else "letter",
                title=match.group("title"),
            )
        )
    references.sort(key=lambda reference: reference.start)
    return references


def extract_eo_references(text: str) -> list[DirectiveReference]:
    """Compatibility helper returning only EO references."""
    return [
        reference
        for reference in extract_directive_references(text)
        if reference.document_type == "executive_order"
    ]


def is_earlier(parent: DirectiveDocument, child: DirectiveDocument) -> bool:
    return parent.date < child.date


def _resolve_reference(
    reference: DirectiveReference,
    by_identifier: dict[tuple[str, str], list[DirectiveDocument]],
    by_title: dict[tuple[str, str], list[DirectiveDocument]],
    by_date: dict[tuple[str, str], list[DirectiveDocument]],
) -> tuple[DirectiveDocument | None, str]:
    if reference.identifier:
        matches = by_identifier.get((reference.document_type, reference.identifier), [])
        if reference.title:
            normalized_title = normalize_title(reference.title)
            matches = [match for match in matches if normalize_title(match.title) == normalized_title]
        if reference.date_text:
            matches = [match for match in matches if match.date_text == reference.date_text]
        if len(matches) == 1:
            return matches[0], ""
        return None, "outside_corpus" if not matches else "ambiguous_match"
    if reference.title:
        matches = by_title.get((reference.document_type, normalize_title(reference.title)), [])
    elif reference.date_text:
        matches = by_date.get((reference.document_type, reference.date_text), [])
    else:
        matches = []
    if len(matches) == 1:
        return matches[0], ""
    return None, "outside_corpus" if not matches else "ambiguous_match"


def build_automatic_edges(
    documents: list[DirectiveDocument],
) -> tuple[list[dict[str, str | int]], list[dict[str, str | int]]]:
    by_identifier: dict[tuple[str, str], list[DirectiveDocument]] = {}
    by_title: dict[tuple[str, str], list[DirectiveDocument]] = {}
    by_date: dict[tuple[str, str], list[DirectiveDocument]] = {}
    for document in documents:
        if document.identifier:
            by_identifier.setdefault(
                (document.document_type, normalize_identifier(document.identifier)), []
            ).append(document)
        by_title.setdefault((document.document_type, normalize_title(document.title)), []).append(document)
        by_date.setdefault((document.document_type, document.date_text), []).append(document)

    edges = []
    unresolved_references = []
    seen: set[tuple[str, str, str]] = set()
    for child in documents:
        for reference in extract_directive_references(child.text):
            parent, reason = _resolve_reference(reference, by_identifier, by_title, by_date)
            if parent is not None and parent.document_id == child.document_id:
                # Numbered memorandum families commonly begin with their own identifier.
                # A document header is not an explicit relationship.
                continue
            if parent is not None and parent.document_type != child.document_type:
                reason = "cross_type_reference"
            elif parent is not None and not is_earlier(parent, child):
                reason = "not_earlier"
            if parent is None or reason:
                unresolved_references.append(
                    {
                        "child_id": child.document_id,
                        "child_document_type": child.document_type,
                        "child_identifier": child.identifier,
                        "referenced_document_type": reference.document_type,
                        "referenced_identifier": reference.identifier,
                        "referenced_title": reference.title,
                        "referenced_date": reference.date_text,
                        "reason": reason,
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
                    "parent_id": parent.document_id,
                    "document_type": child.document_type,
                    "child_identifier": child.identifier,
                    "parent_identifier": parent.identifier,
                    "child_date": child.date_text,
                    "parent_date": parent.date_text,
                    "relation": reference.relation,
                    "reference_text": reference.text,
                    "context": reference.context,
                    "reference_start": reference.start,
                }
            )
    edges.sort(key=lambda row: (str(row["document_type"]), str(row["child_date"]), str(row["child_id"])))
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
    documents: list[DirectiveDocument], automatic_child_ids: set[str]
) -> tuple[list[dict], list[dict]]:
    document_rows = []
    segment_rows = []
    for document in documents:
        cleaned, masked_spans, removed = preprocess_for_similarity(document.text)
        segments = segment_ordering(cleaned, document.document_type)
        operative_index = 0
        for segment in segments:
            if segment.seg_type != "order_action":
                continue
            operative_index += 1
            segment_rows.append(
                {
                    "segment_id": f"{document.document_id}:oa:{operative_index:03d}",
                    "document_id": document.document_id,
                    "document_type": document.document_type,
                    "identifier": document.identifier,
                    "date": document.date_text,
                    "segment_index": operative_index,
                    "text": segment.text,
                    "chunk_indices": segment.chunk_indices,
                }
            )
        document_rows.append(
            {
                "document_id": document.document_id,
                "document_type": document.document_type,
                "identifier": document.identifier,
                "title": document.title,
                "date": document.date_text,
                "url": document.url,
                "has_automatic_parent": document.document_id in automatic_child_ids,
                "cleaned_masked_text": cleaned,
                "masked_authorities": [
                    {"start": span.start, "end": span.end, "text": span.text, "kind": span.kind}
                    for span in masked_spans
                ],
                "removed_boilerplate": removed,
                "operative_segment_count": operative_index,
            }
        )
    return document_rows, segment_rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--corpus",
        dest="corpora",
        action="append",
        type=Path,
        help="Corpus CSV to include; repeat for multiple partitions. Defaults to dev plus holdout.",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data/parent_analysis"))
    parser.add_argument(
        "--include-ceremonial",
        action="store_true",
        help="Retain codebook-defined ceremonial directives (excluded by default).",
    )
    args = parser.parse_args()

    corpus_paths = tuple(args.corpora) if args.corpora else DEFAULT_CORPORA
    all_documents = load_directive_corpus(corpus_paths)
    if not args.corpora and len(all_documents) != EXPECTED_FULL_CORPUS_SIZE:
        raise ValueError(
            f"expected {EXPECTED_FULL_CORPUS_SIZE:,} full-corpus directives, "
            f"found {len(all_documents):,}"
        )
    ceremonial_exclusions = []
    if not args.include_ceremonial:
        for document in all_documents:
            reason = ceremonial_reason({
                "doc_type": document.document_type,
                "doc_text": document.text,
                "title": document.title,
                "url": document.url,
            })
            if reason:
                ceremonial_exclusions.append({
                    "document_id": document.document_id,
                    "document_type": document.document_type,
                    "identifier": document.identifier,
                    "title": document.title,
                    "date": document.date_text,
                    "url": document.url,
                    "exclusion_reason": reason,
                })
    excluded_ids = {row["document_id"] for row in ceremonial_exclusions}
    documents = [row for row in all_documents if row.document_id not in excluded_ids]
    edges, unresolved_references = build_automatic_edges(documents)
    automatic_child_ids = {str(row["child_id"]) for row in edges}
    unresolved_children = [
        {
            "document_id": document.document_id,
            "document_type": document.document_type,
            "identifier": document.identifier,
            "title": document.title,
            "date": document.date_text,
            "url": document.url,
        }
        for document in documents
        if document.document_id not in automatic_child_ids
    ]

    write_csv(args.output_dir / "automatic_edges.csv", edges, EDGE_FIELDS)
    write_csv(
        args.output_dir / "unresolved_references.csv",
        unresolved_references,
        UNRESOLVED_REFERENCE_FIELDS,
    )
    write_csv(args.output_dir / "unresolved_children.csv", unresolved_children)
    write_csv(
        args.output_dir / "ceremonial_exclusions.csv",
        ceremonial_exclusions,
        CEREMONIAL_EXCLUSION_FIELDS,
    )
    document_rows, segment_rows = build_similarity_artifacts(documents, automatic_child_ids)
    write_jsonl(args.output_dir / "directive_similarity_documents.jsonl", document_rows)
    write_jsonl(args.output_dir / "directive_operative_segments.jsonl", segment_rows)
    print(
        f"{len(all_documents)} source directives; "
        f"{len(ceremonial_exclusions)} ceremonial exclusions; "
        f"{len(documents)} analyzed directives; {len(edges)} automatic edges; "
        f"{len(automatic_child_ids)} children with automatic parents; "
        f"{len(unresolved_children)} unresolved children; "
        f"{len(unresolved_references)} unresolved references; "
        f"{len(segment_rows)} operative segments"
    )


if __name__ == "__main__":
    main()
