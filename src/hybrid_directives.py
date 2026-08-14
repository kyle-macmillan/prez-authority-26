#!/usr/bin/env python3
"""Build a viewer showing hybrid directives in the sample-100 annotation set.

A directive is "hybrid" for a given annotator when its sub-directives (chunks) carry
2+ distinct effective labels on at least one axis:
  - Category axis: top-level category + legal_effect split
      (policy-legal vs policy-nonlegal; legal_effect gated to policy only)
  - Scope axis: domestic vs foreign (null scope values ignored)

The output page has a three-way criterion toggle (at least one / majority / unanimous),
a dropdown to filter to a single annotator's hybrid docs, and directives grouped by type.
Each directive shows its vesting clause classification (boilerplate / specific / none)
and the actual clause text.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

from vesting_authority_stats import (
    classify_vesting_clauses,
    extract_vesting_clauses,
    load_corpus,
    DEFAULT_DEV,
    DEFAULT_HOLDOUT,
)


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "data" / "Annotations" / "Sandbox 1"
SOURCE_VIEWER = SAMPLE_DIR / "viewer-100.html"
RESULTS_DIR = SAMPLE_DIR / "results"
DOC_ID_MAP = SAMPLE_DIR / "doc_id_map_viewer.json"
OUTPUT = SAMPLE_DIR / "hybrid-directives.html"

_PREFIX_ORDER = {"EO": 0, "M": 1, "L": 2, "P": 3}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def extract_source_data(source: str) -> tuple[dict, dict]:
    """Return (metadata, chunk_texts) scraped from viewer-100.html."""
    metadata: dict[str, dict] = {}
    for match in re.finditer(
        r'<span class="doc-id">(.*?)</span>\s*'
        r'<span class="doc-prez">(.*?)</span>\s*'
        r'<span class="doc-date">(.*?)</span>\s*'
        r'<span class="doc-type">(.*?)</span>',
        source,
        re.S,
    ):
        doc_id, president, date, doc_type = (html.unescape(v.strip()) for v in match.groups())
        metadata[doc_id] = {"president": president, "date": date, "type": doc_type}

    chunks: dict[str, dict[str, str]] = {}
    for match in re.finditer(
        r'<div class="seg seg-chunk"[^>]*data-doc="([^"]+)"[^>]*data-chunkn="([^"]+)"[^>]*>.*?'
        r'<span class="seg-text">(.*?)</span><span class="chunk-badge"',
        source,
        re.S,
    ):
        doc_id, chunk_number, chunk_html = match.groups()
        chunk_text = re.sub(r"<[^>]+>", "", chunk_html)
        chunks.setdefault(doc_id, {})[chunk_number] = html.unescape(chunk_text).strip()

    return metadata, chunks


def load_results() -> list[tuple[str, dict]]:
    """Return (annotator_name, result_dict) for every JSON in results/."""
    results = []
    for path in sorted(RESULTS_DIR.glob("*.json")):
        data = json.loads(path.read_text())
        name = data.get("annotator") or path.stem
        results.append((name, data))
    return results


# ---------------------------------------------------------------------------
# Vesting classification
# ---------------------------------------------------------------------------


def _vesting_info(doc_text: str, doc_type: str) -> tuple[str, list[str]]:
    """Return (category, clause_texts).

    category: "generic" (boilerplate) | "specific" | "no_vesting_clause"
    """
    clauses = extract_vesting_clauses(doc_text, doc_type)
    if not clauses:
        return "no_vesting_clause", []
    qualifies, _, _ = classify_vesting_clauses(clauses)
    return ("generic" if qualifies else "specific"), clauses


# ---------------------------------------------------------------------------
# Hybrid logic
# ---------------------------------------------------------------------------


def effective_cat(chunk_data: dict) -> str | None:
    """Return the effective category label for one chunk.

    policy + legal_effect=legal    -> "policy-legal"
    policy + legal_effect=nonlegal -> "policy-nonlegal"
    policy (no legal_effect)       -> "policy"
    anything else                  -> the category value as-is
    legal_effect is gated: only meaningful when category == "policy".
    """
    cat = chunk_data.get("category")
    if not cat:
        return None
    if cat == "policy":
        le = chunk_data.get("legal_effect")
        if le == "legal":
            return "policy-legal"
        if le == "nonlegal":
            return "policy-nonlegal"
    return cat


def directive_combos(per_annotator: list[dict]) -> dict[str, bool]:
    """Identify which label-pair types appear in any annotator's assessment.

    pl_pnl: policy-legal + policy-nonlegal
    pl_im:  policy-legal + internal
    pnl_im: policy-nonlegal + internal
    other:  hybrid that doesn't contain any of the three named pairs
            (scope-only hybrids, or other category mixes like policy/ceremonial)
    """
    pl_pnl = pl_im = pnl_im = False
    for a in per_annotator:
        lbls = set(a["labels"].values())
        if {"policy-legal", "policy-nonlegal"} <= lbls:
            pl_pnl = True
        if {"policy-legal", "internal"} <= lbls:
            pl_im = True
        if {"policy-nonlegal", "internal"} <= lbls:
            pnl_im = True
    return {
        "pl_pnl": pl_pnl,
        "pl_im": pl_im,
        "pnl_im": pnl_im,
        "other": not (pl_pnl or pl_im or pnl_im),
    }


def annotator_hybrid(chunks_dict: dict) -> tuple[bool, str | None]:
    """Return (is_hybrid, reason) for one annotator's chunk set on a directive."""
    labels = [effective_cat(v) for v in chunks_dict.values()]
    labels = [l for l in labels if l]
    scopes = [v.get("scope") for v in chunks_dict.values()]
    scopes = [s for s in scopes if s]

    cat_hyb = len(set(labels)) > 1
    scope_hyb = len(set(scopes)) > 1

    if cat_hyb and scope_hyb:
        return True, "both"
    if cat_hyb:
        return True, "category"
    if scope_hyb:
        return True, "scope"
    return False, None


# ---------------------------------------------------------------------------
# Payload construction
# ---------------------------------------------------------------------------


def _doc_sort_key(doc_id: str) -> tuple[int, int]:
    m = re.match(r"^([A-Z]+)(\d+)$", doc_id)
    if m:
        return _PREFIX_ORDER.get(m.group(1), 9), int(m.group(2))
    return 9, 0


def build_payload(
    metadata: dict,
    chunks: dict,
    results: list[tuple[str, dict]],
    corpus: dict[int, dict],
    id_map: dict[str, int],
) -> list[dict]:
    """Return a list of per-doc dicts for the JS payload, hybrid docs only.

    Sorted by: doc type (EO/M/L/P), then hybrid count desc, then doc number.
    """
    docs = []
    for doc_id in sorted(metadata, key=_doc_sort_key):
        doc_chunks = chunks.get(doc_id, {})
        chunk_ns = sorted(doc_chunks, key=lambda n: int(n))

        per_annotator = []
        for name, result_dict in results:
            ann_chunks = result_dict.get(doc_id, {}).get("chunks", {})
            if not any(effective_cat(v) for v in ann_chunks.values()):
                continue
            is_hyb, reason = annotator_hybrid(ann_chunks)
            per_annotator.append(
                {
                    "name": name,
                    "labels": {
                        n: effective_cat(ann_chunks[n])
                        for n in ann_chunks
                        if effective_cat(ann_chunks[n])
                    },
                    "scopes": {
                        n: ann_chunks[n].get("scope")
                        for n in ann_chunks
                        if ann_chunks.get(n, {}).get("scope")
                    },
                    "hybrid": is_hyb,
                    "reason": reason,
                }
            )

        hybrid_count = sum(1 for a in per_annotator if a["hybrid"])
        if hybrid_count < 1:
            continue

        # Vesting classification from corpus text
        row_idx = id_map.get(doc_id)
        corpus_row = corpus.get(row_idx) if row_idx is not None else None
        if corpus_row:
            vc_cat, vc_clauses = _vesting_info(
                corpus_row.get("doc_text", ""), corpus_row.get("doc_type", "")
            )
            doc_url = corpus_row.get("url", "")
        else:
            vc_cat, vc_clauses = "no_vesting_clause", []
            doc_url = ""

        docs.append(
            {
                "id": doc_id,
                "meta": {**metadata[doc_id], "url": doc_url},
                "chunks": [{"n": n, "text": doc_chunks.get(n, "")} for n in chunk_ns],
                "perAnnotator": per_annotator,
                "present": len(per_annotator),
                "hybridCount": hybrid_count,
                "vesting": {"category": vc_cat, "clauses": vc_clauses},
                "combos": directive_combos(per_annotator),
            }
        )

    # Primary: doc type group; secondary: hybrid count desc; tertiary: doc number
    docs.sort(key=lambda d: (_doc_sort_key(d["id"])[0], -d["hybridCount"], _doc_sort_key(d["id"])[1]))
    return docs


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------


def compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def build_html(docs: list[dict], total: int, annotators: list[str]) -> str:
    payload = compact_json({"docs": docs, "total": total, "annotators": annotators})
    return TEMPLATE.replace("__PAYLOAD__", payload)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    metadata, chunks = extract_source_data(SOURCE_VIEWER.read_text())
    results = load_results()
    annotators = [name for name, _ in results]
    id_map: dict[str, int] = json.loads(DOC_ID_MAP.read_text())
    corpus: dict[int, dict] = {int(r[""]): r for r in load_corpus([DEFAULT_DEV])}
    docs = build_payload(metadata, chunks, results, corpus, id_map)
    html_out = build_html(docs, len(metadata), annotators)
    OUTPUT.write_text(html_out)

    by_annotator: dict[str, int] = {}
    for doc in docs:
        for a in doc["perAnnotator"]:
            if a["hybrid"]:
                by_annotator[a["name"]] = by_annotator.get(a["name"], 0) + 1

    n_total = len(metadata)
    print(f"Wrote {OUTPUT.relative_to(ROOT)} ({OUTPUT.stat().st_size:,} bytes)")
    print(f"Hybrid (at least one):  {len(docs)} of {n_total}")
    print(f"Hybrid (majority):      {sum(1 for d in docs if d['hybridCount'] > d['present'] / 2)} of {n_total}")
    print(f"Hybrid (unanimous):     {sum(1 for d in docs if d['hybridCount'] == d['present'])} of {n_total}")
    print("Per annotator:")
    for name, count in sorted(by_annotator.items(), key=lambda x: -x[1]):
        print(f"  {name}: {count}")


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

TEMPLATE = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hybrid Directives — Sample 100</title>
<style>
:root{--ink:#172033;--muted:#64748b;--line:#d9e1ea;--paper:#fff;--bg:#f4f6f8;--blue:#174ea6}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,-apple-system,BlinkMacSystemFont,sans-serif}
button,select{font:inherit}
.shell{max-width:1400px;margin:auto;padding:22px}
.top{position:sticky;top:0;z-index:5;background:rgba(244,246,248,.97);padding:10px 0 14px;border-bottom:1px solid var(--line);margin-bottom:18px}
h1{font-size:22px;margin:0 0 3px}
.subtitle{color:var(--muted);margin:0 0 12px;font-size:13px}
.toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.toggle{display:inline-flex;border:1px solid #b8c4d1;border-radius:7px;overflow:hidden;background:#fff}
.toggle button{border:0;border-right:1px solid #b8c4d1;background:#fff;padding:7px 15px;cursor:pointer;font-size:13px}
.toggle button:last-child{border-right:0}
.toggle button.active{background:var(--blue);color:#fff}
.toggle.disabled{opacity:.4;pointer-events:none}
.ann-select{padding:7px 10px;border:1px solid #b8c4d1;border-radius:7px;background:#fff;font-size:13px;cursor:pointer}
.vest-checks{border:1px solid #b8c4d1;border-radius:7px;background:#fff;padding:5px 12px 6px;display:flex;gap:12px;align-items:center;font-size:13px;margin:0}
.vest-checks legend{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);padding:0 4px;float:left;width:auto}
.vest-checks label{display:flex;align-items:center;gap:5px;cursor:pointer;user-select:none}
.count{margin-left:auto;color:var(--muted);font-size:13px;font-variant-numeric:tabular-nums}
.group-head{font-size:17px;font-weight:750;color:var(--ink);margin:24px 0 10px;padding-bottom:6px;border-bottom:2px solid var(--line)}
.group-head:first-child{margin-top:0}
.documents{display:grid;gap:12px}
.doc{background:var(--paper);border:1px solid var(--line);border-radius:9px;overflow:hidden}
summary.doc-head{cursor:pointer;list-style:none;padding:12px 15px;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
summary.doc-head::-webkit-details-marker{display:none}
.doc-id{font-size:17px;font-weight:850;color:var(--blue);min-width:46px}
.doc-prez{font-weight:700}
.doc-meta{color:var(--muted);font-size:13px}
.src-link{color:var(--blue);font-size:12px;text-decoration:none;margin-left:4px}
.src-link:hover{text-decoration:underline}
.hybrid-badge{margin-left:auto;background:#fff0f0;color:#a02727;border-radius:999px;padding:2px 10px;font-size:11px;font-weight:800;white-space:nowrap}
.doc-body{padding:10px 15px 15px}
.hybrid-summary{font-size:13px;color:#555;margin-bottom:10px;line-height:1.6}
.hybrid-summary .reason{color:var(--muted)}
.vesting-section{margin-bottom:12px;padding:9px 12px;background:#f8fafc;border:1px solid var(--line);border-radius:6px}
.vesting-label{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin-bottom:5px}
.vesting-badge{display:inline-block;padding:3px 8px;border-radius:5px;font-size:12px;font-weight:700;margin-bottom:6px}
.vc-generic{background:#e3f2fd;color:#1565c0}
.vc-specific{background:#ede7f6;color:#5e35b1}
.vc-no_vesting_clause{background:#f5f5f5;color:#616161}
.vesting-clause-text{font-size:12px;color:#444;line-height:1.55;white-space:pre-wrap;word-break:break-word;font-style:italic;margin-top:4px;padding-top:6px;border-top:1px solid var(--line)}
.vesting-clause-text+.vesting-clause-text{margin-top:6px}
.table-wrap{overflow-x:auto}
table.chunk-table{width:100%;border-collapse:collapse;font-size:13px}
.chunk-table th,.chunk-table td{border:1px solid var(--line);padding:8px 10px;vertical-align:top;text-align:left}
.chunk-table thead th{background:#eef3f8;font-weight:750}
th.chunk-col{min-width:300px}
th.ann-col{min-width:155px}
.chunk-n{font-weight:800;color:var(--blue);display:block;margin-bottom:4px}
.chunk-text{color:#333;font-size:13px;line-height:1.55;white-space:pre-wrap;word-break:break-word}
.badge{display:block;padding:3px 7px;border-radius:5px;font-size:12px;font-weight:700;margin-bottom:3px;white-space:nowrap;width:fit-content}
.scope-badge{display:inline-block;padding:2px 6px;border-radius:4px;font-size:11px;font-weight:600;white-space:nowrap}
.cat-ceremonial{background:#ede7f6;color:#5e35b1}
.cat-internal{background:#e3f2fd;color:#1565c0}
.cat-policy-legal{background:#e8f5e9;color:#2e7d32}
.cat-policy-nonlegal{background:#f1f8e9;color:#558b2f}
.cat-operative-congress{background:#fff3e0;color:#e65100}
.cat-other{background:#f5f5f5;color:#616161}
.cat-policy{background:#e8f5e9;color:#33691e}
.cat-missing{background:#fafafa;color:#aaa;font-weight:400;font-style:italic}
.scope-domestic{background:#e0f0ff;color:#1a5276}
.scope-foreign{background:#fff8e1;color:#7b5800}
.empty{text-align:center;color:var(--muted);padding:50px;background:var(--paper);border:1px solid var(--line);border-radius:9px}
</style>
</head>
<body>
<main class="shell">
  <section class="top">
    <h1>Hybrid Directives — Sample 100</h1>
    <p class="subtitle">Directives containing sub-directives with different labels — by category (with policy / legal-effect split) or scope (domestic / foreign)</p>
    <div class="toolbar">
      <fieldset class="vest-checks" id="combo-checks">
        <legend>Hybrid type</legend>
        <label><input type="checkbox" class="combo-cb" value="pl_pnl" checked> Policy Legal / Non-legal</label>
        <label><input type="checkbox" class="combo-cb" value="pl_im" checked> Policy Legal / IM</label>
        <label><input type="checkbox" class="combo-cb" value="pnl_im" checked> Policy Non-legal / IM</label>
        <label><input type="checkbox" class="combo-cb" value="other" checked> Other</label>
      </fieldset>
      <fieldset class="vest-checks" id="vest-checks">
        <legend>Vesting clause</legend>
        <label><input type="checkbox" class="vc-cb" value="generic" checked> Boilerplate</label>
        <label><input type="checkbox" class="vc-cb" value="specific" checked> Specific</label>
        <label><input type="checkbox" class="vc-cb" value="no_vesting_clause" checked> No vesting clause</label>
      </fieldset>
      <div class="toggle" id="crit-toggle" role="group" aria-label="Hybrid criterion">
        <button id="crit-any" class="active" type="button">At least one annotator</button>
        <button id="crit-majority" type="button">Majority</button>
        <button id="crit-unanimous" type="button">Unanimous</button>
      </div>
      <select id="ann-filter" class="ann-select" aria-label="Filter by annotator"></select>
      <span class="count" id="vis-count"></span>
    </div>
  </section>
  <div id="docs-list"></div>
</main>
<script id="payload" type="application/json">__PAYLOAD__</script>
<script>
(function(){
'use strict';
var data=JSON.parse(document.getElementById('payload').textContent);
var docs=data.docs;
var total=data.total;
var annotators=data.annotators;
var crit='any';
var annFilter='all';
var vestFilter=new Set(['generic','specific','no_vesting_clause']);
var comboFilter={pl_pnl:true,pl_im:true,pnl_im:true,other:true};

var CAT_LABELS={
  'ceremonial':'Ceremonial',
  'internal':'Internal',
  'policy-legal':'Policy / Legal',
  'policy-nonlegal':'Policy / Non-legal',
  'operative_congress':'Operative (Congress)',
  'other':'Other',
  'policy':'Policy'
};
var SCOPE_LABELS={'domestic':'Domestic','foreign':'Foreign'};
var REASON_LABELS={
  'category':'category differs',
  'scope':'scope differs',
  'both':'category & scope differ'
};
var VC_LABELS={
  'generic':'Boilerplate',
  'specific':'Specific',
  'no_vesting_clause':'No vesting clause'
};
var GROUP_NAMES={
  'EO':'Executive Orders',
  'M':'Memoranda',
  'L':'Letters',
  'P':'Proclamations'
};

function esc(s){
  return String(s==null?'':s).replace(/[&<>"']/g,function(c){
    return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
  });
}

function catClass(label){
  if(!label)return 'cat-missing';
  return 'cat-'+String(label).replace(/_/g,'-');
}

function prefixOf(id){
  var m=/^([A-Z]+)\d+$/.exec(id);
  return m?m[1]:'';
}

function qualifies(doc){
  if(!vestFilter.has(doc.vesting.category))return false;
  var c=doc.combos;
  if(!(comboFilter.pl_pnl&&c.pl_pnl||comboFilter.pl_im&&c.pl_im||comboFilter.pnl_im&&c.pnl_im||comboFilter.other&&c.other))return false;
  if(annFilter!=='all'){
    return doc.perAnnotator.some(function(a){return a.name===annFilter&&a.hybrid;});
  }
  var h=doc.hybridCount,p=doc.present;
  if(crit==='any')return h>=1;
  if(crit==='majority')return h>p/2;
  if(crit==='unanimous')return h===p;
  return false;
}

function renderVesting(vc){
  var cls='vc-'+vc.category;
  var lbl=VC_LABELS[vc.category]||vc.category;
  var out='<div class="vesting-section">'+
    '<div class="vesting-label">Vesting clause</div>'+
    '<span class="vesting-badge '+esc(cls)+'">'+esc(lbl)+'</span>';
  vc.clauses.forEach(function(c){
    out+='<div class="vesting-clause-text">'+esc(c)+'</div>';
  });
  return out+'</div>';
}

function renderDoc(doc){
  var visibleAnns=annFilter==='all'
    ? doc.perAnnotator
    : doc.perAnnotator.filter(function(a){return a.name===annFilter;});
  var hybridAnns=doc.perAnnotator.filter(function(a){return a.hybrid;});
  var summaryParts=hybridAnns.map(function(a){
    return '<strong>'+esc(a.name)+'</strong> <span class="reason">('+esc(REASON_LABELS[a.reason]||a.reason)+')</span>';
  });

  var thead='<tr><th class="chunk-col">Sub-directive</th>';
  visibleAnns.forEach(function(a){
    thead+='<th class="ann-col">'+esc(a.name)+(a.hybrid?' ★':'')+'</th>';
  });
  thead+='</tr>';

  var tbody='';
  doc.chunks.forEach(function(chunk){
    tbody+='<tr>';
    tbody+='<td><span class="chunk-n">#'+esc(chunk.n)+'</span><span class="chunk-text">'+esc(chunk.text)+'</span></td>';
    visibleAnns.forEach(function(a){
      var cat=a.labels[chunk.n];
      var scope=a.scopes[chunk.n];
      tbody+='<td>';
      tbody+='<span class="badge '+esc(catClass(cat))+'">'+esc(cat?(CAT_LABELS[cat]||cat):'—')+'</span>';
      if(scope)tbody+='<span class="scope-badge scope-'+esc(scope)+'">'+esc(SCOPE_LABELS[scope]||scope)+'</span>';
      tbody+='</td>';
    });
    tbody+='</tr>';
  });

  var m=doc.meta;
  var srcLink=m.url
    ? ' <a class="src-link" href="'+esc(m.url)+'" target="_blank" rel="noopener">source ↗</a>'
    : '';
  return '<details class="doc" open>'+
    '<summary class="doc-head">'+
      '<span class="doc-id">'+esc(doc.id)+'</span>'+
      '<span class="doc-prez">'+esc(m.president)+'</span>'+
      '<span class="doc-meta">'+esc(m.date)+' · '+esc((m.type||'').replace(/_/g,' '))+srcLink+'</span>'+
      '<span class="hybrid-badge">'+doc.hybridCount+' / '+doc.present+' annotators</span>'+
    '</summary>'+
    '<div class="doc-body">'+
      renderVesting(doc.vesting)+
      '<div class="hybrid-summary">Hybrid for: '+summaryParts.join(' · ')+'</div>'+
      '<div class="table-wrap"><table class="chunk-table">'+
        '<thead>'+thead+'</thead>'+
        '<tbody>'+tbody+'</tbody>'+
      '</table></div>'+
    '</div>'+
  '</details>';
}

function render(){
  var shown=docs.filter(qualifies);
  var isSingle=annFilter!=='all';
  document.getElementById('crit-toggle').classList.toggle('disabled',isSingle);
  document.getElementById('vis-count').textContent=
    shown.length+' of '+total+' directives are hybrid'+(isSingle?' for '+annFilter:'');

  // Render with group headers between doc-type sections
  var html='<section class="documents">';
  var lastPrefix=null;
  shown.forEach(function(doc){
    var prefix=prefixOf(doc.id);
    if(prefix!==lastPrefix){
      if(lastPrefix!==null)html+='</section><section class="documents">';
      html+='<h2 class="group-head">'+esc(GROUP_NAMES[prefix]||prefix)+'</h2>';
      lastPrefix=prefix;
    }
    html+=renderDoc(doc);
  });
  html+='</section>';

  document.getElementById('docs-list').innerHTML=shown.length
    ? html
    : '<div class="empty">No directives qualify under this criterion.</div>';

  ['any','majority','unanimous'].forEach(function(c){
    document.getElementById('crit-'+c).classList.toggle('active',crit===c);
  });
}

// Populate annotator dropdown
(function(){
  var sel=document.getElementById('ann-filter');
  sel.innerHTML='<option value="all">All annotators</option>';
  annotators.forEach(function(name){
    var opt=document.createElement('option');
    opt.value=name;opt.textContent=name;
    sel.appendChild(opt);
  });
  sel.addEventListener('change',function(){annFilter=this.value;render();});
})();

document.querySelectorAll('.vc-cb').forEach(function(cb){
  cb.addEventListener('change',function(){
    if(this.checked)vestFilter.add(this.value);else vestFilter.delete(this.value);
    render();
  });
});
document.querySelectorAll('.combo-cb').forEach(function(cb){
  cb.addEventListener('change',function(){comboFilter[this.value]=this.checked;render();});
});

document.getElementById('crit-any').addEventListener('click',function(){crit='any';render();});
document.getElementById('crit-majority').addEventListener('click',function(){crit='majority';render();});
document.getElementById('crit-unanimous').addEventListener('click',function(){crit='unanimous';render();});

render();
})();
</script>
</body>
</html>
'''


if __name__ == "__main__":
    main()
