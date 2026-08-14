#!/usr/bin/env python3
"""Build one auditable Gemini joint-ranking request per pilot child."""

from __future__ import annotations

import argparse, csv, json
from collections import defaultdict
from pathlib import Path

from function_profile_pilot import function_text
from validate_function_profiles import _read_jsonl

ROOT=Path(__file__).resolve().parents[1]
PROMPT_VERSION = "function-parent-rank-v2"
INSTRUCTION = (
    "Rank all 25 earlier candidates from most to least plausible drafting parent for "
    "the child. Put yourself in the position of the child's drafter: would the earlier "
    "directive provide a useful substantive template for drafting the child's operative "
    "provisions? Consider together (1) whether they perform the same or a closely related "
    "governmental function, (2) whether the candidate supplies reusable operative language, "
    "organization, legal effects, or a sequence of actions, and (3) whether differences can "
    "largely be handled by substituting targets, dates, officials, countries, products, or "
    "other case-specific details. A different target does not defeat a parent relationship: "
    "operative mechanisms can be reused across targets and somewhat different policies. "
    "Near-verbatim or structurally parallel substantive operative provisions are strong "
    "evidence. Generic topical, actor, legal boilerplate, or isolated common-verb overlap is "
    "insufficient. Ask how much of the candidate's substantive drafting architecture could "
    "reasonably be reused after replacing case-specific details. Use only the supplied "
    "profiles. Return JSON only: {\"ranking\":[{\"parent_id\":string,\"policy_score\":number "
    "0..1,\"operative_score\":number 0..1,\"overall_score\":number 0..1,\"reason\":string,"
    "\"matched_child_function_ids\":[string],\"matched_parent_function_ids\":[string]}]}. "
    "Include every candidate exactly once in descending overall_score."
)

def compact(profile: dict) -> dict:
    return {kind:[{"function_id":x["function_id"],"description":function_text(x)}
                  for x in profile["profile"][f"{kind}_functions"]]
            for kind in ("policy","operative")}

def main() -> None:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--snapshot-dir",type=Path,default=ROOT/"data/parent_analysis/function_parent_pilot/provisional");p.add_argument("--run-label",default="thinking-off");p.add_argument("--output",type=Path);a=p.parse_args()
    manifest=json.loads((a.snapshot_dir/"snapshot_manifest.json").read_text())
    profiles={str(x["document_id"]):x for x in _read_jsonl(a.snapshot_dir/"profiles.jsonl")}
    grouped=defaultdict(list)
    with (a.snapshot_dir/"candidate_pool.csv").open(newline="",encoding="utf-8") as h:
        for row in csv.DictReader(h): grouped[row["child_id"]].append(row)
    output=a.output or a.snapshot_dir/("gemini_rank_requests.jsonl" if a.run_label=="thinking-off" else f"gemini_{a.run_label}_rank_requests.jsonl")
    with output.open("w",encoding="utf-8") as h:
        for cid,rows in sorted(grouped.items(),key=lambda x:int(x[0])):
            payload={"child":{"document_id":cid,"profile":compact(profiles[cid])},
                     "candidates":[{"parent_id":r["parent_id"],"retrieval_rank":int(r["fusion_rank"]),"profile":compact(profiles[r["parent_id"]])} for r in sorted(rows,key=lambda x:int(x["fusion_rank"]))]}
            request={"request_id":f"{PROMPT_VERSION}:{a.run_label}:{manifest['snapshot_hash'][:12]}:{cid}",
                     "contents":INSTRUCTION+"\n\nINPUT:\n"+json.dumps(payload,ensure_ascii=False),
                     "metadata":{"child_id":cid,"snapshot_hash":manifest["snapshot_hash"],"candidate_count":len(rows),"run_label":a.run_label,"prompt_version":PROMPT_VERSION}}
            h.write(json.dumps(request,ensure_ascii=False)+"\n")
    print(json.dumps({"requests":len(grouped),"output":str(output),"snapshot_hash":manifest["snapshot_hash"]},sort_keys=True))

if __name__=="__main__":main()
