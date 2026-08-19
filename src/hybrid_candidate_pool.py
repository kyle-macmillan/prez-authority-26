#!/usr/bin/env python3
"""Build a cross-type parent pool by taking the union of retrieval channels."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer


TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)*")
CHANNELS = ("cleaned_embedding", "synthesis_embedding", "lexical_tfidf", "text_reuse")


def parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%B %d, %Y")


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_vectors(path: Path) -> tuple[list[str], np.ndarray, np.ndarray]:
    with np.load(path) as cache:
        return (
            cache["ids"].astype(str).tolist(),
            cache["query_embeddings"].astype(np.float32),
            cache["document_embeddings"].astype(np.float32),
        )


def words(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN_RE.findall(text)]


def shingles(text: str, size: int = 10) -> set[tuple[str, ...]]:
    items = words(text)
    return {tuple(items[index:index + size]) for index in range(len(items) - size + 1)}


def distinctive_reuse_scores(
    texts: list[str], eligible_indices: set[int], child_index: int,
    inverted: dict[tuple[str, ...], list[int]], max_document_frequency: int = 25,
) -> dict[int, float]:
    scores: dict[int, float] = defaultdict(float)
    for shingle in shingles(texts[child_index]):
        postings = inverted.get(shingle, [])
        if len(postings) > max_document_frequency:
            continue
        for parent_index in postings:
            if parent_index in eligible_indices:
                scores[parent_index] += 1.0
    return dict(scores)


def top_ranked(scores: dict[int, float], documents: list[dict], limit: int) -> list[int]:
    return sorted(
        scores,
        key=lambda index: (-scores[index], str(documents[index]["document_id"])),
    )[:limit]


def build_hybrid_pool(
    documents: list[dict], target_ids: set[str],
    cleaned_ids: list[str], cleaned_queries: np.ndarray, cleaned_documents: np.ndarray,
    synthesis_vectors: tuple[list[str], np.ndarray, np.ndarray] | None = None,
    operative_ids: set[str] | None = None, top_per_channel: int = 4,
    maximum_candidates: int = 20,
) -> list[dict]:
    document_ids = [str(row["document_id"]) for row in documents]
    if cleaned_ids != document_ids:
        raise ValueError("cleaned embedding IDs do not match document artifact order")
    index_by_id = {document_id: index for index, document_id in enumerate(document_ids)}
    dates = [parse_date(row["date"]) for row in documents]
    texts = [row["cleaned_masked_text"] for row in documents]
    allowed_parents = {
        index for index, document_id in enumerate(document_ids)
        if operative_ids is None or document_id in operative_ids
    }

    vectorizer = TfidfVectorizer(
        lowercase=True, token_pattern=TOKEN_RE.pattern, ngram_range=(1, 2),
        sublinear_tf=True, max_df=0.98,
    )
    lexical = vectorizer.fit_transform(texts)
    inverted: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for index, text in enumerate(texts):
        for shingle in shingles(text):
            inverted[shingle].append(index)

    synthesis = None
    if synthesis_vectors:
        synthesis_ids, synthesis_queries, synthesis_documents = synthesis_vectors
        synthesis = (
            {document_id: index for index, document_id in enumerate(synthesis_ids)},
            synthesis_queries,
            synthesis_documents,
        )

    output = []
    for child_id in sorted(target_ids, key=lambda value: index_by_id.get(value, 10**12)):
        if child_id not in index_by_id:
            raise ValueError(f"unknown target child: {child_id}")
        child_index = index_by_id[child_id]
        if operative_ids is not None and child_id not in operative_ids:
            continue
        eligible = {
            index for index in allowed_parents if dates[index] < dates[child_index]
        }
        if not eligible:
            continue
        eligible_list = sorted(eligible)
        cleaned_values = cleaned_documents[eligible_list] @ cleaned_queries[child_index]
        channel_scores: dict[str, dict[int, float]] = {
            "cleaned_embedding": dict(zip(eligible_list, map(float, cleaned_values), strict=True)),
            "lexical_tfidf": {
                index: float(score) for index, score in zip(
                    eligible_list,
                    lexical[eligible_list].dot(lexical[child_index].T).toarray().ravel(),
                    strict=True,
                )
            },
            "text_reuse": distinctive_reuse_scores(
                texts, eligible, child_index, inverted
            ),
        }
        if synthesis and child_id in synthesis[0]:
            synthesis_index, synthesis_queries, synthesis_documents = synthesis
            available = [index for index in eligible_list if document_ids[index] in synthesis_index]
            channel_scores["synthesis_embedding"] = {
                index: float(
                    synthesis_documents[synthesis_index[document_ids[index]]]
                    @ synthesis_queries[synthesis_index[child_id]]
                )
                for index in available
            }
        else:
            channel_scores["synthesis_embedding"] = {}

        channel_ranks: dict[str, dict[int, int]] = {}
        union: set[int] = set()
        for channel in CHANNELS:
            ranked = top_ranked(channel_scores[channel], documents, top_per_channel)
            channel_ranks[channel] = {index: rank for rank, index in enumerate(ranked, 1)}
            union.update(ranked)
        # The nominal 4x4 union is at most 16; this guard makes the contract explicit
        # if channel counts change in a later experiment.
        union = set(sorted(
            union,
            key=lambda index: (
                min((channel_ranks[c].get(index, 10**6) for c in CHANNELS)),
                str(documents[index]["document_id"]),
            ),
        )[:maximum_candidates])
        for parent_index in sorted(union, key=lambda index: str(documents[index]["document_id"])):
            parent = documents[parent_index]
            row = {
                "child_id": child_id,
                "parent_id": str(parent["document_id"]),
                "document_type": documents[child_index]["document_type"],
                "child_document_type": documents[child_index]["document_type"],
                "parent_document_type": parent["document_type"],
                "child_date": documents[child_index]["date"],
                "parent_date": parent["date"],
                "retrieval_channels": ",".join(
                    channel for channel in CHANNELS if parent_index in channel_ranks[channel]
                ),
            }
            for channel in CHANNELS:
                row[f"{channel}_score"] = channel_scores[channel].get(parent_index, "")
                row[f"{channel}_rank"] = channel_ranks[channel].get(parent_index, "")
            # Compatibility aliases for the established segment-level ranker/viewer.
            row["document_embedding_score"] = row["cleaned_embedding_score"]
            row["document_embedding_rank"] = row["cleaned_embedding_rank"]
            output.append(row)
    output.sort(key=lambda row: (row["child_id"], row["parent_id"]))
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=Path("data/parent_analysis"))
    parser.add_argument("--children", type=Path, help="CSV with document_id; defaults to target children")
    parser.add_argument("--top-per-channel", type=int, default=4)
    parser.add_argument("--maximum-candidates", type=int, default=20)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    documents = read_jsonl(args.input_dir / "directive_similarity_documents.jsonl")
    default_targets = args.input_dir / "similarity_target_children.csv"
    if not default_targets.is_file():
        default_targets = args.input_dir / "unresolved_children.csv"
    child_path = args.children or default_targets
    with child_path.open(newline="", encoding="utf-8") as handle:
        target_ids = {
            str(row.get("document_id", row.get("child_id"))) for row in csv.DictReader(handle)
        }
    operative_ids = {
        str(row["document_id"])
        for row in read_jsonl(args.input_dir / "directive_operative_segments.jsonl")
    }
    cleaned = load_vectors(args.input_dir / "embeddings/directive_document_embeddings.npz")
    synthesis_path = args.input_dir / "embeddings/directive_synthesis_embeddings.npz"
    synthesis = load_vectors(synthesis_path) if synthesis_path.is_file() else None
    rows = build_hybrid_pool(
        documents, target_ids, *cleaned, synthesis_vectors=synthesis,
        operative_ids=operative_ids, top_per_channel=args.top_per_channel,
        maximum_candidates=args.maximum_candidates,
    )
    output = args.output or args.input_dir / "hybrid_candidate_pool.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "child_id", "parent_id", "document_type", "child_document_type", "parent_document_type",
        "child_date", "parent_date", "retrieval_channels",
        *[field for channel in CHANNELS for field in (f"{channel}_score", f"{channel}_rank")],
        "document_embedding_score", "document_embedding_rank",
    ]
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    print(f"{len(target_ids)} target children; {len(rows)} hybrid candidates; {output}")


if __name__ == "__main__":
    main()
