"""Rebuild provenance for already validated directive embedding caches."""

from __future__ import annotations

import importlib.metadata
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from embed_parent_analysis import (
    EMBEDDING_DIMENSION,
    FULL_DOCUMENT_INSTRUCTION,
    MODEL_ID,
    MODEL_REVISION,
    OPERATIVE_SEGMENT_INSTRUCTION,
    read_jsonl,
    sha256_file,
    token_length_audit,
    validate_embeddings,
)


def artifact_entry(
    tokenizer,
    source: Path,
    output: Path,
    id_field: str,
    text_field: str,
    instruction: str,
) -> dict:
    rows = read_jsonl(source)
    ids = [str(row[id_field]) for row in rows]
    texts = [row[text_field] for row in rows]
    with np.load(output) as cache:
        cached_ids = cache["ids"].astype(str).tolist()
        query = cache["query_embeddings"]
        documents = cache["document_embeddings"]
        if cached_ids != ids:
            raise ValueError(f"{output} identifiers do not match {source}")
        validate_embeddings("query", query, len(rows))
        validate_embeddings("document", documents, len(rows))
        shape = list(query.shape)
        dtype = str(query.dtype)
    return {
        "source": str(source),
        "source_sha256": sha256_file(source),
        "output": str(output),
        "output_sha256": sha256_file(output),
        "id_field": id_field,
        "text_field": text_field,
        "instruction": instruction,
        "roles": {
            "query_embeddings": "instructed child queries",
            "document_embeddings": "unprompted candidate-parent documents",
        },
        "shape": shape,
        "dtype": dtype,
        "token_lengths": token_length_audit(tokenizer, texts, instruction, 32768),
        "recovered_from_validated_cache": True,
    }


def main() -> None:
    input_dir = Path("data/parent_analysis")
    output_dir = input_dir / "embeddings"
    model_path = Path(
        ".cache/huggingface/hub/"
        f"models--Qwen--Qwen3-Embedding-0.6B/snapshots/{MODEL_REVISION}"
    )
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(str(model_path), local_files_only=True)
    artifacts = [
        artifact_entry(
            tokenizer,
            input_dir / "directive_similarity_documents.jsonl",
            output_dir / "directive_document_embeddings.npz",
            "document_id",
            "cleaned_masked_text",
            FULL_DOCUMENT_INSTRUCTION,
        ),
        artifact_entry(
            tokenizer,
            input_dir / "directive_operative_segments.jsonl",
            output_dir / "directive_operative_segment_embeddings.npz",
            "segment_id",
            "text",
            OPERATIVE_SEGMENT_INSTRUCTION,
        ),
    ]
    previous = json.loads((output_dir / "provenance.json").read_text(encoding="utf-8"))
    provenance = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "tokenizer_revision": MODEL_REVISION,
        "model_path": str(model_path),
        "embedding_dimension": EMBEDDING_DIMENSION,
        "model_max_sequence_length": 32768,
        "device": previous.get("device", "NVIDIA GeForce RTX 2080 Ti"),
        "torch_dtype": "float16",
        "normalized": True,
        "packages": {
            package: importlib.metadata.version(package)
            for package in ("numpy", "sentence-transformers", "torch", "transformers")
        },
        "artifacts": artifacts,
    }
    (output_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    main()
