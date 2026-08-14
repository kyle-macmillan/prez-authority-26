#!/usr/bin/env python3
"""Incrementally embed policy and operative functions in a profile snapshot."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import numpy as np

from function_profile_pilot import content_hash, profile_function_rows
from validate_function_profiles import _read_jsonl


ROOT = Path(__file__).resolve().parents[1]
MODEL_REVISION = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
MODEL_PATH = ROOT / f".cache/huggingface/hub/models--Qwen--Qwen3-Embedding-0.6B/snapshots/{MODEL_REVISION}"
INSTRUCTIONS = {
    "policy": "Represent this policy function for retrieving earlier presidential directives addressing the same specific policy problem.",
    "operative": "Represent this operative function for retrieving earlier presidential directives using a materially similar administrative or legal mechanism.",
}


def load_existing(path: Path) -> dict[tuple[str, str], tuple[np.ndarray, np.ndarray]]:
    if not path.exists(): return {}
    with np.load(path) as cache:
        return {
            (str(row_id), str(row_hash)): (query, document)
            for row_id, row_hash, query, document in zip(
                cache["row_ids"], cache["row_hashes"], cache["query_embeddings"],
                cache["document_embeddings"], strict=True,
            )
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, default=ROOT / "data/parent_analysis/canonical_profiles")
    parser.add_argument("--model-path", type=Path, default=MODEL_PATH)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--max-seq-length", type=int, default=512)
    parser.add_argument("--allow-incomplete-profiles", action="store_true")
    args = parser.parse_args()
    profiles = _read_jsonl(args.snapshot_dir / "profiles.jsonl")
    manifest = json.loads((args.snapshot_dir / "snapshot_manifest.json").read_text())
    if manifest.get("complete") is False and not args.allow_incomplete_profiles:
        raise RuntimeError("canonical profile snapshot is incomplete")
    rows = profile_function_rows(profiles)
    for row in rows:
        row["row_id"] = f"{row['document_id']}:{row['kind']}:{row['function_id']}"
        row["row_hash"] = content_hash({"kind": row["kind"], "text": row["text"]})
    output = args.snapshot_dir / "function_embeddings.npz"
    existing = load_existing(output)
    missing = [row for row in rows if (row["row_id"], row["row_hash"]) not in existing]
    if missing:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(str(args.model_path), local_files_only=True)
        model.max_seq_length = args.max_seq_length
        document = model.encode(
            [row["text"] for row in missing], batch_size=args.batch_size,
            normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=True,
        )
        query = np.empty_like(document)
        for kind in INSTRUCTIONS:
            indices = [i for i, row in enumerate(missing) if row["kind"] == kind]
            if indices:
                query[indices] = model.encode(
                    [f"Instruct: {INSTRUCTIONS[kind]}\nQuery:{missing[i]['text']}" for i in indices],
                    batch_size=args.batch_size, normalize_embeddings=True,
                    convert_to_numpy=True, show_progress_bar=True,
                )
        existing.update({
            (row["row_id"], row["row_hash"]): (query[i], document[i])
            for i, row in enumerate(missing)
        })
    query = np.asarray([existing[(row["row_id"], row["row_hash"])][0] for row in rows])
    document = np.asarray([existing[(row["row_id"], row["row_hash"])][1] for row in rows])
    with tempfile.NamedTemporaryFile(dir=args.snapshot_dir, suffix=".npz", delete=False) as handle:
        temporary = Path(handle.name)
    np.savez(
        temporary, snapshot_hash=manifest["snapshot_hash"],
        row_ids=np.asarray([row["row_id"] for row in rows]),
        row_hashes=np.asarray([row["row_hash"] for row in rows]),
        document_ids=np.asarray([row["document_id"] for row in rows]),
        kinds=np.asarray([row["kind"] for row in rows]),
        function_ids=np.asarray([row["function_id"] for row in rows]),
        segment_ids=np.asarray([row["segment_id"] for row in rows]),
        query_embeddings=query, document_embeddings=document,
    )
    temporary.replace(output)
    embedding_manifest = {
        "schema_version": 1, "snapshot_hash": manifest["snapshot_hash"],
        "model": "Qwen/Qwen3-Embedding-0.6B", "model_revision": MODEL_REVISION,
        "function_rows": len(rows), "new_embeddings": len(missing),
        "semantic_fields": ["actor", "action", "target", "mechanism", "effect", "condition", "timing"],
        "evidence_excluded": True,
        "max_seq_length": args.max_seq_length,
    }
    (args.snapshot_dir / "function_embedding_manifest.json").write_text(
        json.dumps(embedding_manifest, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(embedding_manifest, sort_keys=True))


if __name__ == "__main__": main()
