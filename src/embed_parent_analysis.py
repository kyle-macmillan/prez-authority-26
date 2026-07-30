"""Generate dual-role Qwen embeddings for executive-order parent retrieval."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"
MODEL_REVISION = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
EMBEDDING_DIMENSION = 1024
FULL_DOCUMENT_INSTRUCTION = (
    "Represent this executive order for identifying earlier executive orders that "
    "address the same substantive policy problem and contain a similar legal directive "
    "or directed operative action."
)
OPERATIVE_SEGMENT_INSTRUCTION = (
    "Represent this directed operative action for identifying earlier executive-order "
    "actions that use a similar legal or administrative mechanism."
)


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def instructed_query(instruction: str, text: str) -> str:
    return f"Instruct: {instruction}\nQuery:{text}"


def token_length_audit(
    tokenizer, texts: list[str], instruction: str, maximum: int
) -> dict[str, int | float]:
    document_lengths = []
    query_lengths = []
    for text in texts:
        document_lengths.append(len(tokenizer.encode(text, add_special_tokens=True)))
        query_lengths.append(
            len(
                tokenizer.encode(
                    instructed_query(instruction, text), add_special_tokens=True
                )
            )
        )
    if max(document_lengths + query_lengths) > maximum:
        raise ValueError(
            f"input exceeds model limit {maximum}: "
            f"document max={max(document_lengths)}, query max={max(query_lengths)}"
        )
    return {
        "count": len(texts),
        "document_max": max(document_lengths),
        "query_max": max(query_lengths),
        "document_mean": float(np.mean(document_lengths)),
        "query_mean": float(np.mean(query_lengths)),
    }


def validate_embeddings(name: str, embeddings: np.ndarray, count: int) -> None:
    expected = (count, EMBEDDING_DIMENSION)
    if embeddings.shape != expected:
        raise ValueError(f"{name} shape is {embeddings.shape}, expected {expected}")
    if not np.isfinite(embeddings).all():
        raise ValueError(f"{name} contains non-finite values")
    norms = np.linalg.norm(embeddings, axis=1)
    if not np.allclose(norms, 1.0, atol=1e-3):
        raise ValueError(f"{name} embeddings are not unit normalized")


def write_npz_atomic(
    path: Path,
    ids: list[str],
    query_embeddings: np.ndarray,
    document_embeddings: np.ndarray,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=f".{path.name}.", suffix=".npz", delete=False
    ) as handle:
        temporary = Path(handle.name)
    try:
        np.savez(
            temporary,
            ids=np.asarray(ids),
            query_embeddings=query_embeddings,
            document_embeddings=document_embeddings,
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def encode_artifact(
    model,
    source_path: Path,
    output_path: Path,
    id_field: str,
    text_field: str,
    instruction: str,
    batch_size: int,
) -> dict:
    rows = read_jsonl(source_path)
    ids = [str(row[id_field]) for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{source_path} contains duplicate {id_field} values")
    texts = [row[text_field] for row in rows]
    audit = token_length_audit(
        model.tokenizer, texts, instruction, model.max_seq_length
    )

    started = time.perf_counter()
    document_embeddings = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=True,
    )
    document_seconds = time.perf_counter() - started

    started = time.perf_counter()
    query_embeddings = model.encode(
        texts,
        prompt=f"Instruct: {instruction}\nQuery:",
        batch_size=batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=True,
    )
    query_seconds = time.perf_counter() - started

    validate_embeddings("document", document_embeddings, len(rows))
    validate_embeddings("query", query_embeddings, len(rows))
    write_npz_atomic(
        output_path, ids, query_embeddings, document_embeddings
    )
    return {
        "source": str(source_path),
        "source_sha256": sha256_file(source_path),
        "output": str(output_path),
        "output_sha256": sha256_file(output_path),
        "id_field": id_field,
        "text_field": text_field,
        "instruction": instruction,
        "roles": {
            "query_embeddings": "instructed child queries",
            "document_embeddings": "unprompted candidate-parent documents",
        },
        "shape": list(query_embeddings.shape),
        "dtype": str(query_embeddings.dtype),
        "token_lengths": audit,
        "batch_size": batch_size,
        "document_seconds": document_seconds,
        "query_seconds": query_seconds,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-dir", type=Path, default=Path("data/parent_analysis")
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/parent_analysis/embeddings")
    )
    parser.add_argument(
        "--model-path",
        type=Path,
        default=Path(
            ".cache/huggingface/hub/"
            f"models--Qwen--Qwen3-Embedding-0.6B/snapshots/{MODEL_REVISION}"
        ),
    )
    parser.add_argument("--document-batch-size", type=int, default=2)
    parser.add_argument("--segment-batch-size", type=int, default=8)
    parser.add_argument(
        "--artifact",
        choices=("all", "documents", "segments"),
        default="all",
        help="Generate both caches or only one cache.",
    )
    args = parser.parse_args()

    if not args.model_path.is_dir():
        raise FileNotFoundError(f"pinned model snapshot not found: {args.model_path}")

    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    import torch
    from sentence_transformers import SentenceTransformer

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required to generate the embedding artifacts")

    started = time.perf_counter()
    model = SentenceTransformer(
        str(args.model_path),
        device="cuda",
        model_kwargs={"torch_dtype": torch.float16},
        tokenizer_kwargs={"padding_side": "left"},
        local_files_only=True,
    )
    load_seconds = time.perf_counter() - started

    args.output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = []
    if args.artifact in ("all", "documents"):
        artifacts.append(
            encode_artifact(
            model,
            args.input_dir / "eo_similarity_documents.jsonl",
            args.output_dir / "eo_document_embeddings.npz",
            "document_id",
            "cleaned_masked_text",
            FULL_DOCUMENT_INSTRUCTION,
            args.document_batch_size,
            )
        )
    if args.artifact in ("all", "segments"):
        artifacts.append(
            encode_artifact(
            model,
            args.input_dir / "eo_operative_segments.jsonl",
            args.output_dir / "eo_operative_segment_embeddings.npz",
            "segment_id",
            "text",
            OPERATIVE_SEGMENT_INSTRUCTION,
            args.segment_batch_size,
            )
        )
    provenance = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "tokenizer_revision": MODEL_REVISION,
        "model_path": str(args.model_path),
        "embedding_dimension": EMBEDDING_DIMENSION,
        "model_max_sequence_length": model.max_seq_length,
        "model_load_seconds": load_seconds,
        "device": torch.cuda.get_device_name(0),
        "torch_dtype": "float16",
        "normalized": True,
        "packages": {
            package: importlib.metadata.version(package)
            for package in (
                "numpy",
                "sentence-transformers",
                "torch",
                "transformers",
            )
        },
        "artifacts": artifacts,
    }
    provenance_path = args.output_dir / "provenance.json"
    provenance_path.write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    main()
