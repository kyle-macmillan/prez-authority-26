#!/usr/bin/env python3
"""Build the authority-blind, three-dimension parent-method annotation viewer."""

from __future__ import annotations

import argparse
import csv
import html
import json
import random
from collections import defaultdict
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def build_payload(
    sampled: list[dict], candidates: list[dict], documents: list[dict],
    segment_rows: list[dict], seed: int,
) -> dict:
    docs = {str(row["document_id"]): row for row in documents}
    segments: dict[str, list[dict]] = defaultdict(list)
    for row in segment_rows:
        segments[str(row["document_id"])].append({
            "segment_id": row["segment_id"], "text": row["text"]
        })
    candidates_by_child: dict[str, list[str]] = defaultdict(list)
    for row in candidates:
        candidates_by_child[str(row["child_id"])].append(str(row["parent_id"]))

    def document_payload(document_id: str) -> dict:
        row = docs[document_id]
        # Do not serialize masked_authorities or removed_vesting_clauses.  The
        # browser therefore cannot reveal authority even through its dev tools.
        return {
            "document_id": document_id,
            "document_type": row["document_type"], "identifier": row.get("identifier", ""),
            "title": row.get("title", ""), "date": row["date"],
            "text": row["cleaned_masked_text"], "segments": segments.get(document_id, []),
        }

    children = []
    for sample in sampled:
        child_id = str(sample.get("document_id", sample.get("child_id")))
        parent_ids = sorted(set(candidates_by_child.get(child_id, [])))
        random.Random(f"{seed}:{child_id}").shuffle(parent_ids)
        children.append({
            "sample_id": sample.get("sample_id", child_id),
            "known_parent_genre": sample.get("known_parent_genre", ""),
            "child": document_payload(child_id),
            "candidates": [document_payload(parent_id) for parent_id in parent_ids],
        })
    return {
        "schema_version": 2, "seed": seed,
        "candidate_order": "deterministically randomized; retrieval ranks concealed",
        "definition": (
            "An earlier directive addressing the same specific policy problem through a "
            "materially similar operative mechanism."
        ),
        "children": children,
    }


def safe_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def build_html(payload: dict) -> str:
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Parent-method review</title>
<style>body{{margin:0;font:14px system-ui;background:#f4f6f9;color:#172033}}header{{position:sticky;top:0;z-index:3;background:#172033;color:white;padding:10px 18px;display:flex;gap:15px;align-items:center}}header b{{margin-right:auto}}button,input,textarea{{font:inherit}}main{{padding:16px}}.nav{{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:12px}}.nav button,.ratings button{{border:1px solid #b8c2cf;background:white;border-radius:5px;padding:6px 9px}}.nav button.active{{background:#245ea8;color:white}}.compare{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}article,.decision{{background:white;border:1px solid #d7dee8;border-radius:8px}}h2,h3{{margin:0 0 5px}}.head{{padding:11px;border-bottom:1px solid #ddd}}.text{{white-space:pre-wrap;font:15px/1.55 Georgia,serif;padding:13px;max-height:52vh;overflow:auto}}.segments{{padding:10px;background:#f8fafc;max-height:25vh;overflow:auto}}.segment{{padding:6px;border-top:1px solid #ddd}}.decision{{margin-top:12px;padding:12px}}.dimension{{margin:8px 0}}.ratings button.selected{{background:#245ea8;color:white}}textarea{{width:100%;min-height:65px;margin-top:8px}}.muted{{color:#64748b}}@media(max-width:850px){{.compare{{grid-template-columns:1fr}}}}</style></head><body>
<header><b>Authority-blind parent-method review</b><span id="progress"></span><label>Reviewer <input id="reviewer"></label><button id="export">Export JSON</button></header><main><h2 id="child-title"></h2><p id="definition"></p><div class="nav" id="child-nav"></div><div class="nav" id="candidate-nav"></div><div id="content"></div></main>
<script>const DATA={safe_json(payload)},KEY='parent-method-v2-'+DATA.seed,state=JSON.parse(localStorage.getItem(KEY)||'{{}}');let ci=0,pi=0;const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));const label=d=>d.title||d.identifier||('Document '+d.document_id);const pairState=(c,p)=>{{let x=state[c]||(state[c]={{}});return x[p]||(x[p]={{policy:'',mechanism:'',overall:'',evidence_segment_ids:'',notes:''}})}};function save(){{localStorage.setItem(KEY,JSON.stringify(state));renderProgress()}}function renderProgress(){{let done=0,total=0;DATA.children.forEach(x=>x.candidates.forEach(p=>{{total++;if(state[x.child.document_id]?.[p.document_id]?.overall)done++}}));document.querySelector('#progress').textContent=done+' / '+total+' pairs'}}function nav(){{document.querySelector('#child-nav').innerHTML=DATA.children.map((x,i)=>'<button class="'+(i===ci?'active':'')+'" data-i="'+i+'">'+esc(x.sample_id)+'</button>').join('');document.querySelectorAll('#child-nav button').forEach(b=>b.onclick=()=>{{ci=+b.dataset.i;pi=0;render()}});let x=DATA.children[ci];document.querySelector('#candidate-nav').innerHTML=x.candidates.map((p,i)=>'<button class="'+(i===pi?'active':'')+'" data-i="'+i+'">Candidate '+(i+1)+'</button>').join('');document.querySelectorAll('#candidate-nav button').forEach(b=>b.onclick=()=>{{pi=+b.dataset.i;render()}})}}function segments(d){{return '<div class="segments"><b>Operative segments</b>'+d.segments.map(s=>'<div class="segment"><code>'+esc(s.segment_id)+'</code> '+esc(s.text)+'</div>').join('')+'</div>'}}function ratings(name,value){{return '<div class="dimension"><b>'+name+'</b> '+['no','plausible','strong'].map(v=>'<button class="rate '+(value===v?'selected':'')+'" data-d="'+name.toLowerCase()+'" data-v="'+v+'">'+v+'</button>').join('')+'</div>'}}function render(){{nav();renderProgress();let x=DATA.children[ci];document.querySelector('#child-title').textContent=x.sample_id+' · '+label(x.child);document.querySelector('#definition').textContent=DATA.definition;if(!x.candidates.length){{document.querySelector('#content').innerHTML='<p>No candidates.</p>';return}}pi=Math.min(pi,x.candidates.length-1);let p=x.candidates[pi],s=pairState(x.child.document_id,p.document_id);document.querySelector('#content').innerHTML='<div class="compare">'+doc('Child',x.child)+doc('Candidate parent',p)+'</div><div class="decision">'+ratings('Policy',s.policy)+ratings('Mechanism',s.mechanism)+ratings('Overall',s.overall)+'<label>Evidence segment IDs (comma separated)<input id="evidence" value="'+esc(s.evidence_segment_ids)+'"></label><textarea id="notes" placeholder="Why is this—or is this not—an expected drafting precedent?">'+esc(s.notes)+'</textarea></div>';document.querySelectorAll('.rate').forEach(b=>b.onclick=()=>{{s[b.dataset.d]=b.dataset.v;save();render()}});document.querySelector('#evidence').oninput=e=>{{s.evidence_segment_ids=e.target.value;save()}};document.querySelector('#notes').oninput=e=>{{s.notes=e.target.value;save()}}}}function doc(role,d){{return '<article><div class="head"><h3>'+role+'</h3>'+esc(label(d))+'<div class="muted">'+esc(d.document_type.replaceAll('_',' ')+' · '+d.date+' · ID '+d.document_id)+'</div></div><div class="text">'+esc(d.text)+'</div>'+segments(d)+'</article>'}}document.querySelector('#reviewer').value=localStorage.getItem(KEY+'-reviewer')||'';document.querySelector('#reviewer').oninput=e=>localStorage.setItem(KEY+'-reviewer',e.target.value);document.querySelector('#export').onclick=()=>{{let judgments=[];DATA.children.forEach(x=>x.candidates.forEach(p=>judgments.push({{sample_id:x.sample_id,child_id:x.child.document_id,parent_id:p.document_id,...(state[x.child.document_id]?.[p.document_id]||{{}})}})));let out={{schema_version:2,reviewer:document.querySelector('#reviewer').value,exported_at:new Date().toISOString(),candidate_order:DATA.candidate_order,judgments}},blob=new Blob([JSON.stringify(out,null,2)],{{type:'application/json'}}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='parent-method-judgments.json';a.click();URL.revokeObjectURL(a.href)}};render();</script></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=Path("data/parent_analysis"))
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260810)
    args = parser.parse_args()
    with args.sample.open(newline="", encoding="utf-8") as handle:
        sampled = list(csv.DictReader(handle))
    candidate_path = args.candidates or args.input_dir / "hybrid_candidate_pool.csv"
    with candidate_path.open(newline="", encoding="utf-8") as handle:
        candidates = list(csv.DictReader(handle))
    payload = build_payload(
        sampled, candidates,
        read_jsonl(args.input_dir / "directive_similarity_documents.jsonl"),
        read_jsonl(args.input_dir / "directive_operative_segments.jsonl"), args.seed,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_html(payload), encoding="utf-8")
    print(f"wrote {args.output} with {len(payload['children'])} children")


if __name__ == "__main__":
    main()
