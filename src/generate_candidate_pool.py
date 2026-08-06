"""Generate up-to-25 same-type, strictly-earlier embedding candidates."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

import numpy as np


def parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%B %d, %Y")


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def top_candidates(
    documents: list[dict],
    unresolved_ids: set[str],
    ids: list[str],
    query_embeddings: np.ndarray,
    document_embeddings: np.ndarray,
    limit: int = 25,
    operative_ids: set[str] | None = None,
) -> list[dict]:
    if ids != [str(row["document_id"]) for row in documents]:
        raise ValueError("embedding IDs do not match document artifact order")
    dates = [parse_date(row["date"]) for row in documents]
    rows: list[dict] = []
    by_type: dict[str, list[int]] = {}
    for index, document in enumerate(documents):
        if operative_ids is not None and str(document["document_id"]) not in operative_ids:
            continue
        by_type.setdefault(document["document_type"], []).append(index)

    for document_type, indices in sorted(by_type.items()):
        candidate_matrix = document_embeddings[indices].astype(np.float32)
        for child_index in indices:
            child = documents[child_index]
            child_id = str(child["document_id"])
            if child_id not in unresolved_ids:
                continue
            eligible_local = [
                local_index
                for local_index, parent_index in enumerate(indices)
                if dates[parent_index] < dates[child_index]
            ]
            if not eligible_local:
                continue
            scores = candidate_matrix[eligible_local] @ query_embeddings[child_index].astype(np.float32)
            count = min(limit, len(eligible_local))
            if count < len(eligible_local):
                selected = np.argpartition(scores, -count)[-count:]
            else:
                selected = np.arange(len(eligible_local))
            ranked = sorted(
                selected,
                key=lambda position: (
                    -float(scores[position]),
                    str(documents[indices[eligible_local[position]]]["document_id"]),
                ),
            )
            for rank, position in enumerate(ranked, 1):
                parent = documents[indices[eligible_local[position]]]
                rows.append(
                    {
                        "child_id": child_id,
                        "parent_id": str(parent["document_id"]),
                        "document_type": document_type,
                        "child_date": child["date"],
                        "parent_date": parent["date"],
                        "document_embedding_score": float(scores[position]),
                        "document_embedding_rank": rank,
                    }
                )
    rows.sort(key=lambda row: (row["document_type"], row["child_id"], row["document_embedding_rank"]))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=Path("data/parent_analysis"))
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()
    documents = load_jsonl(args.input_dir / "directive_similarity_documents.jsonl")
    operative_ids = {
        str(row["document_id"])
        for row in load_jsonl(args.input_dir / "directive_operative_segments.jsonl")
    }
    with (args.input_dir / "unresolved_children.csv").open(newline="", encoding="utf-8") as handle:
        unresolved_ids = {row["document_id"] for row in csv.DictReader(handle)}
    with np.load(args.input_dir / "embeddings/directive_document_embeddings.npz") as cache:
        rows = top_candidates(
            documents,
            unresolved_ids,
            cache["ids"].astype(str).tolist(),
            cache["query_embeddings"],
            cache["document_embeddings"],
            args.limit,
            operative_ids,
        )
    output = args.input_dir / "embedding_candidate_pool.csv"
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(unresolved_ids)} unresolved children; {len(rows)} candidate pairs; {output}")


if __name__ == "__main__":
    main()
