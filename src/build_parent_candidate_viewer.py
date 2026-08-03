#!/usr/bin/env python3
"""Build the 200-child parent-candidate pilot viewer."""

from __future__ import annotations

import argparse
import csv
import html
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from segmenter import _get_ordering_re


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "parent_analysis"
DEFAULT_OUTPUT = DEFAULT_INPUT / "pilot"
DEFAULT_HOLDOUT = ROOT / "data" / "holdout_ids.json"
SEED = 20260803
PER_TYPE = 50
TYPE_ORDER = ("executive_order", "memorandum", "proclamation", "letter")
TYPE_LABELS = {
    "executive_order": "Executive orders",
    "memorandum": "Memoranda",
    "proclamation": "Proclamations",
    "letter": "Letters",
}


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def select_sample(
    unresolved: list[dict], holdout_ids: set[str], seed: int = SEED,
    per_type: int = PER_TYPE,
) -> list[dict]:
    """Sample the same number of non-holdout unresolved children per type."""
    pools: dict[str, list[dict]] = defaultdict(list)
    for row in unresolved:
        if str(row["document_id"]) not in holdout_ids:
            pools[row["document_type"]].append(row)
    rng = random.Random(seed)
    selected: list[dict] = []
    for document_type in TYPE_ORDER:
        pool = sorted(pools[document_type], key=lambda row: int(row["document_id"]))
        if len(pool) < per_type:
            raise ValueError(f"{document_type} has only {len(pool)} eligible children")
        chosen = rng.sample(pool, per_type)
        rng.shuffle(chosen)
        selected.extend(chosen)
    return selected


def _candidate_rows(path: Path, sampled_ids: set[str]) -> dict[str, list[dict]]:
    candidates: dict[str, list[dict]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["child_id"] in sampled_ids and row["selected_top_10"].lower() == "true":
                candidates[row["child_id"]].append(row)
    for child_id, rows in candidates.items():
        rows.sort(key=lambda row: int(row["rrf_rank"]))
    return candidates


def _alignment_evidence(
    row: dict, segments: dict[str, list[dict]],
) -> list[dict]:
    child_segments = segments.get(row["child_id"], [])
    parent_segments = segments.get(row["parent_id"], [])
    evidence = []
    for child_index, parent_index, _score in json.loads(row["operative_alignments"]):
        if child_index >= len(child_segments) or parent_index >= len(parent_segments):
            raise ValueError(
                f"alignment index out of range for {row['child_id']} -> {row['parent_id']}"
            )
        child = child_segments[child_index]
        parent = parent_segments[parent_index]
        evidence.append({
            "child_segment_id": child["segment_id"],
            "parent_segment_id": parent["segment_id"],
            "child_text": child["text"],
            "parent_text": parent["text"],
            "child_ordering_spans": _ordering_spans(child["text"]),
            "parent_ordering_spans": _ordering_spans(parent["text"]),
        })
    return evidence


def build_payload(
    sampled: list[dict], documents: list[dict], segment_rows: list[dict],
    candidates: dict[str, list[dict]], seed: int = SEED,
    selections: dict[str, dict] | None = None, sample_prefix: str = "PC",
    viewer_title: str = "Parent candidate review", storage_namespace: str = "parent-candidate-pilot-v1",
    sample_design: str = "50 unresolved children per directive type",
) -> dict:
    """Create the self-contained browser payload."""
    selections = selections or {}
    documents_by_id = {str(row["document_id"]): row for row in documents}
    segments: dict[str, list[dict]] = defaultdict(list)
    for row in segment_rows:
        segments[str(row["document_id"])].append(row)
    for rows in segments.values():
        rows.sort(key=lambda row: int(row["segment_index"]))

    children = []
    for display_index, sample_row in enumerate(sampled, 1):
        child_id = str(sample_row["document_id"])
        child = documents_by_id[child_id]
        candidate_rows = sorted(
            candidates.get(child_id, []), key=lambda row: int(row["rrf_rank"])
        )
        displayed = []
        for candidate_row in candidate_rows:
            parent_id = candidate_row["parent_id"]
            parent = documents_by_id[parent_id]
            displayed.append({
                "parent": _document_payload(parent),
                "evidence": _alignment_evidence(candidate_row, segments),
                "scores": {
                    "document_embedding": _score_rank(
                        candidate_row, "document_embedding_score", "document_embedding_rank"
                    ),
                    "operative_embedding": _score_rank(
                        candidate_row, "operative_embedding_score", "operative_embedding_rank"
                    ),
                    "same_ordering_phrase": {
                        "score": (
                            candidate_row["same_ordering_phrase"].lower() == "true"
                            if candidate_row["same_ordering_phrase"] else None
                        ),
                        "rank": int(candidate_row["same_ordering_phrase_rank"])
                        if candidate_row["same_ordering_phrase_rank"] else None,
                    },
                    "word_trigram": _score_rank(
                        candidate_row, "segment_word_trigram_tfidf_score",
                        "segment_word_trigram_rank"
                    ),
                    "text_reuse": _score_rank(
                        candidate_row, "segment_text_reuse_words", "segment_text_reuse_rank"
                    ),
                    "rrf": {
                        "score": float(candidate_row["rrf_score"]),
                        "rank": int(candidate_row["rrf_rank"]),
                        "k": int(candidate_row["rrf_k"]),
                    },
                },
            })
        children.append({
            "sample_id": f"{sample_prefix}{display_index:03d}",
            "child": _document_payload(child),
            "candidates": displayed,
            "selection": selections.get(child_id),
        })
    return {
        "schema_version": 1,
        "seed": seed,
        "sample_design": sample_design,
        "candidate_order": "ascending fused RRF rank",
        "viewer_title": viewer_title,
        "storage_namespace": storage_namespace,
        "children": children,
    }


def _document_payload(row: dict) -> dict:
    text = row["cleaned_masked_text"]
    authorities = row.get("masked_authorities", [])
    revealed_text = _reveal_authorities(text, authorities)
    return {
        "document_id": str(row["document_id"]),
        "document_type": row["document_type"],
        "identifier": row.get("identifier", ""),
        "title": row.get("title", ""),
        "date": row.get("date", ""),
        "url": row.get("url", ""),
        "text": text,
        "revealed_text": revealed_text,
        "authorities": _unique_authorities(authorities),
        "ordering_spans": _ordering_spans(text),
        "revealed_ordering_spans": _ordering_spans(revealed_text),
    }


def _reveal_authorities(text: str, authorities: list[dict]) -> str:
    """Restore masked citations in encounter order for optional viewer display."""
    pieces = text.split("[AUTHORITY]")
    if len(pieces) - 1 != len(authorities):
        raise ValueError("masked authority count does not match [AUTHORITY] tokens")
    output = [pieces[0]]
    for authority, suffix in zip(authorities, pieces[1:]):
        output.extend((authority["text"], suffix))
    return "".join(output)


def _unique_authorities(authorities: list[dict]) -> list[dict]:
    """Deduplicate citations while retaining first-seen wording and type."""
    unique = []
    seen = set()
    for authority in authorities:
        key = " ".join(authority["text"].casefold().split())
        if key not in seen:
            seen.add(key)
            unique.append({"text": authority["text"], "kind": authority["kind"]})
    return unique


def _ordering_spans(text: str) -> list[list[int]]:
    return [[match.start(), match.end()] for match in _get_ordering_re(extended=True).finditer(text)]


def _score_rank(row: dict, score_field: str, rank_field: str) -> dict:
    return {
        "score": float(row[score_field]) if row[score_field] != "" else None,
        "rank": int(row[rank_field]) if row[rank_field] != "" else None,
    }


def _safe_json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def build_html(payload: dict) -> str:
    data = _safe_json(payload)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(payload.get("viewer_title", "Parent candidate review"))}</title>
<style>
:root{{--ink:#172033;--muted:#667085;--line:#d8dee9;--paper:#fff;--wash:#f4f7fb;--accent:#225ea8;--yes:#18794e;--no:#b42318}}
*{{box-sizing:border-box}} body{{margin:0;font:14px/1.45 system-ui,sans-serif;color:var(--ink);background:var(--wash)}}
button,input,textarea{{font:inherit}} button{{cursor:pointer}} .top{{position:sticky;top:0;z-index:5;display:flex;gap:12px;align-items:center;padding:10px 16px;background:#172033;color:#fff}}
.top h1{{font-size:18px;margin:0 auto 0 0}} .top input{{width:170px;padding:6px}} .top button{{padding:7px 11px;border:0;border-radius:5px}}
.layout{{display:grid;grid-template-columns:245px minmax(0,1fr);height:calc(100vh - 52px)}}
.sidebar{{overflow:auto;border-right:1px solid var(--line);background:#fff;padding:10px}} .type-title{{font-weight:750;margin:12px 5px 5px}}
.child-nav{{display:block;width:100%;text-align:left;border:0;border-radius:5px;background:transparent;padding:7px;color:var(--ink)}} .child-nav:hover,.child-nav.active{{background:#dbeafe}} .child-nav.done::after{{content:' ✓';color:var(--yes);font-weight:bold}}
.main{{overflow:auto;padding:16px}} .head-card,.decision,.doc{{background:#fff;border:1px solid var(--line);border-radius:8px}}
.head-card{{padding:12px;margin-bottom:12px}} h2{{margin:0 0 4px;font-size:19px}} .meta{{color:var(--muted)}} .candidate-tabs{{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}}
.candidate-tab{{border:1px solid var(--line);background:#fff;border-radius:6px;padding:6px 10px}} .candidate-tab.active{{color:#fff;background:var(--accent)}} .candidate-tab.yes{{border-color:var(--yes)}} .candidate-tab.no{{border-color:var(--no)}}
.score-toggle,.authority-toggle{{border:1px solid var(--accent);color:var(--accent);background:#fff;border-radius:6px;padding:6px 10px}} .score-toggle.active,.authority-toggle.active{{background:var(--accent);color:#fff}}
.scores{{display:none;margin-top:10px;padding-top:10px;border-top:1px solid var(--line)}} .scores.visible{{display:block}} .score-grid{{display:grid;grid-template-columns:repeat(3,minmax(150px,1fr));gap:8px}} .score-card{{background:var(--wash);border-radius:6px;padding:8px}} .score-value{{font-size:18px;font-weight:750}} .score-help{{font-size:12px;color:var(--muted)}}
.selection{{margin-top:10px;padding:10px;border-left:4px solid #7c3aed;background:#f5f3ff;border-radius:4px}} .selection blockquote{{margin:6px 0;font-family:Georgia,serif}} .selection-meta{{font-size:12px;color:var(--muted)}}
.compare{{display:grid;grid-template-columns:1fr 1fr;gap:12px}} .doc{{min-width:0}} .doc-head{{padding:10px 12px;border-bottom:1px solid var(--line)}} .doc-text{{white-space:pre-wrap;padding:14px;max-height:52vh;overflow:auto;font-family:Georgia,serif;font-size:15px;line-height:1.58}}
.authorities{{display:none;margin-top:8px;padding:9px;background:#fff8e6;border:1px solid #f0cf84;border-radius:6px}} .authorities.visible{{display:block}} .authorities ul{{margin:5px 0 0;padding-left:20px}} .authority-kind{{color:var(--muted);font-size:12px}}
mark.m0{{background:#fff2a8}} mark.m1{{background:#c9f1e5}} mark.m2{{background:#dbeafe}} .evidence{{grid-column:1/-1;background:#fff;border:1px solid var(--line);border-radius:8px;padding:12px}} .pair{{display:grid;grid-template-columns:1fr 1fr;gap:12px;border-top:1px solid var(--line);padding:10px 0}} .pair:first-of-type{{border:0}}
.decision{{padding:12px;margin-top:12px}} .choice{{border:1px solid var(--line);background:#fff;border-radius:6px;padding:7px 13px;margin-right:6px}} .choice.active.yes{{background:var(--yes);color:#fff}} .choice.active.no{{background:var(--no);color:#fff}} textarea{{display:block;width:100%;min-height:70px;margin-top:9px;padding:8px;border:1px solid var(--line);border-radius:5px}}
.none-row{{margin-top:12px;padding-top:10px;border-top:1px solid var(--line)}} .empty{{padding:30px;background:#fff;border:1px solid var(--line)}}
@media(max-width:900px){{.layout{{grid-template-columns:1fr;height:auto}}.sidebar{{max-height:220px;border-right:0}}.compare,.pair{{grid-template-columns:1fr}}.main{{overflow:visible}}}}
</style></head><body>
<div class="top"><h1>{html.escape(payload.get("viewer_title", "Parent candidate review"))}</h1><span id="progress"></span><label>Reviewer <input id="reviewer"></label><button id="export">Export JSON</button></div>
<div class="layout"><nav class="sidebar" id="sidebar"></nav><main class="main" id="main"></main></div>
<script>const DATA={data};
const STORE=DATA.storage_namespace+'-'+DATA.seed; const NAME=STORE+'-reviewer';
const SCORE_KEY=STORE+'-show-scores';
const AUTHORITY_KEY=STORE+'-show-authorities';
const sidebar=document.getElementById('sidebar'), main=document.getElementById('main');
const progress=document.getElementById('progress'), reviewer=document.getElementById('reviewer');
const exportButton=document.getElementById('export');
let state=JSON.parse(localStorage.getItem(STORE)||'{{}}'), ci=0, pi=0;
const esc=s=>String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const save=()=>{{localStorage.setItem(STORE,JSON.stringify(state));renderSidebar();renderProgress()}};
const childState=id=>state[id]||(state[id]={{candidates:{{}},none:false,explanation:''}});
function title(d){{return d.title||d.identifier||('Document '+d.document_id)}}
function meta(d){{return [d.document_type.replaceAll('_',' '),d.identifier,d.date,'ID '+d.document_id].filter(Boolean).join(' · ')}}
function fmt(v,n){{return v==null?'not available':Number(v).toFixed(n)}}
function scoreHtml(c){{let s=c.scores,shown=localStorage.getItem(SCORE_KEY)==='1';return '<button class="score-toggle '+(shown?'active':'')+'" id="score-toggle">'+(shown?'Hide':'Show')+' similarity scores</button><div class="scores '+(shown?'visible':'')+'"><div class="score-grid">'+
  scoreCard('Document embedding gate',fmt(s.document_embedding.score,3),'Gate rank '+s.document_embedding.rank+' of up to 25','Used only to create the candidate pool; excluded from RRF')+
  scoreCard('Operative embedding',fmt(s.operative_embedding.score,3),'Rank '+s.operative_embedding.rank+' of 25','Mean of three strongest segment alignments')+
  scoreCard('Same W&P phrase',s.same_ordering_phrase.score==null?'not available':(s.same_ordering_phrase.score?'Yes':'No'),s.same_ordering_phrase.rank==null?'Rank not available':'Rank '+s.same_ordering_phrase.rank+' of 25','Any operative segment pair shares the same normalized ordering phrase')+
  scoreCard('Segment 3-gram similarity',fmt(s.word_trigram.score,3),'Rank '+s.word_trigram.rank+' of 25','Mean of three strongest segment-pair TF-IDF cosine scores')+
  scoreCard('Segment text reuse',fmt(s.text_reuse.score,1)+' words','Rank '+s.text_reuse.rank+' of 25','Mean reused words across the three strongest segment pairs')+
  scoreCard('Fused result','Rank '+s.rrf.rank,fmt(s.rrf.score,4)+' RRF score','Unweighted rank fusion with k='+s.rrf.k)+
  '</div><p class="score-help">Segment-level scores are evidence, not probabilities that this candidate is a parent. Candidate tabs follow fused RRF rank.</p></div>'}}
function scoreCard(label,value,rank,help){{return '<div class="score-card"><b>'+label+'</b><div class="score-value">'+value+'</div><div>'+rank+'</div><div class="score-help">'+help+'</div></div>'}}
function authorityToggleHtml(){{let shown=localStorage.getItem(AUTHORITY_KEY)==='1';return '<button class="authority-toggle '+(shown?'active':'')+'" id="authority-toggle">'+(shown?'Mask':'Show')+' cited authorities in text</button>'}}
function authorityHtml(d){{let shown=localStorage.getItem(AUTHORITY_KEY)==='1',items=d.authorities||[];return '<div class="authorities '+(shown?'visible':'')+'"><b>Unique cited authorities</b>'+(items.length?'<ul>'+items.map(a=>'<li>'+esc(a.text)+' <span class="authority-kind">('+esc(a.kind.replaceAll('_',' '))+')</span></li>').join('')+'</ul>':'<p>No authority citations were identified by the masking rules.</p>')+'</div>'}}
function selectionHtml(x){{let s=x.selection;if(!s)return '';let model=s.model_code3?'dual-prompt Code 3':'rule-selected Code 3';return '<section class="selection"><b>Why this child was selected</b><div>'+esc(model)+' · policy: '+esc(s.selected_policy)+'</div><blockquote>'+esc(s.model_evidence||s.rule_excerpt||'')+'</blockquote><div class="selection-meta">Evidence segment: '+esc(s.evidence_segment_id||'not available')+' · minimum model P(Code 3): '+fmt(s.minimum_code3_probability,3)+' · rule: '+esc(s.rule_rationale||s.rule_category)+'</div></section>'}}
function highlighted(doc,evidence,side){{let revealed=localStorage.getItem(AUTHORITY_KEY)==='1',text=revealed?doc.revealed_text:doc.text,boldSpans=revealed?doc.revealed_ordering_spans:doc.ordering_spans,marks=[];evidence.forEach((e,i)=>{{let needle=e[side+'_text'];if(!needle)return;if(revealed&&needle.includes('[AUTHORITY]')){{let pattern=needle.split('[AUTHORITY]').map(regexEsc).join('.+?'),re=new RegExp(pattern,'g'),match;while((match=re.exec(text)))marks.push([match.index,match.index+match[0].length,i])}}else{{let start=0,pos;while((pos=text.indexOf(needle,start))>=0){{marks.push([pos,pos+needle.length,i]);start=pos+needle.length}}}}}});return styledText(text,boldSpans,marks)}}
function regexEsc(s){{return s.replace(/[.*+?^${{}}()|[\\]\\\\]/g,'\\\\$&')}}
function styledText(text,boldSpans,marks=[]){{
 let bounds=new Set([0,text.length]);boldSpans.forEach(s=>{{bounds.add(s[0]);bounds.add(s[1])}});marks.forEach(s=>{{bounds.add(s[0]);bounds.add(s[1])}});let points=Array.from(bounds).sort((a,b)=>a-b),out='';
 for(let i=0;i<points.length-1;i++){{let a=points[i],b=points[i+1],part=esc(text.slice(a,b)),bold=boldSpans.some(s=>s[0]<=a&&s[1]>=b),mark=marks.find(s=>s[0]<=a&&s[1]>=b);if(bold)part='<strong>'+part+'</strong>';if(mark)part='<mark class="m'+Math.min(mark[2],2)+'">'+part+'</mark>';out+=part}}return out
}}
function renderSidebar(){{
 let out='',last=''; DATA.children.forEach((x,i)=>{{let type=x.child.document_type;if(type!==last){{out+='<div class="type-title">'+esc(type.replaceAll('_',' '))+'</div>';last=type}}let s=state[x.child.document_id],done=s&&(s.none||Object.keys(s.candidates||{{}}).length===x.candidates.length)&&s.explanation?.trim();out+='<button class="child-nav '+(i===ci?'active ':'')+(done?'done':'')+'" data-i="'+i+'">'+esc(x.sample_id)+' · '+esc(title(x.child).slice(0,27))+'</button>'}}); sidebar.innerHTML=out;sidebar.querySelectorAll('button').forEach(b=>b.onclick=()=>{{ci=+b.dataset.i;pi=0;render()}})
}}
function renderProgress(){{let answered=0,total=0;DATA.children.forEach(x=>{{total+=x.candidates.length;let s=state[x.child.document_id];if(s)answered+=Object.keys(s.candidates||{{}}).length}});progress.textContent=answered+' / '+total+' pairs judged'}}
function render(){{renderSidebar();renderProgress();let x=DATA.children[ci],s=childState(x.child.document_id);if(!x.candidates.length){{main.innerHTML='<div class="empty"><h2>'+esc(x.sample_id)+' · '+esc(title(x.child))+'</h2><p>No eligible earlier candidate was available.</p>'+decisionHtml(x,s,null)+'</div>';wire(x,s,null);return}}pi=Math.min(pi,x.candidates.length-1);let c=x.candidates[pi],p=c.parent;
 let tabs=x.candidates.map((z,i)=>{{let v=s.candidates[z.parent.document_id];return '<button class="candidate-tab '+(i===pi?'active ':'')+(v||'')+'" data-p="'+i+'">Candidate '+(i+1)+'</button>'}}).join('');
 let pairs=c.evidence.map((e,i)=>'<div class="pair"><div><b>Child segment '+(i+1)+'</b><br>'+styledText(e.child_text,e.child_ordering_spans)+'</div><div><b>Candidate segment '+(i+1)+'</b><br>'+styledText(e.parent_text,e.parent_ordering_spans)+'</div></div>').join('')||'<p>No operative-segment alignment available.</p>';
 main.innerHTML='<section class="head-card"><h2>'+esc(x.sample_id)+' · '+esc(title(x.child))+'</h2><div class="meta">'+esc(meta(x.child))+'</div>'+selectionHtml(x)+'<div class="candidate-tabs">'+tabs+'</div>'+scoreHtml(c)+' '+authorityToggleHtml()+'</section><div class="compare"><article class="doc"><div class="doc-head"><b>Child</b><br>'+esc(title(x.child))+'<div class="meta">'+esc(meta(x.child))+'</div>'+authorityHtml(x.child)+'</div><div class="doc-text">'+highlighted(x.child,c.evidence,'child')+'</div></article><article class="doc"><div class="doc-head"><b>Candidate parent '+(pi+1)+'</b><br>'+esc(title(p))+'<div class="meta">'+esc(meta(p))+'</div>'+authorityHtml(p)+'</div><div class="doc-text">'+highlighted(p,c.evidence,'parent')+'</div></article><section class="evidence"><b>Strongest operative-segment matches</b>'+pairs+'</section></div>'+decisionHtml(x,s,p);
 main.querySelectorAll('.candidate-tab').forEach(b=>b.onclick=()=>{{pi=+b.dataset.p;render()}});document.getElementById('score-toggle').onclick=()=>{{let show=localStorage.getItem(SCORE_KEY)!=='1';localStorage.setItem(SCORE_KEY,show?'1':'0');render()}};document.getElementById('authority-toggle').onclick=()=>{{let show=localStorage.getItem(AUTHORITY_KEY)!=='1';localStorage.setItem(AUTHORITY_KEY,show?'1':'0');render()}};wire(x,s,p)
}}
function decisionHtml(x,s,p){{let v=p?(s.candidates[p.document_id]||''):'';return '<section class="decision">'+(p?'<b>Is this candidate a drafting parent?</b><div><button class="choice yes '+(v==='yes'?'active yes':'')+'" data-value="yes">Parent</button><button class="choice no '+(v==='no'?'active no':'')+'" data-value="no">Not parent</button></div>':'')+'<label class="none-row"><input type="checkbox" id="none" '+(s.none?'checked':'')+'> None of this child’s candidates is a parent</label><textarea id="explanation" placeholder="Brief explanation for the final parent selection or none decision">'+esc(s.explanation)+'</textarea></section>'}}
function wire(x,s,p){{document.querySelectorAll('.choice').forEach(b=>b.onclick=()=>{{s.candidates[p.document_id]=b.dataset.value;if(b.dataset.value==='yes')s.none=false;save();render()}});let n=document.getElementById('none');n.onchange=()=>{{s.none=n.checked;if(s.none)Object.keys(s.candidates).forEach(k=>s.candidates[k]='no');save();render()}};let t=document.getElementById('explanation');t.oninput=()=>{{s.explanation=t.value;save()}}}}
reviewer.value=localStorage.getItem(NAME)||'';reviewer.oninput=()=>localStorage.setItem(NAME,reviewer.value);
exportButton.onclick=()=>{{let judgments=DATA.children.map(x=>{{let s=state[x.child.document_id]||{{candidates:{{}},none:false,explanation:''}};return {{sample_id:x.sample_id,child_id:x.child.document_id,document_type:x.child.document_type,selection:x.selection,none:s.none,explanation:s.explanation,candidates:x.candidates.map(c=>({{parent_id:c.parent.document_id,decision:s.candidates[c.parent.document_id]||'not_reviewed',alignment_segment_ids:c.evidence.map(e=>[e.child_segment_id,e.parent_segment_id])}}))}}}});let out={{schema_version:1,reviewer:reviewer.value.trim(),exported_at:new Date().toISOString(),sample:{{seed:DATA.seed,sample_design:DATA.sample_design,candidate_order:DATA.candidate_order}},judgments}};let blob=new Blob([JSON.stringify(out,null,2)],{{type:'application/json'}}),a=document.createElement('a'),name=(reviewer.value.trim()||'unknown').replace(/\\s+/g,'_').toLowerCase();a.href=URL.createObjectURL(blob);a.download=DATA.storage_namespace+'-'+name+'-'+new Date().toISOString().slice(0,10)+'.json';a.click();URL.revokeObjectURL(a.href)}};
render();</script></body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--holdout-ids", type=Path, default=DEFAULT_HOLDOUT)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--per-type", type=int, default=PER_TYPE)
    args = parser.parse_args()

    with (args.input_dir / "unresolved_children.csv").open(newline="", encoding="utf-8") as handle:
        unresolved = list(csv.DictReader(handle))
    holdout_ids = {str(value) for value in json.loads(args.holdout_ids.read_text())}
    sampled = select_sample(unresolved, holdout_ids, args.seed, args.per_type)
    sampled_ids = {str(row["document_id"]) for row in sampled}
    candidates = _candidate_rows(args.input_dir / "ranked_candidates.csv", sampled_ids)
    documents = read_jsonl(args.input_dir / "directive_similarity_documents.jsonl")
    segments = read_jsonl(args.input_dir / "directive_operative_segments.jsonl")
    payload = build_payload(sampled, documents, segments, candidates, args.seed)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    viewer_path = args.output_dir / "parent_candidate_viewer.html"
    manifest_path = args.output_dir / "sample_manifest.json"
    sample_path = args.output_dir / "sampled_children.csv"
    viewer_path.write_text(build_html(payload), encoding="utf-8")
    manifest = {
        "seed": args.seed,
        "per_type": args.per_type,
        "sample_size": len(sampled),
        "sample_counts_by_type": dict(Counter(row["document_type"] for row in sampled)),
        "holdout_count": len(holdout_ids),
        "sampled_holdout_overlap": sorted(sampled_ids & holdout_ids),
        "candidate_comparisons": sum(len(row["candidates"]) for row in payload["children"]),
        "candidate_order": payload["candidate_order"],
        "inputs": {
            "unresolved_children": "data/parent_analysis/unresolved_children.csv",
            "ranked_candidates": "data/parent_analysis/ranked_candidates.csv",
            "documents": "data/parent_analysis/directive_similarity_documents.jsonl",
            "segments": "data/parent_analysis/directive_operative_segments.jsonl",
            "holdout_ids": "data/holdout_ids.json",
        },
        "sampled_ids": [str(row["document_id"]) for row in sampled],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    with sample_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(sampled[0]))
        writer.writeheader(); writer.writerows(sampled)
    print(f"Wrote {viewer_path} ({len(sampled)} children, {manifest['candidate_comparisons']} comparisons)")
    print(f"Wrote {manifest_path}")
    print(f"Wrote {sample_path}")


if __name__ == "__main__":
    main()
