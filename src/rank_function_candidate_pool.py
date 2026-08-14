#!/usr/bin/env python3
"""Rank the frozen pilot pool with deterministic alignment or local Qwen."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from function_profile_pilot import alignment_coverage, function_text
from validate_function_profiles import _read_jsonl


ROOT = Path(__file__).resolve().parents[1]
QWEN_INSTRUCTIONS = {
    "policy": "Does the earlier directive address the same specific policy problem as the later directive? Generic topical overlap is insufficient.",
    "operative": "Does the earlier directive use a materially similar administrative or legal mechanism as the later directive? Generic actor or boilerplate overlap is insufficient.",
    "joint": "Is the earlier directive the most plausible functional precedent for the later directive, considering both the specific policy problem and especially the operative mechanism?",
}


def profile_text(profile: dict, kind: str) -> str:
    functions = profile["profile"][f"{kind}_functions"]
    return "\n\n".join(f"[{x['function_id']}]\n{function_text(x)}" for x in functions)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("method", choices=("deterministic", "qwen"))
    parser.add_argument("--snapshot-dir", type=Path, default=ROOT / "data/parent_analysis/function_parent_pilot/provisional")
    parser.add_argument("--model-path", type=Path, default=ROOT / ".cache/models/Qwen3-Reranker-0.6B")
    parser.add_argument("--max-batch", type=int, default=4)
    args = parser.parse_args()
    manifest = json.loads((args.snapshot_dir / "snapshot_manifest.json").read_text())
    profiles = {str(x["document_id"]): x for x in _read_jsonl(args.snapshot_dir / "profiles.jsonl")}
    with (args.snapshot_dir / "candidate_pool.csv").open(newline="", encoding="utf-8") as handle:
        pool = list(csv.DictReader(handle))
    by_child = defaultdict(list)
    for row in pool: by_child[row["child_id"]].append(row)
    with np.load(args.snapshot_dir / "function_embeddings.npz") as data:
        if str(data["snapshot_hash"].item()) != manifest["snapshot_hash"]: raise ValueError("snapshot mismatch")
        dids=data["document_ids"].astype(str); kinds=data["kinds"].astype(str); fids=data["function_ids"].astype(str)
        query=data["query_embeddings"]; document=data["document_embeddings"]
    indices=defaultdict(lambda:defaultdict(list))
    for i,(did,kind) in enumerate(zip(dids,kinds,strict=True)): indices[did][kind].append(i)
    scorer = None
    if args.method == "qwen":
        from rerank_qwen_candidates import QwenReranker
        scorer = QwenReranker(args.model_path)
    output=[]
    for child_id, rows in sorted(by_child.items(), key=lambda x:int(x[0])):
        scored=[]
        for row in rows:
            parent_id=row["parent_id"]; components={}; matches={}
            if args.method == "deterministic":
                for kind in ("policy", "operative"):
                    ci=indices[child_id][kind]; pi=indices[parent_id][kind]
                    matrix=query[ci]@document[pi].T
                    components[kind], aligned=alignment_coverage(matrix)
                    matches[kind]=[{"child_function_id":fids[ci[a]],"parent_function_id":fids[pi[b]],"score":score}
                                   for a,b,score in aligned]
                score=.30*components["policy"]+.70*components["operative"]
            else:
                pairs=[]
                for kind in ("policy", "operative"):
                    pairs.append((profile_text(profiles[child_id],kind),profile_text(profiles[parent_id],kind)))
                pairs.append((profile_text(profiles[child_id],"policy")+"\n\n"+profile_text(profiles[child_id],"operative"),
                              profile_text(profiles[parent_id],"policy")+"\n\n"+profile_text(profiles[parent_id],"operative")))
                values=[]
                for kind,pair in zip(("policy","operative","joint"),pairs,strict=True):
                    # Instruction is explicit in the query so the shared scorer remains backward compatible.
                    values.append(scorer.score_many([(QWEN_INSTRUCTIONS[kind]+"\n\n"+pair[0],pair[1])],max_batch=args.max_batch)[0])
                components=dict(zip(("policy","operative","joint"),values,strict=True))
                score=.20*values[0]+.50*values[1]+.30*values[2]; matches={}
            scored.append((score,int(row["fusion_rank"]),parent_id,row,components,matches))
        scored.sort(key=lambda x:(-x[0],x[1],int(x[2])))
        for rank,(score,_,parent_id,row,components,matches) in enumerate(scored,1):
            output.append({"child_id":child_id,"parent_id":parent_id,"method":args.method,
                           "method_version":"function-parent-v1","rank":rank,"score":score,
                           "retrieval_rank":row["fusion_rank"],"components":components,"matches":matches,
                           "snapshot_hash":manifest["snapshot_hash"]})
    path=args.snapshot_dir/f"{args.method}_rankings.jsonl"
    with path.open("w",encoding="utf-8") as handle:
        for row in output: handle.write(json.dumps(row,ensure_ascii=False)+"\n")
    print(json.dumps({"method":args.method,"children":len(by_child),"pairs":len(output),"output":str(path)},sort_keys=True))


if __name__ == "__main__": main()
