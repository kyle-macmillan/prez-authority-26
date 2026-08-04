"""Build a standalone HTML report of IEEPA directives and candidate similarities."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IEEPA_RE = re.compile(r"\bIEEPA\b|International Emergency Economic Powers Act", re.I)
BAND_ORDER = ("at_least_0.9", "0.8_to_under_0.9", "0.7_to_under_0.8", "under_0.7", "missing")
BAND_LABELS = {
    "at_least_0.9": "≥0.9", "0.8_to_under_0.9": "0.8–<0.9",
    "0.7_to_under_0.8": "0.7–<0.8", "under_0.7": "<0.7", "missing": "Missing",
    "not_applicable_automatic_parent": "Automatic parent — not ranked",
}


def is_ieepa(text: str) -> bool:
    return bool(IEEPA_RE.search(text))


def score_band(value: str | float | None) -> str:
    if value in (None, ""):
        return "missing"
    score = float(value)
    if score >= .9:
        return "at_least_0.9"
    if score >= .8:
        return "0.8_to_under_0.9"
    if score >= .7:
        return "0.7_to_under_0.8"
    return "under_0.7"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def stratified_examples(rows: list[dict], predicate, limit: int = 2) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        if predicate(row):
            digest = hashlib.sha256(f"ieepa:{row['document_id']}".encode()).hexdigest()
            groups[row["document_type"]].append((digest, row))
    return [row for kind in sorted(groups) for _, row in sorted(groups[kind])[:limit]]


def build_analysis(corpora: list[Path], ranked_path: Path, automatic_path: Path,
                   documents_path: Path, segments_path: Path) -> tuple[list[dict], dict]:
    corpus = {}
    for partition, path in (("development", corpora[0]), ("holdout", corpora[1])):
        for row in read_csv(path):
            if is_ieepa(row["doc_text"]):
                corpus[row[""]] = {**row, "partition": partition}
    documents = {row["document_id"]: row for row in read_jsonl(documents_path)}
    segments = defaultdict(list)
    for segment in read_jsonl(segments_path):
        segments[segment["document_id"]].append(segment)
    automatic = defaultdict(list)
    for edge in read_csv(automatic_path):
        if edge["child_id"] in corpus:
            automatic[edge["child_id"]].append(edge)
    candidates = defaultdict(dict)
    for row in read_csv(ranked_path):
        if row["child_id"] in corpus and int(row["rrf_rank"]) in (1, 2):
            candidates[row["child_id"]][int(row["rrf_rank"])] = row

    output = []
    for document_id in sorted(corpus, key=int):
        meta = documents[document_id]
        item = {
            "document_id": document_id, "document_type": meta["document_type"],
            "title": meta["title"], "date": meta["date"], "url": meta["url"],
            "partition": corpus[document_id]["partition"],
            "operative_segment_count": len(segments[document_id]),
            "status": "automatic_parent" if document_id in automatic else "ranked",
            "automatic_parents": [{k: edge[k] for k in ("parent_id", "parent_identifier", "parent_date", "relation")} for edge in automatic[document_id]],
        }
        for rank in (1, 2):
            candidate = candidates[document_id].get(rank)
            if item["status"] == "automatic_parent":
                item[f"candidate_{rank}"] = {"band": "not_applicable_automatic_parent"}
                continue
            if candidate is None:
                item[f"candidate_{rank}"] = {"band": "missing", "reason": "candidate unavailable"}
                continue
            parent = documents[candidate["parent_id"]]
            score = candidate["operative_embedding_score"]
            alignments = json.loads(candidate["operative_alignments"])
            evidence = []
            for child_index, parent_index, similarity in alignments:
                evidence.append({"child": segments[document_id][child_index]["text"],
                                 "parent": segments[candidate["parent_id"]][parent_index]["text"],
                                 "similarity": similarity})
            reason = ""
            if score == "":
                missing = []
                if not segments[document_id]: missing.append("child")
                if not segments[candidate["parent_id"]]: missing.append("parent")
                reason = " and ".join(missing) + " has no extracted operative provisions"
            item[f"candidate_{rank}"] = {
                "parent_id": candidate["parent_id"], "title": parent["title"],
                "date": parent["date"], "url": parent["url"],
                "score": None if score == "" else float(score), "band": score_band(score),
                "parent_segment_count": len(segments[candidate["parent_id"]]),
                "reason": reason, "evidence": evidence,
            }
        output.append(item)
    ranked = [row for row in output if row["status"] == "ranked"]
    summary = {
        "total": len(output), "ranked": len(ranked), "automatic": len(output) - len(ranked),
        "types": dict(sorted(Counter(row["document_type"] for row in output).items())),
        "candidates": {str(rank): dict(Counter(row[f"candidate_{rank}"]["band"] for row in ranked)) for rank in (1, 2)},
        "missing_types": {str(rank): dict(sorted(Counter(
            row["document_type"] for row in ranked if row[f"candidate_{rank}"]["band"] == "missing"
        ).items())) for rank in (1, 2)},
    }
    return output, summary


def build_html(rows: list[dict], summary: dict) -> str:
    low = stratified_examples(rows, lambda r: r["status"] == "ranked" and any(r[f"candidate_{n}"]["band"] == "under_0.7" for n in (1, 2)))
    missing = stratified_examples(rows, lambda r: r["status"] == "ranked" and any(r[f"candidate_{n}"]["band"] == "missing" for n in (1, 2)))
    data = json.dumps(rows, separators=(",", ":")).replace("</", "<\\/")
    labels = json.dumps(BAND_LABELS)
    def count_cell(rank, band):
        count = summary["candidates"][str(rank)].get(band, 0)
        return f"{count:,} ({count / summary['ranked']:.1%})"
    counts = "".join(f"<tr><th>{BAND_LABELS[b]}</th><td>{count_cell(1,b)}</td><td>{count_cell(2,b)}</td></tr>" for b in BAND_ORDER)
    def cards(items):
        return "".join(f'<article class="example" data-id="{r["document_id"]}"></article>' for r in items)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>IEEPA candidate similarity</title>
<style>body{{font:15px system-ui;margin:0;background:#f5f7fa;color:#172033}}main{{max-width:1400px;margin:auto;padding:28px}}h1,h2{{color:#102a43}}.cards{{display:flex;gap:14px;flex-wrap:wrap}}.stat,.example{{background:white;border:1px solid #d9e2ec;border-radius:10px;padding:16px}}.stat strong{{font-size:26px;display:block}}table{{width:100%;border-collapse:collapse;background:white}}th,td{{padding:9px;border-bottom:1px solid #e5e7eb;text-align:left;vertical-align:top}}nav button{{padding:10px 14px;margin:0 5px 12px 0}}.view[hidden]{{display:none}}input,select{{padding:8px;margin:0 8px 12px 0}}.examples{{display:grid;gap:14px}}.pair{{border-top:1px solid #ddd;padding-top:8px;margin-top:8px}}.evidence{{font-size:13px;background:#f7fafc;padding:8px}}a{{color:#075985}}.badge{{padding:2px 6px;border-radius:10px;background:#e0f2fe;white-space:nowrap}}</style></head><body><main>
<h1>IEEPA candidate similarity</h1><p>Directives explicitly mentioning “IEEPA” or “International Emergency Economic Powers Act.” Candidate scores are all-pairs mean operative-provision cosine similarities.</p>
<div class="cards"><div class="stat"><strong>{summary['total']:,}</strong>IEEPA directives</div><div class="stat"><strong>{summary['ranked']:,}</strong>ranked children</div><div class="stat"><strong>{summary['automatic']:,}</strong>automatic-parent directives</div></div>
<nav><button data-view="overview">Overview</button><button data-view="all">All directives</button><button data-view="low">Below 0.7 examples</button><button data-view="missing">Missing-score examples</button></nav>
<section class="view" id="overview"><h2>Range counts</h2><table><thead><tr><th>Range</th><th>Candidate 1</th><th>Candidate 2</th></tr></thead><tbody>{counts}</tbody></table><h2>Directive types</h2><p>{html.escape(', '.join(f'{k.replace("_"," ")}: {v:,}' for k,v in summary['types'].items()))}</p><p>Percentages use {summary['ranked']:,} ranked IEEPA children as the denominator. Missing scores are separate from valid scores below 0.7.</p></section>
<section class="view" id="all" hidden><h2>All IEEPA directives</h2><input id="search" placeholder="Search title or ID"><select id="status"><option value="">All statuses</option><option value="ranked">Ranked</option><option value="automatic_parent">Automatic parent</option></select><select id="band"><option value="">All ranges</option>{''.join(f'<option value="{b}">{BAND_LABELS[b]}</option>' for b in BAND_ORDER)}</select><table><thead><tr><th>Directive</th><th>Type/date</th><th>Status</th><th>Candidate 1</th><th>Candidate 2</th></tr></thead><tbody id="inventory"></tbody></table></section>
<section class="view" id="low" hidden><h2>Examples below 0.7</h2><p>Up to two deterministic examples per available document type.</p><div class="examples">{cards(low)}</div></section>
<section class="view" id="missing" hidden><h2>Missing-score examples</h2><p>Missing means the child or candidate parent has no extracted operative provisions. Candidate 1: {html.escape(', '.join(f'{k.replace("_"," ")}: {v}' for k,v in summary['missing_types']['1'].items()))}. Candidate 2: {html.escape(', '.join(f'{k.replace("_"," ")}: {v}' for k,v in summary['missing_types']['2'].items()))}.</p><div class="examples">{cards(missing)}</div></section>
<script>const ROWS={data},LABELS={labels};const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const link=x=>'<a target="_blank" rel="noopener" href="'+esc(x.url)+'">'+esc(x.title||('ID '+x.document_id))+'</a>';const cand=c=>c.band==='not_applicable_automatic_parent'?LABELS[c.band]:(c.parent_id?link(c)+'<br><span class="badge">'+LABELS[c.band]+(c.score==null?'':' · '+c.score.toFixed(3))+'</span>'+(c.reason?'<br>'+esc(c.reason):''):'Unavailable');
function renderTable(){{let q=document.querySelector('#search').value.toLowerCase(),s=document.querySelector('#status').value,b=document.querySelector('#band').value;document.querySelector('#inventory').innerHTML=ROWS.filter(r=>(!q||(r.title+' '+r.document_id).toLowerCase().includes(q))&&(!s||r.status===s)&&(!b||r.candidate_1.band===b||r.candidate_2.band===b)).map(r=>'<tr><td>'+link(r)+'<br>ID '+r.document_id+'</td><td>'+esc(r.document_type.replace(/_/g,' '))+'<br>'+esc(r.date)+'</td><td>'+esc(r.status.replace(/_/g,' '))+(r.automatic_parents.length?'<br>'+r.automatic_parents.map(x=>'Parent ID '+esc(x.parent_id)).join(', '):'')+'</td><td>'+cand(r.candidate_1)+'</td><td>'+cand(r.candidate_2)+'</td></tr>').join('')}}
function renderExample(el){{let r=ROWS.find(x=>x.document_id===el.dataset.id);el.innerHTML='<h3>'+link(r)+'</h3><p>'+esc(r.document_type.replace(/_/g,' '))+' · '+esc(r.date)+' · ID '+r.document_id+' · child operative provisions: '+r.operative_segment_count+'</p>'+[1,2].map(n=>{{let c=r['candidate_'+n];return '<div class="pair"><strong>Candidate '+n+':</strong> '+cand(c)+(c.parent_id?'<br>Parent operative provisions: '+c.parent_segment_count:'')+(c.evidence&&c.evidence.length?'<details><summary>Strongest illustrative operative pairs</summary>'+c.evidence.map(e=>'<div class="evidence"><b>Child:</b> '+esc(e.child)+'<br><b>Parent:</b> '+esc(e.parent)+'<br>Pair similarity: '+e.similarity.toFixed(3)+'</div>').join('')+'</details>':'')+'</div>'}}).join('')}}
document.querySelectorAll('.example').forEach(renderExample);document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>document.querySelectorAll('.view').forEach(v=>v.hidden=v.id!==b.dataset.view));document.querySelectorAll('#search,#status,#band').forEach(x=>x.oninput=renderTable);renderTable();</script></main></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "data/parent_analysis/ieepa_similarity/ieepa_candidate_similarity.html")
    args = parser.parse_args()
    rows, summary = build_analysis(
        [ROOT / "data/4_28_2026_build_dev.csv", ROOT / "data/4_28_2026_build_holdout.csv"],
        ROOT / "data/parent_analysis/ranked_candidates.csv", ROOT / "data/parent_analysis/automatic_edges.csv",
        ROOT / "data/parent_analysis/directive_similarity_documents.jsonl", ROOT / "data/parent_analysis/directive_operative_segments.jsonl")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_html(rows, summary), encoding="utf-8")
    print(json.dumps(summary, indent=2)); print(args.output)


if __name__ == "__main__":
    main()
