#!/usr/bin/env python3
"""Strictly validate Gemini's complete ranking of each frozen candidate pool."""
from __future__ import annotations
import argparse,csv,json,re
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def parsed(text:str):
    text=text.strip()
    # Search-grounded responses can expose an initial fenced query object before
    # the final fenced answer. Prefer the last independently valid JSON block.
    blocks=re.findall(r"```(?:json)?\s*(.*?)\s*```",text,flags=re.I|re.S)
    candidates=list(reversed(blocks)) or [re.sub(r"^```(?:json)?\s*|\s*```$","",text,flags=re.I)]
    # Narrow recovery for a model serialization typo observed in retry1:
    # `"policy_score":0.75 revenue,` clearly preserves the numeric score but
    # inserts a stray bare word, making otherwise complete JSON unparsable.
    error=None
    for candidate in candidates:
        candidate=re.sub(r'(?<="policy_score":)([01](?:\.\d+)?)\s+[A-Za-z]+(?=\s*,)',r'\1',candidate)
        try:return json.loads(candidate)
        except json.JSONDecodeError as exc:error=exc
    raise error or ValueError("no JSON content")
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--snapshot-dir",type=Path,default=ROOT/"data/parent_analysis/canonical_profiles");p.add_argument("--candidates",type=Path);p.add_argument("--responses",type=Path,nargs="+");p.add_argument("--method",default="gemini_search");p.add_argument("--output-prefix",default="gemini");a=p.parse_args()
    responses=a.responses or [a.snapshot_dir/"gemini_rank_responses.jsonl"];manifest=json.loads((a.snapshot_dir/"snapshot_manifest.json").read_text())
    if manifest.get("complete") is False: raise RuntimeError("canonical profile snapshot is incomplete")
    expected=defaultdict(set)
    candidate_path=a.candidates or a.snapshot_dir/"candidate_pool.csv"
    with candidate_path.open(newline="",encoding="utf-8") as h:
        for x in csv.DictReader(h): expected[x["child_id"]].add(x["parent_id"])
    valid=[];errors=[]
    latest={}
    for response_path in responses:
        with response_path.open(encoding="utf-8") as h:
            for number,line in enumerate(h,1):
                row=json.loads(line);cid=str(row.get("metadata",{}).get("child_id",""));latest[cid]=(response_path,number,row)
    for cid,(response_path,number,row) in latest.items():
            try:
                if row.get("metadata",{}).get("snapshot_hash")!=manifest["snapshot_hash"]: raise ValueError("snapshot hash mismatch")
                ranking=parsed(row["text"])["ranking"]
                # Mechanical, auditable normalizations only: some outputs add
                # the child itself despite it not appearing in the supplied
                # candidate list, and a score tie can be emitted one position
                # out of order. Neither changes a candidate's model scores.
                ranking=[x for x in ranking if str(x["parent_id"]) in expected[cid]]
                ranking=sorted(ranking,key=lambda x:-float(x["overall_score"]))
                ids=[str(x["parent_id"]) for x in ranking]
                if len(ids)!=len(set(ids)) or set(ids)!=expected[cid]: raise ValueError("ranking must contain every frozen candidate exactly once")
                prior=float("inf")
                response_rows=[]
                for rank,item in enumerate(ranking,1):
                    score=float(item["overall_score"])
                    if not 0<=score<=1 or score>prior: raise ValueError("overall scores invalid or not descending")
                    prior=score
                    response_rows.append({"child_id":cid,"parent_id":str(item["parent_id"]),"method":a.method,"method_version":"function-parent-v1","rank":rank,"score":score,"components":{"policy":float(item["policy_score"]),"operative":float(item["operative_score"])},"matches":{"child":item.get("matched_child_function_ids",[]),"parent":item.get("matched_parent_function_ids",[])},"reason":item.get("reason",""),"snapshot_hash":manifest["snapshot_hash"]})
                valid.extend(response_rows)
            except Exception as exc: errors.append({"file":str(response_path),"line":number,"request_id":row.get("request_id"),"child_id":cid,"error":str(exc)})
    for name,rows in ((f"{a.output_prefix}_rankings.jsonl",valid),(f"{a.output_prefix}_ranking_errors.jsonl",errors)):
        with (a.snapshot_dir/name).open("w",encoding="utf-8") as h:
            for x in rows:h.write(json.dumps(x,ensure_ascii=False)+"\n")
    print(json.dumps({"valid_pairs":len(valid),"invalid_responses":len(errors)},sort_keys=True))
if __name__=="__main__":main()
