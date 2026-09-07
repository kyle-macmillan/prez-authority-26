#!/usr/bin/env python3
"""Retrieve a shared 25-parent pool from function and lexical channels."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from function_profile_pilot import parse_date, reciprocal_rank_fusion
from validate_function_profiles import _read_jsonl


ROOT = Path(__file__).resolve().parents[1]
TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)*")


def words(text: str) -> list[str]: return [x.casefold() for x in TOKEN_RE.findall(text)]


def bm25_scores(query: list[str], corpus: dict[str, list[str]]) -> dict[str, float]:
    n = len(corpus); avg = sum(map(len, corpus.values())) / max(n, 1); q = Counter(query)
    df = Counter(token for tokens in corpus.values() for token in set(tokens)); output = {}
    for did, tokens in corpus.items():
        tf = Counter(tokens); score = 0.0
        for token in q:
            if token not in df: continue
            idf = math.log(1 + (n - df[token] + .5) / (df[token] + .5))
            score += idf * tf[token] * 2.2 / (tf[token] + 1.2 * (.25 + .75 * len(tokens) / avg))
        output[did] = score
    return output


def reuse_score(child: list[str], parent: list[str], size: int = 10) -> int:
    if len(child) < size or len(parent) < size: return 0
    p = {tuple(parent[i:i + size]) for i in range(len(parent) - size + 1)}
    return sum(tuple(child[i:i + size]) in p for i in range(len(child) - size + 1))


def shingles(tokens: list[str], size: int = 10) -> list[tuple[str, ...]]:
    return [tuple(tokens[i:i + size]) for i in range(len(tokens) - size + 1)]


def indexed_bm25_scores(
    query: list[str], eligible: list[str], lengths: dict[str, int],
    postings: dict[str, dict[str, int]],
) -> dict[str, float]:
    """Exact ``bm25_scores`` equivalent without rescanning every document's tokens."""
    eligible_set = set(eligible); n = len(eligible); avg = sum(lengths[x] for x in eligible) / max(n, 1)
    output = {did: 0.0 for did in eligible}
    for token in set(query):
        matches = {did: tf for did, tf in postings.get(token, {}).items() if did in eligible_set}
        if not matches: continue
        df = len(matches); idf = math.log(1 + (n - df + .5) / (df + .5))
        for did, tf in matches.items():
            output[did] += idf * tf * 2.2 / (tf + 1.2 * (.25 + .75 * lengths[did] / avg))
    return output


def indexed_reuse_scores(
    child: list[str], eligible: list[str], shingle_postings: dict[tuple[str, ...], list[str]],
) -> dict[str, float]:
    counts = Counter(shingles(child))
    eligible_set = set(eligible)
    output = {did: 0.0 for did in eligible}
    for gram, count in counts.items():
        for did in shingle_postings.get(gram, []):
            if did in eligible_set: output[did] += float(count)
    return output


def ranks(scores: dict[str, float]) -> dict[str, int]:
    return {did: i for i, did in enumerate(sorted(scores, key=lambda x: (-scores[x], int(x))), 1)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, default=ROOT / "data/parent_analysis/canonical_profiles")
    parser.add_argument("--input-dir", type=Path, default=ROOT / "data/parent_analysis_all_corpus")
    parser.add_argument("--children", type=Path, help="Child CSV; defaults to sampled_children.csv in snapshot-dir")
    parser.add_argument("--output", type=Path, help="Candidate CSV; defaults to candidate_pool.csv in snapshot-dir")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--fusion", choices=("rrf", "reserved"), default="rrf")
    parser.add_argument("--include-document-ablation", action="store_true")
    parser.add_argument("--allow-incomplete-profiles", action="store_true")
    parser.add_argument("--progress-every", type=int, default=10, help="emit measured ETA every N children")
    args = parser.parse_args()
    if args.progress_every < 1: parser.error("--progress-every must be positive")
    snapshot = json.loads((args.snapshot_dir / "snapshot_manifest.json").read_text())
    if snapshot.get("complete") is False and not args.allow_incomplete_profiles:
        raise RuntimeError("canonical profile snapshot is incomplete")
    with np.load(args.snapshot_dir / "function_embeddings.npz") as e:
        if str(e["snapshot_hash"].item()) != snapshot["snapshot_hash"]: raise ValueError("embedding snapshot mismatch")
        dids=e["document_ids"].astype(str); kinds=e["kinds"].astype(str); q=e["query_embeddings"]; d=e["document_embeddings"]
    by_kind = defaultdict(lambda: defaultdict(list))
    for i,(did,kind) in enumerate(zip(dids,kinds,strict=True)): by_kind[did][kind].append(i)
    dates={}
    with (args.input_dir / "directive_similarity_documents.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row=json.loads(line); did=str(row["document_id"])
                if did in by_kind: dates[did]=parse_date(row["date"])
    segments=defaultdict(list)
    for x in _read_jsonl(args.input_dir / "directive_operative_segments.jsonl"): segments[str(x["document_id"])].append(x["text"])
    lexical={did:words(" ".join(segments.get(did,[]))) for did in by_kind}
    lengths={did:len(tokens) for did,tokens in lexical.items()}
    postings=defaultdict(dict)
    shingle_postings=defaultdict(list)
    for did,tokens in lexical.items():
        postings_for_doc=Counter(tokens)
        for token,tf in postings_for_doc.items(): postings[token][did]=tf
        for gram in set(shingles(tokens)): shingle_postings[gram].append(did)

    # Concatenate each kind's parent vectors by document so reduceat can score all
    # parents in one matrix multiplication instead of thousands of tiny products.
    vector_index={}
    for kind in ("policy","operative"):
        kind_dids=[did for did in sorted(by_kind,key=int) if by_kind[did][kind]]
        grouped=[by_kind[did][kind] for did in kind_dids]
        indices=np.asarray([i for group in grouped for i in group],dtype=np.int64)
        starts=np.cumsum([0]+[len(group) for group in grouped[:-1]],dtype=np.int64)
        vector_index[kind]=(kind_dids,indices,starts)
    children_path = args.children or args.snapshot_dir / "sampled_children.csv"
    with children_path.open(newline="",encoding="utf-8") as h: children=list(csv.DictReader(h))
    missing=sorted({child["document_id"] for child in children}-set(by_kind),key=int)
    if missing:
        raise ValueError(f"{len(missing)} children have no function embeddings; examples: {missing[:10]}")
    doc_vectors=None
    if args.include_document_ablation:
        with np.load(args.input_dir / "embeddings/directive_document_embeddings.npz") as e:
            doc_vectors={str(x):(e["query_embeddings"][i],e["document_embeddings"][i]) for i,x in enumerate(e["ids"])}
    output=[]; started=time.monotonic(); total_children=len(children)
    print(json.dumps({"event":"retrieval_started","children":total_children}),flush=True)
    for child_number,child in enumerate(children,1):
        cid=child["document_id"]; eligible=[pid for pid in by_kind if dates[pid] < dates[cid]]
        channel_scores={"policy":{},"operative":{}}
        for kind in ("policy","operative"):
            ci=by_kind[cid][kind]; kind_dids,indices,starts=vector_index[kind]
            if ci and len(indices):
                matrix=q[ci]@d[indices].T
                scores=np.maximum.reduceat(matrix,starts,axis=1).mean(axis=0)
                all_scores=dict(zip(kind_dids,map(float,scores),strict=True))
                channel_scores[kind]={pid:all_scores.get(pid,0.0) for pid in eligible}
            else: channel_scores[kind]={pid:0.0 for pid in eligible}
        bm=indexed_bm25_scores(lexical[cid],eligible,lengths,postings)
        reuse=indexed_reuse_scores(lexical[cid],eligible,shingle_postings)
        channel_scores.update({"bm25":bm,"text_reuse":reuse})
        if doc_vectors:
            channel_scores["document"]={pid:float(doc_vectors[cid][0]@doc_vectors[pid][1]) for pid in eligible}
        channel_ranks={name:ranks(values) for name,values in channel_scores.items()}
        fused={pid:reciprocal_rank_fusion({name:r[pid] for name,r in channel_ranks.items()},args.rrf_k) for pid in eligible}
        ordered=sorted(eligible,key=lambda x:(-fused[x],int(x)))
        if args.fusion == "reserved":
            selected=[]
            reservations={"policy":8,"operative":8,"bm25":5,"text_reuse":4}
            for name,count in reservations.items():
                for pid in sorted(eligible,key=lambda x:(channel_ranks[name][x],int(x)))[:count]:
                    if pid not in selected:selected.append(pid)
            selected=(selected+[pid for pid in ordered if pid not in selected])[:args.limit]
        else:selected=ordered[:args.limit]
        for rank,pid in enumerate(selected,1):
            row={"child_id":cid,"parent_id":pid,"fusion_method":args.fusion,"fusion_rank":rank,"fusion_score":fused[pid],"snapshot_hash":snapshot["snapshot_hash"]}
            for name in channel_scores: row[f"{name}_score"]=channel_scores[name][pid];row[f"{name}_rank"]=channel_ranks[name][pid]
            output.append(row)
        if child_number % args.progress_every == 0 or child_number == total_children:
            elapsed=time.monotonic()-started; rate=child_number/elapsed
            print(json.dumps({"event":"retrieval_progress","completed":child_number,"total":total_children,
                              "percent":round(100*child_number/total_children,2),"elapsed_seconds":round(elapsed,1),
                              "children_per_second":round(rate,4),
                              "eta_seconds":round((total_children-child_number)/rate,1)}),flush=True)
    path=args.output or args.snapshot_dir/("candidate_pool_with_document_ablation.csv" if doc_vectors else "candidate_pool.csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w",newline="",encoding="utf-8") as h:
        writer=csv.DictWriter(h,fieldnames=list(output[0]));writer.writeheader();writer.writerows(output)
    manifest_path=path.with_name("candidate_pool_manifest.json")
    manifest_path.write_text(json.dumps({"schema_version":1,"snapshot_hash":snapshot["snapshot_hash"],"canonical_snapshot_complete":bool(snapshot.get("complete")),"canonical_profile_count":snapshot.get("canonical_profiles"),"unresolved_profile_exclusions":snapshot.get("requests_remaining",0),"allow_incomplete_profiles":args.allow_incomplete_profiles,"fusion":args.fusion,"rrf_k":args.rrf_k,"limit":args.limit,"channels":["policy","operative","bm25","text_reuse"],"document_ablation":bool(doc_vectors),"children":str(children_path)},indent=2,sort_keys=True)+"\n")
    print(json.dumps({"children":len(children),"pairs":len(output),"snapshot_hash":snapshot["snapshot_hash"],"output":str(path)},sort_keys=True))


if __name__ == "__main__": main()
