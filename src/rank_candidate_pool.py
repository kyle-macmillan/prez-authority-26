"""Rank embedding-gated parent candidates through segment-level channels and RRF."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from segmenter import _get_ordering_re


TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)*")


def tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text)


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
    """Assign equal dense ranks to equal scores, with higher scores first."""
    ordered = sorted(values, key=lambda item: (-values[item], item))
    ranks = {}
    rank = 0
    previous = None
    for item in ordered:
        value = values[item]
        if previous is None or value != previous:
            rank += 1
            previous = value
        ranks[item] = rank
    return ranks


def ordinal_ranks(values: dict[str, float]) -> dict[str, int]:
    """Deterministically break score ties so top-N selection has at most N rows."""
    ordered = sorted(values, key=lambda item: (-values[item], item))
    return {item: rank for rank, item in enumerate(ordered, 1)}


def top_pairs(
    similarities: np.ndarray, count: int = 3,
) -> tuple[float | None, list[tuple[int, int, float]]]:
    if not similarities.size:
        return None, []
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


def top_pair_average(
    child_vectors: np.ndarray, parent_vectors: np.ndarray, count: int = 3
) -> tuple[float | None, list[tuple[int, int, float]]]:
    if not len(child_vectors) or not len(parent_vectors):
        return None, []
    similarities = child_vectors.astype(np.float32) @ parent_vectors.astype(np.float32).T
    return top_pairs(similarities, count)


def ordering_phrases(text: str) -> set[str]:
    """Return normalized extended-W&P phrases occurring in one operative segment."""
    return {
        " ".join(match.group(0).casefold().split())
        for match in _get_ordering_re(extended=True).finditer(text)
    }


def matching_phrase_pairs(
    child_segments: list[dict], parent_segments: list[dict],
) -> list[tuple[int, int, list[str]]]:
    child_phrases = [ordering_phrases(row["text"]) for row in child_segments]
    parent_phrases = [ordering_phrases(row["text"]) for row in parent_segments]
    return [
        (child_index, parent_index, sorted(child & parent))
        for child_index, child in enumerate(child_phrases)
        for parent_index, parent in enumerate(parent_phrases)
        if child & parent
    ]


def segment_reuse_score(
    child_segments: list[dict], parent_segments: list[dict], count: int = 3,
) -> tuple[float | None, list[tuple[int, int, float]]]:
    if not child_segments or not parent_segments:
        return None, []
    child_tokens = [tokens(row["text"]) for row in child_segments]
    parent_tokens = [tokens(row["text"]) for row in parent_segments]
    return segment_reuse_score_tokens(child_tokens, parent_tokens, count=count)


def segment_reuse_score_tokens(
    child_tokens: list[list[str]], parent_tokens: list[list[str]], count: int = 3,
    parent_shingles: list[set[tuple[str, ...]]] | None = None,
) -> tuple[float | None, list[tuple[int, int, float]]]:
    if not child_tokens or not parent_tokens:
        return None, []
    parent_shingles = parent_shingles or [word_shingles(words) for words in parent_tokens]
    similarities = np.asarray([
        [reused_word_count(child, parent, parent_shingles=shingles)
         for parent, shingles in zip(parent_tokens, parent_shingles)]
        for child in child_tokens
    ], dtype=np.float32)
    return top_pairs(similarities, count)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=Path("data/parent_analysis"))
    parser.add_argument("--rrf-k", type=int, default=20)
    args = parser.parse_args()

    pools: dict[str, list[dict]] = defaultdict(list)
    with (args.input_dir / "embedding_candidate_pool.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            pools[row["child_id"]].append(row)

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
    segment_tokens = [tokens(row["text"]) for row in segment_rows]
    segment_shingles = [word_shingles(words) for words in segment_tokens]
    segment_phrases = [ordering_phrases(row["text"]) for row in segment_rows]
    vectorizer = TfidfVectorizer(
        lowercase=False, token_pattern=TOKEN_RE.pattern, ngram_range=(3, 3)
    )
    trigram_matrix = vectorizer.fit_transform(row["text"] for row in segment_rows)

    output_rows = []
    for child_number, (child_id, candidates) in enumerate(sorted(pools.items()), 1):
        candidates.sort(key=lambda row: int(row["document_embedding_rank"]))
        parent_ids = [row["parent_id"] for row in candidates]
        operative: dict[str, float] = {}
        ngram: dict[str, float] = {}
        reuse: dict[str, float] = {}
        same_phrase: dict[str, float] = {}
        alignments: dict[str, list[tuple[int, int, float]]] = {}
        ngram_alignments: dict[str, list[tuple[int, int, float]]] = {}
        reuse_alignments: dict[str, list[tuple[int, int, float]]] = {}
        phrase_alignments: dict[str, list[tuple[int, int, list[str]]]] = {}
        child_segment_indices = segments_by_document.get(child_id, [])
        parent_indices = {
            parent_id: segments_by_document.get(parent_id, []) for parent_id in parent_ids
        }
        all_parent_indices = [
            index for parent_id in parent_ids for index in parent_indices[parent_id]
        ]
        parent_slices = {}
        offset = 0
        for parent_id in parent_ids:
            width = len(parent_indices[parent_id])
            parent_slices[parent_id] = slice(offset, offset + width)
            offset += width
        if child_segment_indices and all_parent_indices:
            operative_matrix = (
                query_segments[child_segment_indices]
                @ parent_segments[all_parent_indices].T
            )
            trigram_pair_matrix = trigram_matrix[child_segment_indices].dot(
                trigram_matrix[all_parent_indices].T
            ).toarray()
        else:
            operative_matrix = np.empty((0, 0), dtype=np.float32)
            trigram_pair_matrix = np.empty((0, 0), dtype=np.float32)
        for parent_id in parent_ids:
            parent_segment_indices = parent_indices[parent_id]
            parent_slice = parent_slices[parent_id]
            score, pairs = top_pairs(operative_matrix[:, parent_slice])
            if score is not None:
                operative[parent_id] = score
            alignments[parent_id] = pairs
            if child_segment_indices and parent_segment_indices:
                trigram_score, trigram_pairs = top_pairs(
                    trigram_pair_matrix[:, parent_slice]
                )
                reuse_score, reuse_pairs = segment_reuse_score_tokens(
                    [segment_tokens[index] for index in child_segment_indices],
                    [segment_tokens[index] for index in parent_segment_indices],
                    parent_shingles=[segment_shingles[index] for index in parent_segment_indices],
                )
                phrase_pairs = [
                    (child_local, parent_local, sorted(child_phrases & parent_phrases))
                    for child_local, child_index in enumerate(child_segment_indices)
                    for parent_local, parent_index in enumerate(parent_segment_indices)
                    if (child_phrases := segment_phrases[child_index])
                    and (parent_phrases := segment_phrases[parent_index])
                    and child_phrases & parent_phrases
                ]
                ngram[parent_id] = float(trigram_score)
                reuse[parent_id] = float(reuse_score)
                same_phrase[parent_id] = float(bool(phrase_pairs))
                ngram_alignments[parent_id] = trigram_pairs
                reuse_alignments[parent_id] = reuse_pairs
                phrase_alignments[parent_id] = phrase_pairs
            else:
                ngram_alignments[parent_id] = []
                reuse_alignments[parent_id] = []
                phrase_alignments[parent_id] = []

        scores_by_channel = {
            "operative": operative,
            "same_phrase": same_phrase,
            "ngram": ngram,
            "text_reuse": reuse,
        }
        ranks = {name: dense_ranks(values) for name, values in scores_by_channel.items()}
        rrf = {
            parent_id: sum(
                1.0 / (args.rrf_k + channel_ranks[parent_id])
                for channel_ranks in ranks.values()
                if parent_id in channel_ranks
            )
            for parent_id in parent_ids
        }
        rrf_ranks = ordinal_ranks(rrf)
        for candidate in candidates:
            parent_id = candidate["parent_id"]
            pairs = alignments[parent_id]
            output_rows.append(
                {
                    **candidate,
                    "operative_embedding_score": operative.get(parent_id, ""),
                    "operative_embedding_rank": ranks["operative"].get(parent_id, ""),
                    "operative_alignments": json.dumps(pairs),
                    "same_ordering_phrase": (
                        bool(same_phrase[parent_id]) if parent_id in same_phrase else ""
                    ),
                    "same_ordering_phrase_rank": ranks["same_phrase"].get(parent_id, ""),
                    "same_ordering_phrase_alignments": json.dumps(phrase_alignments[parent_id]),
                    "segment_word_trigram_tfidf_score": ngram.get(parent_id, ""),
                    "segment_word_trigram_rank": ranks["ngram"].get(parent_id, ""),
                    "segment_word_trigram_alignments": json.dumps(ngram_alignments[parent_id]),
                    "segment_text_reuse_words": reuse.get(parent_id, ""),
                    "segment_text_reuse_rank": ranks["text_reuse"].get(parent_id, ""),
                    "segment_text_reuse_alignments": json.dumps(reuse_alignments[parent_id]),
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
