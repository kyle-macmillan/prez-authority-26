"""Build a standalone comparison of RRF and two Qwen reranking representations."""

from __future__ import annotations

import argparse
import csv
import html
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def summarize(rows: list[dict[str, str]]) -> dict:
    by_child = defaultdict(list)
    for row in rows:
        by_child[row["child_id"]].append(row)
    tops = {}
    for child_id, candidates in by_child.items():
        tops[child_id] = {
            field: min(candidates, key=lambda row: int(row[field]))["parent_id"]
            for field in ("rrf_rank", "qwen_full_operative_rank", "qwen_matched_pairs_rank")
        }
    return {
        "children": len(by_child), "pairs": len(rows),
        "full_matched_agreement": sum(x["qwen_full_operative_rank"] == x["qwen_matched_pairs_rank"] for x in tops.values()),
        "full_rrf_agreement": sum(x["qwen_full_operative_rank"] == x["rrf_rank"] for x in tops.values()),
        "matched_rrf_agreement": sum(x["qwen_matched_pairs_rank"] == x["rrf_rank"] for x in tops.values()),
    }


def build_html(rows: list[dict[str, str]], documents: dict[str, dict]) -> str:
    summary = summarize(rows)
    payload = []
    for row in rows:
        payload.append({
            "child_id": row["child_id"], "parent_id": row["parent_id"],
            "child": documents[row["child_id"]], "parent": documents[row["parent_id"]],
            "bidir": float(row["operative_embedding_score"]), "rrf": int(row["rrf_rank"]),
            "full_score": float(row["qwen_full_operative_score"]),
            "full_rank": int(row["qwen_full_operative_rank"]),
            "matched_score": float(row["qwen_matched_pairs_score"]),
            "matched_rank": int(row["qwen_matched_pairs_rank"]),
            "alignments": json.loads(row["operative_alignments"]),
        })
    data = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    pct = lambda value: f"{value / summary['children']:.1%}" if summary["children"] else "—"
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Qwen reranker comparison</title><style>
body{{font:15px system-ui;background:#f5f7fa;color:#172033;margin:0}}main{{max-width:1400px;margin:auto;padding:28px}}.stats{{display:flex;gap:12px;flex-wrap:wrap}}.stat,article{{background:white;border:1px solid #d8e1eb;border-radius:9px;padding:14px}}.stat strong{{font-size:25px;display:block}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:8px;border-bottom:1px solid #ddd}}input{{padding:9px;width:320px}}a{{color:#075985}}.winner{{background:#dcfce7}}small{{color:#52606d}}</style></head><body><main>
<h1>Qwen top-10 reranker comparison</h1><p>Both rerankers use: <em>Rank the earlier presidential directives according to whether they have a similar function, directive, or operative instruction to the later directive.</em></p>
<div class="stats"><div class="stat"><strong>{summary['children']}</strong>children</div><div class="stat"><strong>{summary['pairs']}</strong>candidate pairs</div><div class="stat"><strong>{pct(summary['full_matched_agreement'])}</strong>full/matched top-1 agreement</div><div class="stat"><strong>{pct(summary['full_rrf_agreement'])}</strong>full/RRF agreement</div><div class="stat"><strong>{pct(summary['matched_rrf_agreement'])}</strong>matched/RRF agreement</div></div>
<p><input id="search" placeholder="Search child title or ID"></p><div id="children"></div>
<script>const DATA={data};const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));const link=d=>'<a target="_blank" rel="noopener" href="'+esc(d.url)+'">'+esc(d.title)+'</a>';function render(){{let q=document.querySelector('#search').value.toLowerCase(),groups={{}};DATA.forEach(x=>(groups[x.child_id]||(groups[x.child_id]=[])).push(x));document.querySelector('#children').innerHTML=Object.values(groups).filter(g=>!q||(g[0].child.title+' '+g[0].child_id).toLowerCase().includes(q)).map(g=>{{g.sort((a,b)=>a.rrf-b.rrf);let top=[g.find(x=>x.rrf===1).parent_id,g.find(x=>x.full_rank===1).parent_id,g.find(x=>x.matched_rank===1).parent_id];return '<article><h2>'+link(g[0].child)+' <small>ID '+g[0].child_id+'</small></h2><p>Top 1 — RRF: '+top[0]+' · Full operative: '+top[1]+' · Matched pairs: '+top[2]+'</p><table><thead><tr><th>Earlier candidate</th><th>Bidirectional</th><th>RRF</th><th>Qwen full</th><th>Qwen matched</th></tr></thead><tbody>'+g.map(x=>'<tr><td>'+link(x.parent)+'<br><small>ID '+x.parent_id+'</small></td><td>'+x.bidir.toFixed(3)+'</td><td class="'+(x.rrf===1?'winner':'')+'">'+x.rrf+'</td><td class="'+(x.full_rank===1?'winner':'')+'">'+x.full_rank+' · '+x.full_score.toFixed(3)+'</td><td class="'+(x.matched_rank===1?'winner':'')+'">'+x.matched_rank+' · '+x.matched_score.toFixed(3)+'</td></tr>').join('')+'</tbody></table></article>'}}).join('')}}document.querySelector('#search').oninput=render;render();</script></main></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.input.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    documents = {}
    with (ROOT / "data/parent_analysis/directive_similarity_documents.jsonl").open(encoding="utf-8") as handle:
        for row in map(json.loads, handle):
            documents[row["document_id"]] = {key: row[key] for key in ("title", "date", "url")}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_html(rows, documents), encoding="utf-8")
    print(json.dumps(summarize(rows), indent=2)); print(args.output)


if __name__ == "__main__":
    main()
