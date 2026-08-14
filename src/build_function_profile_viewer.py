#!/usr/bin/env python3
"""Build a local source-vs-Gemini function-profile comparison viewer."""
from __future__ import annotations
import argparse, html, json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCUMENTS = ROOT / "data/parent_analysis_full/directive_similarity_documents.jsonl"
DEFAULT_SEGMENTS = ROOT / "data/parent_analysis_full/directive_operative_segments.jsonl"
DEFAULT_OUTPUT = ROOT / "data/parent_analysis/function_profile_pilot/function_profile_viewer.html"

def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]

def build_payload(profiles, responses, documents, segments, errors=None):
    docs = {str(x["document_id"]): x for x in documents}
    segs: dict[str, list[dict]] = {}
    for x in segments:
        segs.setdefault(str(x["document_id"]), []).append(x)
    for values in segs.values():
        values.sort(key=lambda x: int(x["segment_index"]))
    response_map = {}
    for x in responses:
        response_map.setdefault(str(x["request_id"]), x)
    profile_map = {str(x.get("request_id")): x for x in profiles}
    items = []
    envelopes = list(profiles)
    # Keep response records that failed validation in the viewer as well.  They
    # have empty validated function lists, but their source, raw JSON, and
    # audit errors remain available for review instead of being discarded.
    for response in responses:
        request_id = str(response.get("request_id"))
        if request_id in profile_map:
            continue
        metadata = response.get("metadata", {})
        doc_id = str(metadata.get("document_id", ""))
        if doc_id in docs:
            envelopes.append({"request_id": request_id, "document_id": doc_id,
                              "profile": {"policy_functions": [], "operative_functions": []}})
    for envelope in envelopes:
        profile, doc_id = envelope["profile"], str(envelope["document_id"])
        doc, response = docs[doc_id], response_map.get(str(envelope.get("request_id")), {})
        items.append({
            "document_id": doc_id, "document_type": doc["document_type"],
            "identifier": doc.get("identifier", ""), "title": doc.get("title", ""),
            "date": doc.get("date", ""), "url": doc.get("url", ""),
            "source_text": doc["cleaned_masked_text"],
            "segments": [{"segment_id": x["segment_id"], "segment_index": x["segment_index"], "text": x["text"]}
                         for x in segs.get(doc_id, [])],
            "policy_functions": profile["policy_functions"],
            "operative_functions": profile["operative_functions"],
            "request_id": envelope.get("request_id", ""),
            "model": envelope.get("model") or response.get("model", ""),
            "model_version": envelope.get("model_version") or response.get("model_version", ""),
            "grounding_metadata": response.get("grounding_metadata"),
            "raw_response": response.get("text", ""),
        })
    items.sort(key=lambda x: (x["document_type"], x["date"], x["document_id"]))
    return {"schema_version": 1, "viewer_title": "Directive functions — source vs Gemini Flash",
            "storage_namespace": "function-profile-pilot-v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "authority_policy": "Source text is authority-masked; preserved authority tables are not included.",
            "audit_errors": errors or [], "documents": items}

def build_html(payload):
    title = html.escape(payload["viewer_title"])
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    template = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__</title>
<style>
body{margin:0;background:#f4f7fb;color:#172033;font:14px/1.45 system-ui,sans-serif}button,input{font:inherit}.top{position:sticky;top:0;z-index:2;background:#172033;color:white;padding:10px 16px;display:flex;gap:10px;align-items:center}.top h1{margin:0 auto 0 0;font-size:18px}.top input{width:220px;padding:6px}.top button,.nav{cursor:pointer;padding:7px 10px;border:0;border-radius:5px}.layout{display:grid;grid-template-columns:260px 1fr;min-height:calc(100vh - 52px)}.sidebar{background:white;border-right:1px solid #d8dee9;padding:10px}.nav{display:block;width:100%;text-align:left;background:transparent;color:#172033}.nav:hover,.nav.active{background:#dbeafe}.nav small,.muted{display:block;color:#667085}.main{padding:18px;max-width:1500px}.card,.source,.section,.function,.audit{background:white;border:1px solid #d8dee9;border-radius:8px;padding:12px;margin-bottom:12px}.badge{display:inline-block;padding:3px 8px;border-radius:99px;background:#e6f4ea;color:#176b3a;font-size:12px;margin:5px 4px 0 0}.warn{background:#fff8e6;color:#8a5a00}.source-text,.segment-text{white-space:pre-wrap;overflow:auto;max-height:45vh;padding:10px;background:#fbfcfe;border:1px solid #d8dee9;font:15px/1.58 Georgia,serif}.source-text mark.policy{background:#fff0a6}.segment-text mark.operative{background:#b9efd9}.columns{display:grid;grid-template-columns:1fr 1fr;gap:12px}.function{padding:10px;margin:8px 0}.function h4{margin:0;color:#225ea8}.fields{display:grid;grid-template-columns:115px 1fr;gap:3px 8px}.fields dt{color:#667085;font-size:12px}.fields dd{margin:0}.evidence{border-left:3px solid #225ea8;background:#f6f8fc;padding:7px;margin-top:7px;font-family:Georgia,serif}.segment{border-top:1px solid #d8dee9;margin-top:12px;padding-top:8px}.raw pre{white-space:pre-wrap;max-height:350px;overflow:auto;background:#172033;color:#eef4ff;padding:10px;font-size:12px}@media(max-width:900px){.layout{grid-template-columns:1fr}.sidebar{max-height:230px;border:0}.columns{grid-template-columns:1fr}}
</style></head><body><header class="top"><h1>__TITLE__</h1><span id="count"></span><input id="search" placeholder="Filter directives"><button id="prev">Previous</button><button id="next">Next</button></header><div class="layout"><nav class="sidebar" id="sidebar"></nav><main class="main" id="main"></main></div>
<script>
const DATA=%%DATA%%,sidebar=document.getElementById('sidebar'),main=document.getElementById('main');let index=0;
const esc=s=>String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const title=d=>d.title||d.identifier||('Document '+d.document_id),meta=d=>[d.document_type.replaceAll('_',' '),d.identifier,d.date,'ID '+d.document_id].filter(Boolean).join(' · ');
function highlight(text,fs,cls){let rs=[];for(const f of fs){let n=f.evidence||'',p=0,i;if(!n)continue;while((i=text.indexOf(n,p))>=0){rs.push([i,i+n.length,cls]);p=i+n.length}}let points=new Set([0,text.length]);rs.forEach(x=>{points.add(x[0]);points.add(x[1])});let q=[...points].sort((a,b)=>a-b),out='';for(let i=0;i<q.length-1;i++){let a=q[i],b=q[i+1],m=rs.find(x=>x[0]<=a&&x[1]>=b);out+=(m?'<mark class="'+m[2]+'">':'')+esc(text.slice(a,b))+(m?'</mark>':'')}return out}
function field(k,v){return v?'<dt>'+esc(k)+'</dt><dd>'+esc(v)+'</dd>':''}
function card(f,k){return '<article class="function"><h4>'+esc(f.function_id)+' · '+esc(f.label)+'</h4><dl class="fields">'+field('Actor',f.actor)+field('Action',f.action)+field('Target',f.target)+field('Mechanism',f.mechanism)+field('Effect',f.effect)+field('Condition',f.condition)+field('Timing',f.timing)+field('Confidence',f.confidence)+'</dl><div class="evidence"><b>'+esc(k)+' evidence</b><br>'+esc(f.evidence||'')+'<br><span class="muted">offsets '+esc(f.evidence_start)+'–'+esc(f.evidence_end)+'</span></div></article>'}
function sidebarRender(){let q=document.getElementById('search').value.toLowerCase(),out='';DATA.documents.forEach((d,i)=>{let hay=String(d.document_id)+' '+d.title+' '+d.document_type;if(q&&!hay.toLowerCase().includes(q))return;out+='<button class="nav '+(i===index?'active':'')+'" data-i="'+i+'">'+esc(d.document_type.replaceAll('_',' '))+' · '+esc(title(d))+'<small>'+esc(d.date)+' · '+d.policy_functions.length+' policy · '+d.operative_functions.length+' operative</small></button>'});sidebar.innerHTML=out;sidebar.querySelectorAll('.nav').forEach(b=>b.onclick=()=>{index=+b.dataset.i;render()});document.getElementById('count').textContent=(index+1)+' / '+DATA.documents.length}
function render(){sidebarRender();let d=DATA.documents[index];if(!d){main.innerHTML='<div class="card">No matching directives.</div>';return}let warning=DATA.audit_errors.filter(e=>String(e.request_id||'').includes(d.request_id));let segs=d.segments.map(s=>{let fs=d.operative_functions.filter(f=>f.segment_id===s.segment_id);return '<div class="segment"><h4>'+esc(s.segment_id)+' · '+fs.length+' functions</h4><div class="segment-text">'+highlight(s.text,fs,'operative')+'</div>'+fs.map(f=>card(f,'Operative')).join('')+'</div>'}).join('');let ground=d.grounding_metadata?JSON.stringify(d.grounding_metadata,null,2):'No Google Search grounding metadata was returned.';main.innerHTML='<section class="card"><h2>'+esc(title(d))+'</h2><div class="muted">'+esc(meta(d))+'</div><span class="badge">Authority-masked source</span><span class="badge">'+esc(d.model||'Gemini')+' · '+esc(d.model_version||'')+'</span><span class="badge '+(d.grounding_metadata?'':'warn')+'">'+(d.grounding_metadata?'Search grounding used':'Search grounding not invoked')+'</span></section>'+(warning.length?'<section class="audit warn"><b>Audit warning</b><ul>'+warning.map(e=>(e.errors||[]).map(x=>'<li>'+esc(x)+'</li>').join('')).join('')+'</ul></section>':'')+'<section class="source"><h3>Initial directive supplied to Flash</h3><div class="muted">'+esc(DATA.authority_policy)+'</div><div class="source-text">'+highlight(d.source_text,d.policy_functions,'policy')+'</div></section><div class="columns"><section class="section"><h3>Policy functions ('+d.policy_functions.length+')</h3>'+(d.policy_functions.length?d.policy_functions.map(f=>card(f,'Policy')).join(''):'<p class="muted">None returned.</p>')+'</section><section class="section"><h3>Operative functions ('+d.operative_functions.length+')</h3>'+(segs||'<p class="muted">No operative segments.</p>')+'</section></div><section class="card raw"><details><summary>Raw validated Flash JSON</summary><pre>'+esc(d.raw_response)+'</pre></details><details><summary>Grounding metadata</summary><pre>'+esc(ground)+'</pre></details></section>'}
document.getElementById('prev').onclick=()=>{index=(index+DATA.documents.length-1)%DATA.documents.length;render()};document.getElementById('next').onclick=()=>{index=(index+1)%DATA.documents.length;render()};document.getElementById('search').oninput=render;render();
</script></body></html>'''
    return template.replace("__TITLE__", title).replace("%%DATA%%", data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", type=Path, required=True)
    parser.add_argument("--responses", type=Path, required=True)
    parser.add_argument("--documents", type=Path, default=DEFAULT_DOCUMENTS)
    parser.add_argument("--segments", type=Path, default=DEFAULT_SEGMENTS)
    parser.add_argument("--errors", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    errors = read_jsonl(args.errors) if args.errors and args.errors.exists() else []
    payload = build_payload(read_jsonl(args.profiles), read_jsonl(args.responses), read_jsonl(args.documents), read_jsonl(args.segments), errors)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_html(payload), encoding="utf-8")
    total = sum(len(x["policy_functions"]) + len(x["operative_functions"]) for x in payload["documents"])
    print(json.dumps({"output": str(args.output), "documents": len(payload["documents"]), "functions": total}, sort_keys=True))


if __name__ == "__main__":
    main()
