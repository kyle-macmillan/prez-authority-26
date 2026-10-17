#!/usr/bin/env python3
"""Build blinded 25-candidate Sol requests for unevaluated eligible directives."""

from __future__ import annotations

import argparse
from bisect import bisect_left
import csv
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer

import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ceremonial import ceremonial_reason  # noqa: E402
from parent_analysis import load_directive_corpus  # noqa: E402
from precedent_preprocess import (  # noqa: E402
    AUTHORITY_PATTERNS,
    remove_similarity_boilerplate,
    remove_vesting_clauses,
)


HERE = Path(__file__).resolve().parent
DEFAULT_OUTPUT = HERE / "outputs/sol_parent_remaining"
DEFAULT_EVALUATED = HERE / "outputs"
DIRECT_RELATIONS = {
    "amends", "modifies", "continues", "replaces", "revokes", "supersedes",
}
TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)*")
DIRECTIVE_REFERENCE_KINDS = {
    "executive_order", "proclamation", "numbered_memorandum",
    "dated_unnumbered_directive", "titled_unnumbered_directive",
}
SALT = "sol-parent-remaining-v1"


def parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%B %d, %Y")


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def mask_directive_references(text: str) -> str:
    spans = []
    for kind, pattern in AUTHORITY_PATTERNS:
        if kind in DIRECTIVE_REFERENCE_KINDS:
            spans.extend((match.start(), match.end()) for match in pattern.finditer(text))
    spans.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    selected = []
    for start, end in spans:
        if selected and start < selected[-1][1]:
            selected[-1] = (selected[-1][0], max(selected[-1][1], end))
        else:
            selected.append((start, end))
    pieces = []
    cursor = 0
    for start, end in selected:
        pieces.extend((text[cursor:start], "[DIRECTIVE_REFERENCE]"))
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)


def prepare_text(text: str) -> str:
    without_vesting, _ = remove_vesting_clauses(text)
    without_boilerplate, _ = remove_similarity_boilerplate(without_vesting)
    return mask_directive_references(without_boilerplate)


def evaluated_document_ids(outputs_dir: Path) -> set[str]:
    evaluated = set()
    for sample_path in outputs_dir.glob("*/sampled_children.csv"):
        response_dir = sample_path.parent / "responses"
        if not response_dir.is_dir():
            continue
        with sample_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                case_id = row.get("case_id", "")
                if case_id and (response_dir / f"{case_id}.json").is_file():
                    evaluated.add(str(row["document_id"]))
    return evaluated


def tokens(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN_RE.findall(text)]


def shingles(items: list[str], size: int) -> set[tuple[str, ...]]:
    return {tuple(items[index:index + size]) for index in range(len(items) - size + 1)}


def reuse_score(child: set[tuple[str, ...]], parent: set[tuple[str, ...]]) -> float:
    return len(child & parent) / len(child) if child else 0.0


def ranked(scores: dict[int, float], limit: int = 100) -> list[int]:
    return sorted(scores, key=lambda index: (-scores[index], index))[:limit]


def sparse_scores(matrix: sparse.csr_matrix, child: int, eligible: list[int]) -> dict[int, float]:
    if not eligible:
        return {}
    values = matrix[eligible].dot(matrix[child].T).tocoo()
    return {
        eligible[row]: float(value)
        for row, value in zip(values.row, values.data, strict=True)
        if value > 0
    }


def candidate_pool(
    child_index: int,
    eligible: list[int],
    documents: list[dict],
    full_matrix: sparse.csr_matrix,
    operative_matrix: sparse.csr_matrix,
    tokenized: list[list[str]],
    shingle_cache: dict[tuple[int, int], set[tuple[str, ...]]],
    dates: list[datetime],
) -> tuple[list[int], dict[str, dict[int, float]], dict[str, dict[int, int]]]:
    full_scores = sparse_scores(full_matrix, child_index, eligible)
    operative_scores = sparse_scores(operative_matrix, child_index, eligible)
    shortlist = set(ranked(full_scores, 100)) | set(ranked(operative_scores, 100))
    # Documents and eligible indices are chronological, so no per-child date sort is needed.
    recent = list(reversed(eligible[-100:]))
    shortlist.update(recent)

    child_shingles = {}
    reuse_scores = {5: {}, 10: {}}
    for size in (5, 10):
        child_shingles[size] = shingles(tokenized[child_index], size)
        for parent_index in shortlist:
            key = (parent_index, size)
            if key not in shingle_cache:
                shingle_cache[key] = shingles(tokenized[parent_index], size)
            score = reuse_score(child_shingles[size], shingle_cache[key])
            if score:
                reuse_scores[size][parent_index] = score

    recency_scores = {
        index: 1.0 / (rank + 1)
        for rank, index in enumerate(recent)
    }
    scores = {
        "word5": reuse_scores[5],
        "word10": reuse_scores[10],
        "bm25": full_scores,
        "operative": operative_scores,
        "recency": recency_scores,
    }
    ranks = {
        channel: {index: rank for rank, index in enumerate(ranked(values), 1)}
        for channel, values in scores.items()
    }
    selected = set()
    for channel in ("word5", "word10", "bm25", "operative"):
        selected.update(ranked(scores[channel], 5))
    selected.update(recent[:2])
    rrf = {
        index: sum(1.0 / (60 + channel_ranks[index]) for channel_ranks in ranks.values() if index in channel_ranks)
        for index in shortlist
    }
    for index in ranked(rrf, 25):
        selected.add(index)
        if len(selected) >= 25:
            break
    for index in recent:
        selected.add(index)
        if len(selected) >= 25:
            break
    chosen = sorted(selected, key=lambda index: (-rrf.get(index, 0.0), index))[:25]
    return chosen, scores, ranks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, help="Build only the first N missing children")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    requests_dir = args.output_dir / "requests"
    requests_dir.mkdir(exist_ok=True)

    source_documents = load_directive_corpus([
        ROOT / "data/4_28_2026_build_dev.csv",
        ROOT / "data/4_28_2026_build_holdout.csv",
    ])
    documents = []
    for document in source_documents:
        if ceremonial_reason({
            "doc_type": document.document_type,
            "doc_text": document.text,
            "title": document.title,
            "url": document.url,
        }):
            continue
        documents.append({
            "document_id": document.document_id,
            "document_type": document.document_type,
            "title": document.title,
            "date": document.date_text,
            "president": "",
            "non_vesting_text": prepare_text(document.text),
        })
    raw_presidents = {}
    for path in (ROOT / "data/4_28_2026_build_dev.csv", ROOT / "data/4_28_2026_build_holdout.csv"):
        with path.open(newline="", encoding="utf-8") as handle:
            raw_presidents.update({row[""]: row["president"] for row in csv.DictReader(handle)})
    for document in documents:
        document["president"] = raw_presidents[document["document_id"]]

    document_ids = {row["document_id"] for row in documents}
    explicit_children = set()
    with (ROOT / "data/parent_analysis_full/automatic_edges.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if (
                row["relation"] in DIRECT_RELATIONS
                and row["child_id"] in document_ids
                and row["parent_id"] in document_ids
            ):
                explicit_children.add(row["child_id"])
    evaluated = evaluated_document_ids(DEFAULT_EVALUATED)
    remaining_ids = document_ids - explicit_children - evaluated

    documents.sort(key=lambda row: (parse_date(row["date"]), int(row["document_id"])))
    dates = [parse_date(row["date"]) for row in documents]
    index_by_id = {row["document_id"]: index for index, row in enumerate(documents)}
    targets = sorted((index_by_id[document_id] for document_id in remaining_ids))
    if args.limit is not None:
        targets = targets[:args.limit]

    texts = [row["non_vesting_text"] for row in documents]
    operative_by_document = defaultdict(list)
    with (ROOT / "data/parent_analysis_full/directive_operative_segments.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if str(row["document_id"]) in document_ids:
                operative_by_document[str(row["document_id"])].append(row["text"])
    operative_texts = [" ".join(operative_by_document[row["document_id"]]) for row in documents]
    vectorizer_options = dict(
        lowercase=True, token_pattern=TOKEN_RE.pattern, ngram_range=(1, 2),
        sublinear_tf=True, min_df=2, max_df=0.98, max_features=200_000,
    )
    full_matrix = TfidfVectorizer(**vectorizer_options).fit_transform(texts).tocsr()
    operative_matrix = TfidfVectorizer(**vectorizer_options).fit_transform(operative_texts).tocsr()
    tokenized = [tokens(text) for text in texts]
    shingle_cache = {}

    sample_rows = []
    key_rows = []
    skipped_too_early = []
    for number, child_index in enumerate(targets, 1):
        child = documents[child_index]
        child_date = dates[child_index]
        eligible = list(range(bisect_left(dates, child_date)))
        if len(eligible) < 3:
            skipped_too_early.append(child["document_id"])
            continue
        parents, scores, ranks = candidate_pool(
            child_index, eligible, documents, full_matrix, operative_matrix,
            tokenized, shingle_cache, dates,
        )
        if len(shingle_cache) > 5_000:
            shingle_cache.clear()
        case_id = f"SPR{number:05d}"
        labels = [f"C{label:02d}" for label in range(1, len(parents) + 1)]
        order = sorted(
            range(len(parents)),
            key=lambda offset: hashlib.sha256(
                f"{SALT}|{child['document_id']}|{documents[parents[offset]]['document_id']}".encode()
            ).hexdigest(),
        )
        request_candidates = []
        for display_offset, parent_offset in enumerate(order):
            parent_index = parents[parent_offset]
            parent = documents[parent_index]
            label = labels[display_offset]
            request_candidates.append({
                "candidate_label": label,
                "title": parent["title"],
                "date": parent["date"],
                "document_type": parent["document_type"],
                "non_vesting_text": parent["non_vesting_text"],
            })
            rrf_score = sum(
                1.0 / (60 + channel_ranks[parent_index])
                for channel_ranks in ranks.values() if parent_index in channel_ranks
            )
            key_rows.append({
                "case_id": case_id,
                "child_id": child["document_id"],
                "candidate_label": label,
                "parent_id": parent["document_id"],
                "retrieval_sources": "|".join(
                    channel for channel in scores if parent_index in ranks[channel] and ranks[channel][parent_index] <= 5
                ) or "rrf_fill",
                **{f"{channel}_score": scores[channel].get(parent_index, "") for channel in scores},
                **{f"{channel}_rank": ranks[channel].get(parent_index, "") for channel in ranks},
                "rrf_score": rrf_score,
            })
        request = {
            "case_id": case_id,
            "child": {
                "title": child["title"], "date": child["date"],
                "document_type": child["document_type"],
                "non_vesting_text": child["non_vesting_text"],
            },
            "candidates": request_candidates,
        }
        (requests_dir / f"{case_id}.json").write_text(
            json.dumps(request, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        sample_rows.append({
            "case_id": case_id, "document_id": child["document_id"],
            "document_type": child["document_type"], "president": child["president"],
            "date": child["date"], "title": child["title"],
            "candidate_count": len(request_candidates),
        })
        if number % 100 == 0:
            print(json.dumps({"built": number, "selected": len(targets)}), flush=True)

    sample_fields = ["case_id", "document_id", "document_type", "president", "date", "title", "candidate_count"]
    key_fields = [
        "case_id", "child_id", "candidate_label", "parent_id", "retrieval_sources",
        *[f"{channel}_{suffix}" for channel in ("word5", "word10", "bm25", "operative", "recency") for suffix in ("score", "rank")],
        "rrf_score",
    ]
    write_csv(args.output_dir / "sampled_children.csv", sample_rows, sample_fields)
    write_csv(args.output_dir / "candidate_pool_key.csv", key_rows, key_fields)
    manifest = {
        "schema_version": 1,
        "kind": "remaining_nonceremonial_no_explicit_link_sol_parent_identification",
        "candidate_pool_size": 25,
        "nonceremonial_directives": len(document_ids),
        "explicit_direct_transition_children": len(explicit_children),
        "previously_evaluated_children": len(evaluated & (document_ids - explicit_children)),
        "remaining_children": len(remaining_ids),
        "requests_built": len(sample_rows),
        "skipped_with_fewer_than_three_earlier_candidates": skipped_too_early,
        "candidate_channels": ["word5", "word10", "bm25_tfidf_proxy", "operative_tfidf", "recency"],
        "candidate_method_note": "Function-profile embeddings used by the frozen 100-case package were not preserved; operative-text TF-IDF is used for full-corpus coverage.",
        "model": "gpt-5.6-sol",
        "reasoning_effort": "low",
        "text": "vesting clauses and generic boilerplate removed; directive-number references masked",
    }
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
