#!/usr/bin/env python3
"""Self-contained Round 2 sub-directive Qwen benchmark CLI."""
from __future__ import annotations

import argparse, collections, datetime as dt, hashlib, json, math, os, random, re
import signal, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
GOLD = Path("/tmp/prez-authority-plan-df5ab70/data/Annotations/Round 2/round-2-finalized-validation-labels-with-subdirectives.json")
PROFILES = Path("data/parent_analysis/canonical_profiles/profiles.jsonl")
MODEL = "qwen3.8:27b-32k"
SEEDS = (20260819, 20260820, 20260821)
CODEBOOK = """Codes: 0 = no meaningful presidential-authority relationship; 1 = routine or indirect executive administration; 2 = explicit delegation/assignment of presidential authority; 3 = exercise, assertion, or transfer of substantial presidential authority; 4 = military operational command or use of force. Classify the operative function, not policy desirability or topic."""

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, path)

def load_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]

def clean(value):
    """Remove source-text/evidence fields recursively, retaining Flash summaries."""
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()
                if k not in {"evidence", "evidence_start", "evidence_end", "text", "labels"}}
    if isinstance(value, list): return [clean(v) for v in value]
    return value

def prompt_for(profile, target_ids):
    cleaned = clean(profile)
    return ("You are coding a presidential directive's operative function under this codebook.\n"
            + CODEBOOK + "\n\nThe JSON below is a Gemini Flash structural profile of ONE directive. "
            "The target is exactly the operative function group whose function_id appears in TARGET_FUNCTION_IDS. "
            "Use the entire profile only as context. Return JSON only: {\"code\": <0-4>, \"rationale\": \"<brief reason>\"}.\n\n"
            + json.dumps({"TARGET_FUNCTION_IDS": target_ids, "profile": cleaned}, ensure_ascii=False, separators=(",", ":")))

def prepare(_args):
    if not GOLD.exists(): raise SystemExit(f"Authoritative gold missing: {GOLD}")
    profiles = {str(x["document_id"]): x["profile"] for x in load_jsonl(PROFILES)}
    gold = json.loads(GOLD.read_text())["subdirective_records"]
    requests, mapping, no_profile_gold, unmatched_gold, seen = [], [], [], [], set()
    for rec in gold:
        doc, chunk = str(rec["global_dev_id"]), int(rec["chunk_number"])
        seg = f"{doc}:oa:{chunk:03d}"; profile = profiles.get(doc)
        funcs = [f for f in (profile or {}).get("operative_functions", []) if f.get("segment_id") == seg]
        if not profile:
            no_profile_gold.append({"global_dev_id": doc, "chunk_number": chunk, "segment_id": seg})
            continue
        if not funcs:
            unmatched_gold.append({"global_dev_id": doc, "chunk_number": chunk, "segment_id": seg})
            continue
        key = f"{doc}:{chunk:03d}"; seen.add((doc, seg))
        target_ids = [f["function_id"] for f in funcs]
        prompt = prompt_for(profile, target_ids)
        # Blind artifact must never contain raw annotation text or annotation labels.
        assert rec["text"] not in prompt and '"labels"' not in prompt
        assert '"evidence"' not in prompt and 'evidence_start' not in prompt and 'evidence_end' not in prompt
        requests.append({"target_id": key, "document_id": doc, "segment_id": seg,
                         "target_function_ids": target_ids, "prompt": prompt,
                         "prompt_hash": hashlib.sha256(prompt.encode()).hexdigest()})
        mapping.append({"target_id": key, "document_id": doc, "segment_id": seg,
                        "gold_code": int(rec["labels"]["code"])})
    unmatched_segments=[]
    gold_segments={(str(r['global_dev_id']), f"{r['global_dev_id']}:oa:{int(r['chunk_number']):03d}") for r in gold}
    for doc, profile in profiles.items():
        for seg in {f.get("segment_id") for f in profile.get("operative_functions", []) if f.get("segment_id")}:
            if (doc, seg) not in gold_segments and doc in {str(r['global_dev_id']) for r in gold}: unmatched_segments.append({"document_id":doc,"segment_id":seg})
    if len(requests) != 172: raise SystemExit(f"Expected 172 aligned targets, got {len(requests)}")
    write_json(OUT / "blind_requests.json", requests)
    write_json(OUT / "gold_mapping.json", mapping)
    no_aligned_directives=sorted({x['global_dev_id'] for x in unmatched_gold if sum(1 for q in requests if q['document_id']==x['global_dev_id'])==0})
    write_json(OUT / "exclusions.json", {"gold_without_profile":no_profile_gold,"gold_without_flash_target":unmatched_gold,"flash_without_gold_target":unmatched_segments,"directives_without_aligned_target":no_aligned_directives})
    write_json(OUT / "manifest.json", {"model":MODEL,"seeds":SEEDS,"target_count":len(requests),"gold_source":str(GOLD),"profile_source":str(PROFILES),"prepared_at":dt.datetime.now(dt.timezone.utc).isoformat()})
    print(f"Prepared {len(requests)} blind requests; {len(unmatched_gold)} gold chunks without Flash target; {len(unmatched_segments)} unmatched Flash segments; {len(no_aligned_directives)} directives without aligned target.")

def event(kind, **data):
    data.update(event=kind, at=dt.datetime.now(dt.timezone.utc).isoformat())
    with (OUT / "events.jsonl").open("a") as f: f.write(json.dumps(data) + "\n")

def responses(): return load_jsonl(OUT / "responses.jsonl") if (OUT / "responses.jsonl").exists() else []
def append_response(r):
    with (OUT / "responses.jsonl").open("a") as f: f.write(json.dumps(r, ensure_ascii=False) + "\n")

def parse_answer(raw):
    candidates = re.findall(r"\{(?:[^{}]|\{[^{}]*\})*\}", raw, re.S)
    for c in reversed(candidates):
        try:
            x=json.loads(c); code=x.get("code")
            if isinstance(code, str) and code.strip().isdigit(): code=int(code.strip())
            if code in range(5): return code, x.get("rationale", ""), True
        except json.JSONDecodeError: pass
    return None, "", False

class Tunnel:
    def __enter__(self):
        self.p=subprocess.Popen(["ssh","-o","BatchMode=yes","-o","ExitOnForwardFailure=yes","-o","ConnectTimeout=15","-N","-L","11434:127.0.0.1:11434","tigerteam"])
        time.sleep(2)
        if self.p.poll() is not None: raise RuntimeError("SSH tunnel failed to start")
        return self
    def __exit__(self,*_): self.p.terminate(); self.p.wait(timeout=10)

def call_ollama(prompt, seed):
    body=json.dumps({"model":MODEL,"stream":False,"think":True,"messages":[{"role":"user","content":prompt}],"options":{"seed":seed,"temperature":1,"top_p":0.95,"top_k":20}}).encode()
    req=urllib.request.Request("http://127.0.0.1:11434/api/chat", data=body, headers={"Content-Type":"application/json"})
    started=time.monotonic()
    # Bound any individual inference so an unattended run remains resumable.
    with urllib.request.urlopen(req, timeout=600) as r: answer=json.load(r)
    return answer, time.monotonic()-started

def refresh_status(requests, current=None, last=None):
    rs=responses(); terminal={(r['target_id'],r['seed']) for r in rs if r.get('terminal')}
    per={str(s):sum((q['target_id'],s) in terminal for q in requests) for s in SEEDS}
    write_json(OUT / "status.json", {"updated_at":dt.datetime.now(dt.timezone.utc).isoformat(),"total":len(requests)*len(SEEDS),"completed":len(terminal),"per_seed":per,"current":current,"latest":last})

def run(args):
    reqs=json.loads((OUT / "blind_requests.json").read_text())
    if args.smoke: reqs=reqs[:1]
    done={(r['target_id'],r['seed']) for r in responses() if r.get('terminal')}
    refresh_status(reqs); event("run_started", smoke=args.smoke, count=len(reqs)*3)
    with Tunnel():
        for q in reqs:
            for seed in SEEDS:
                if (q['target_id'],seed) in done: continue
                cur={"target_id":q['target_id'],"seed":seed,"started_at":dt.datetime.now(dt.timezone.utc).isoformat()}; refresh_status(reqs,cur); event("request_started",**cur)
                try:
                    reply, elapsed=call_ollama(q['prompt'], seed)
                    raw=reply.get('message',{}).get('content',''); code,rationale,valid=parse_answer(raw)
                    r={**cur,"terminal":True,"ok":valid,"code":code,"rationale":rationale,"raw_response":raw,"thinking":reply.get('message',{}).get('thinking',''),"elapsed_seconds":elapsed,"ollama":{k:v for k,v in reply.items() if k!='message'},"prompt_hash":q['prompt_hash']}
                    event("request_finished",target_id=q['target_id'],seed=seed,ok=valid,elapsed_seconds=elapsed)
                except Exception as e:
                    r={**cur,"terminal":True,"ok":False,"code":None,"error":repr(e),"elapsed_seconds":None,"prompt_hash":q['prompt_hash']}; event("request_error",target_id=q['target_id'],seed=seed,error=repr(e))
                append_response(r); refresh_status(reqs,None,r)
    event("run_finished", smoke=args.smoke); refresh_status(reqs)

def status(args):
    while True:
        p=OUT/"status.json"
        if not p.exists(): print("No status yet; run prepare then run."); return
        s=json.loads(p.read_text()); age=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(s['updated_at'])).total_seconds()
        done=s['completed']; total=s['total']; elapsed=[]
        for r in responses():
            if r.get('elapsed_seconds'): elapsed.append(r['elapsed_seconds'])
        rate=done/max(sum(elapsed),1) if elapsed else 0; eta=(total-done)/rate if rate else None
        print(f"{done}/{total} ({done/total:.1%}) seeds={s['per_seed']} current={s['current']} latest={s['latest'] and (s['latest'].get('target_id'),s['latest'].get('ok'))} age={age:.0f}s stale={age>180} ETA={eta and str(dt.timedelta(seconds=int(eta)))}")
        if not args.watch: return
        time.sleep(args.interval)

def metrics(rows):
    labels=range(5); n=len(rows); y=[r['gold_code'] for r in rows]; p=[r['prediction'] for r in rows]
    cm=[[sum(a==i and b==j for a,b in zip(y,p)) for j in labels] for i in labels]
    acc=sum(a==b for a,b in zip(y,p))/n if n else float('nan'); recalls=[]; fs=[]; weights=[]; per=[]
    for i in labels:
        tp=cm[i][i]; support=sum(cm[i]); predicted=sum(row[i] for row in cm); prec=tp/predicted if predicted else 0; rec=tp/support if support else 0; f=2*prec*rec/(prec+rec) if prec+rec else 0
        per.append({"code":i,"precision":prec,"recall":rec,"f1":f,"support":support});
        if support: recalls.append(rec); fs.append(f); weights.append((f,support))
    return {"n":n,"accuracy":acc,"balanced_accuracy":sum(recalls)/len(recalls),"macro_f1":sum(fs)/len(fs),"weighted_f1":sum(f*w for f,w in weights)/n,"confusion_matrix":cm,"per_class":per}

def bootstrap(rows, reps=1000):
    groups=collections.defaultdict(list)
    for r in rows: groups[r['document_id']].append(r)
    keys=list(groups); rng=random.Random(20260819); values=[]
    for _ in range(reps): values.append(metrics([x for k in (rng.choice(keys) for _ in keys) for x in groups[k]])['accuracy'])
    values.sort(); return [values[int(.025*(reps-1))],values[int(.975*(reps-1))]]

def evaluate(_args):
    gold={r['target_id']:r for r in json.loads((OUT/'gold_mapping.json').read_text())}; rs=responses(); by=collections.defaultdict(dict)
    for r in rs:
        if r.get('ok') and r.get('code') in range(5): by[r['target_id']][r['seed']]=r['code']
    if any(len(by[x])!=3 for x in gold): raise SystemExit("Evaluation requires valid terminal results for every target and seed.")
    report={"model":MODEL,"target_count":len(gold),"seeds":{},"agreement":{}}
    allrows={}
    for seed in SEEDS:
        rows=[{**g,"prediction":by[k][seed]} for k,g in gold.items()]; allrows[seed]=rows; report['seeds'][str(seed)]=metrics(rows)
    consensus=[]; agreements=[]; unstable=[]
    for k,g in gold.items():
        votes=[by[k][s] for s in SEEDS]; counts=collections.Counter(votes); best=max(counts.values()); winners=[c for c,n in counts.items() if n==best]; pred=sorted(winners)[len(winners)//2]
        unstable_flag=len(winners)>1; consensus.append({**g,"prediction":pred,"votes":votes,"unstable":unstable_flag}); agreements.append(best/3)
        if unstable_flag: unstable.append(k)
    report['consensus']=metrics(consensus); report['consensus']['clustered_bootstrap_accuracy_95ci']=bootstrap(consensus); report['agreement']={"mean_majority_fraction":sum(agreements)/len(agreements),"unstable_three_way_ties":unstable}
    # directive-balanced accuracy: mean of per-directive accuracy
    report['consensus']['directive_balanced_accuracy']=sum(metrics(list(g))['accuracy'] for _,g in itertools_group(consensus))/len({r['document_id'] for r in consensus})
    errors=[r for r in consensus if r['gold_code']!=r['prediction']]
    write_json(OUT/'evaluation.json',report); write_json(OUT/'error_table.json',errors)
    (OUT/'REPORT.md').write_text("# Qwen Round 2 sub-directive benchmark\n\n"+json.dumps(report,indent=2)+"\n\nErrors: `error_table.json`.\n")
    print(json.dumps(report['consensus'],indent=2))

def itertools_group(rows):
    d=collections.defaultdict(list)
    for r in rows:d[r['document_id']].append(r)
    return d.items()

def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(required=True)
    sub.add_parser('prepare').set_defaults(func=prepare)
    r=sub.add_parser('run'); r.add_argument('--smoke',action='store_true'); r.set_defaults(func=run)
    s=sub.add_parser('status'); s.add_argument('--watch',action='store_true'); s.add_argument('--interval',type=float,default=15); s.set_defaults(func=status)
    sub.add_parser('evaluate').set_defaults(func=evaluate)
    a=ap.parse_args(); a.func(a)
if __name__=='__main__': main()
