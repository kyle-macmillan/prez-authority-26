"""Rank embedding-gated parent candidates through four channels and RRF."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer


TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)*")


def tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text)


def bm25_scores(
    query: list[str],
    candidates: list[list[str]],
    k1: float = 1.5,
    b: float = 0.75,
    frequencies: list[Counter] | None = None,
) -> list[float]:
    count = len(candidates)
    lengths = [len(document) for document in candidates]
    average_length = sum(lengths) / count if count else 0.0
    frequencies = frequencies or [Counter(document) for document in candidates]
    document_frequency = Counter(
        term for document in candidates for term in set(document)
    )
    query_frequency = Counter(query)
    scores = []
    for frequency, length in zip(frequencies, lengths):
        score = 0.0
        for term, query_count in query_frequency.items():
            df = document_frequency.get(term, 0)
            if not df:
                continue
            inverse_frequency = math.log(1.0 + (count - df + 0.5) / (df + 0.5))
            tf = frequency.get(term, 0)
            denominator = tf + k1 * (1.0 - b + b * length / average_length) if average_length else 1.0
            score += query_count * inverse_frequency * tf * (k1 + 1.0) / denominator
        scores.append(score)
    return scores


def word_shingles(words: list[str], size: int = 10) -> set[tuple[str, ...]]:
    return {tuple(words[index : index + size]) for index in range(len(words) - size + 1)}


def reused_word_count(
    child: list[str],
    parent: list[str],
    minimum: int = 10,
    parent_shingles: set[tuple[str, ...]] | None = None,
) -> int:
    parent_shingles = parent_shingles if parent_shingles is not None else word_shingles(parent, minimum)
    intervals = [
        (index, index + minimum)
        for index in range(len(child) - minimum + 1)
        if tuple(child[index : index + minimum]) in parent_shingles
    ]
    if not intervals:
        return 0
    total = 0
    start, end = intervals[0]
    for next_start, next_end in intervals[1:]:
        if next_start <= end:
            end = max(end, next_end)
        else:
            total += end - start
            start, end = next_start, next_end
    return total + end - start


def dense_ranks(values: dict[str, float]) -> dict[str, int]:
    ordered = sorted(values, key=lambda item: (-values[item], item))
    return {item: rank for rank, item in enumerate(ordered, 1)}


def top_pair_average(
    child_vectors: np.ndarray, parent_vectors: np.ndarray, count: int = 3
) -> tuple[float | None, list[tuple[int, int, float]]]:
    if not len(child_vectors) or not len(parent_vectors):
        return None, []
    similarities = child_vectors.astype(np.float32) @ parent_vectors.astype(np.float32).T
    flat = similarities.ravel()
    take = min(count, len(flat))
    selected = np.argpartition(flat, -take)[-take:]
    pairs = sorted(
        [
            (
                int(position // similarities.shape[1]),
                int(position % similarities.shape[1]),
                float(flat[position]),
            )
            for position in selected
        ],
        key=lambda item: (-item[2], item[0], item[1]),
    )
    return float(np.mean([item[2] for item in pairs])), pairs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=Path("data/parent_analysis"))
    parser.add_argument("--rrf-k", type=int, default=20)
    args = parser.parse_args()

    documents = [
        json.loads(line)
        for line in (args.input_dir / "directive_similarity_documents.jsonl").open(encoding="utf-8")
    ]
    by_id = {str(row["document_id"]): row for row in documents}
    document_tokens = {key: tokens(row["cleaned_masked_text"]) for key, row in by_id.items()}
    document_frequencies = {key: Counter(words) for key, words in document_tokens.items()}
    document_reuse_shingles = {
        key: word_shingles(words) for key, words in document_tokens.items()
    }
    pools: dict[str, list[dict]] = defaultdict(list)
    with (args.input_dir / "embedding_candidate_pool.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            pools[row["child_id"]].append(row)

    vectorizer = TfidfVectorizer(lowercase=False, token_pattern=TOKEN_RE.pattern, ngram_range=(3, 3))
    trigram_matrix = vectorizer.fit_transform(row["cleaned_masked_text"] for row in documents)
    document_position = {str(row["document_id"]): index for index, row in enumerate(documents)}

    segment_rows = [
        json.loads(line)
        for line in (args.input_dir / "directive_operative_segments.jsonl").open(encoding="utf-8")
    ]
    with np.load(args.input_dir / "embeddings/directive_operative_segment_embeddings.npz") as cache:
        segment_ids = cache["ids"].astype(str).tolist()
        if segment_ids != [row["segment_id"] for row in segment_rows]:
            raise ValueError("segment embedding IDs do not match segment artifact order")
        query_segments = cache["query_embeddings"].astype(np.float32)
        parent_segments = cache["document_embeddings"].astype(np.float32)
    segments_by_document: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(segment_rows):
        segments_by_document[str(row["document_id"])].append(index)

    output_rows = []
    for child_number, (child_id, candidates) in enumerate(sorted(pools.items()), 1):
        candidates.sort(key=lambda row: int(row["document_embedding_rank"]))
        parent_ids = [row["parent_id"] for row in candidates]
        bm25 = dict(
            zip(
                parent_ids,
                bm25_scores(
                    document_tokens[child_id],
                    [document_tokens[x] for x in parent_ids],
                    frequencies=[document_frequencies[x] for x in parent_ids],
                ),
            )
        )
        child_vector = trigram_matrix[document_position[child_id]]
        parent_positions = [document_position[parent_id] for parent_id in parent_ids]
        ngram_values = trigram_matrix[parent_positions].dot(child_vector.T).toarray().ravel()
        ngram = dict(zip(parent_ids, map(float, ngram_values)))
        reuse = {
            parent_id: float(
                reused_word_count(
                    document_tokens[child_id],
                    document_tokens[parent_id],
                    parent_shingles=document_reuse_shingles[parent_id],
                )
            )
            for parent_id in parent_ids
        }
        operative: dict[str, float] = {}
        alignments: dict[str, list[tuple[int, int, float]]] = {}
        child_segment_indices = segments_by_document.get(child_id, [])
        for parent_id in parent_ids:
            parent_segment_indices = segments_by_document.get(parent_id, [])
            score, pairs = top_pair_average(
                query_segments[child_segment_indices],
                parent_segments[parent_segment_indices],
            )
            if score is not None:
                operative[parent_id] = score
            alignments[parent_id] = pairs

        scores_by_channel = {"operative": operative, "bm25": bm25, "ngram": ngram, "text_reuse": reuse}
        ranks = {name: dense_ranks(values) for name, values in scores_by_channel.items()}
        rrf = {
            parent_id: sum(
                1.0 / (args.rrf_k + channel_ranks[parent_id])
                for channel_ranks in ranks.values()
                if parent_id in channel_ranks
            )
            for parent_id in parent_ids
        }
        rrf_ranks = dense_ranks(rrf)
        for candidate in candidates:
            parent_id = candidate["parent_id"]
            pairs = alignments[parent_id]
            output_rows.append(
                {
                    **candidate,
                    "operative_embedding_score": operative.get(parent_id, ""),
                    "operative_embedding_rank": ranks["operative"].get(parent_id, ""),
                    "operative_alignments": json.dumps(pairs),
                    "bm25_score": bm25[parent_id],
                    "bm25_rank": ranks["bm25"][parent_id],
                    "word_trigram_tfidf_score": ngram[parent_id],
                    "word_trigram_rank": ranks["ngram"][parent_id],
                    "text_reuse_words": int(reuse[parent_id]),
                    "text_reuse_rank": ranks["text_reuse"][parent_id],
                    "rrf_k": args.rrf_k,
                    "rrf_score": rrf[parent_id],
                    "rrf_rank": rrf_ranks[parent_id],
                    "selected_top_10": rrf_ranks[parent_id] <= 10,
                }
            )
        if child_number % 250 == 0:
            print(f"ranked {child_number}/{len(pools)} children", flush=True)

    output_rows.sort(key=lambda row: (row["document_type"], row["child_id"], row["rrf_rank"]))
    output = args.input_dir / "ranked_candidates.csv"
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)
    print(f"{len(pools)} children; {len(output_rows)} ranked pairs; {output}")


if __name__ == "__main__":
    main()
