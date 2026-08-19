#!/usr/bin/env python3
"""Evaluate candidate-pool recall/MRR against eligible explicit-reference edges."""
from __future__ import annotations
import argparse,csv,json
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("candidate_pool",type=Path);p.add_argument("--edges",type=Path,default=ROOT/"data/parent_analysis_full/automatic_edges.csv");p.add_argument("--output",type=Path);a=p.parse_args()
    ranks={}
    with a.candidate_pool.open(newline="",encoding="utf-8") as h:
        for x in csv.DictReader(h):ranks[(x["child_id"],x["parent_id"])]=int(x["fusion_rank"])
    truth=defaultdict(set)
    allowed={"amends","revokes","modifies","continues","supersedes","replaces","delegates"}
    with a.edges.open(newline="",encoding="utf-8") as h:
        for x in csv.DictReader(h):
            if x["relation"] in allowed and any(c==x["child_id"] for c,_ in ranks):truth[x["child_id"]].add(x["parent_id"])
    best=[]
    for cid,parents in truth.items():
        found=[ranks[(cid,p)] for p in parents if (cid,p) in ranks];best.append(min(found) if found else None)
    metrics={"eligible_children":len(best),"recall_at_25":sum(x is not None and x<=25 for x in best)/len(best) if best else None,"recall_at_10":sum(x is not None and x<=10 for x in best)/len(best) if best else None,"mrr":sum(1/x for x in best if x)/len(best) if best else None}
    out=a.output or a.candidate_pool.with_suffix(".evaluation.json");out.write_text(json.dumps(metrics,indent=2,sort_keys=True)+"\n");print(json.dumps(metrics,sort_keys=True))
if __name__=="__main__":main()
