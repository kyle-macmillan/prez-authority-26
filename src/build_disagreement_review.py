#!/usr/bin/env python3
"""Build disagreement review viewer - six discussion groups for round-2 annotations."""

from __future__ import annotations
import html as html_lib, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SANDBOX_DIR = ROOT / "data" / "Annotations" / "Sandbox 2"

GROUPS = [
    {"label": "Slate", "docs": ["EO9", "EO19", "EO20", "P6", "EO7", "M3", "M22"]},
]

RESULT_FILES = [
    SANDBOX_DIR / "7.16.2026 Tweil_annotations.json",
    SANDBOX_DIR / "annotations-viewer2-claire-2026-07-17.json",
    SANDBOX_DIR / "annotations-viewer2-kylem-2026-07-17.json",
]

SOURCE_VIEWER = SANDBOX_DIR / "sample_100_v2.html"
OUTPUT = SANDBOX_DIR / "disagreement-review.html"

VALUE_LABELS = {
    "0": "0 – Outside scope",
    "1": "1 – Discretionary / internal",
    "2": "2 – Dictated agency outcome",
    "3": "3 – Self-executing",
    "4": "4 – Unclear / mixed",
    "yes": "Yes",
    "no": "No",
}

FIELD_LABELS = {
    "code": "Code",
    "diplomacy": "Diplomacy",
    "military_ops": "Mil / ops",
}

FIELDS = ["code", "diplomacy", "military_ops"]


# ---------------------------------------------------------------------------
# Source extraction (mirrors build_annotation_comparison.py)
# ---------------------------------------------------------------------------

def _extract_json_assignment(source: str, var_name: str) -> object:
    prefix = f"var {var_name}="
    start = source.find(prefix)
    if start < 0:
        raise ValueError(f"Could not find {var_name} assignment")
    start += len(prefix)
    while start < len(source) and source[start].isspace():
        start += 1
    opener = source[start]
    closer = "}" if opener == "{" else "]"
    depth = 0
    in_string = escape = False
    for pos in range(start, len(source)):
        ch = source[pos]
        if in_string:
            if escape: escape = False
            elif ch == "\\": escape = True
            elif ch == '"': in_string = False
            continue
        if ch == '"': in_string = True
        elif ch == opener: depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return json.loads(source[start: pos + 1])
    raise ValueError(f"Could not parse {var_name} JSON assignment")


def extract_source_data(source: str) -> tuple[dict, dict, dict]:
    doc_texts = _extract_json_assignment(source, "DOC_TEXTS")

    metadata: dict = {}
    for match in re.finditer(
        r'<span class="doc-id">([^<]*)</span>\s*'
        r'(?:<span class="global-id">[^<]*</span>\s*)?'
        r'<span class="doc-prez">([^<]*)</span>\s*'
        r'<span class="doc-date">([^<]*)</span>\s*'
        r'<span class="doc-type">([^<]*)</span>',
        source, re.S,
    ):
        doc_id, president, date, doc_type = (html_lib.unescape(v.strip()) for v in match.groups())
        metadata[doc_id] = {"president": president, "date": date, "type": doc_type}

    chunks: dict = {}
    for match in re.finditer(
        r'<div class="seg seg-chunk"(?P<attrs>[^>]*)>.*?'
        r'<span class="seg-text">(?P<chunk_html>.*?)</span><span class="chunk-badge"',
        source, re.S,
    ):
        attrs = dict(re.findall(r'data-([a-zA-Z0-9_-]+)="([^"]*)"', match.group("attrs")))
        if attrs.get("strategy") != "wp":
            continue
        doc_id = attrs.get("doc")
        chunk_number = attrs.get("chunkn")
        if not doc_id or not chunk_number:
            continue
        chunk_text = re.sub(r"<[^>]+>", "", match.group("chunk_html"))
        chunks.setdefault(doc_id, {})[chunk_number] = html_lib.unescape(chunk_text).strip()

    return metadata, chunks, doc_texts  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build_html(metadata: dict, chunks: dict, doc_texts: dict, results: list[dict]) -> str:
    annotators = [r.get("annotator", f"Annotator {i + 1}") for i, r in enumerate(results)]

    # Collect unique doc IDs across all groups
    all_doc_ids: set[str] = {doc_id for g in GROUPS for doc_id in g["docs"]}

    docs_data: dict = {}
    for doc_id in all_doc_ids:
        docs_data[doc_id] = {
            "metadata": metadata.get(doc_id, {}),
            "text": doc_texts.get(doc_id, ""),  # type: ignore[call-overload]
            "chunks": chunks.get(doc_id, {}),
            "annotations": [
                {
                    "directive": r.get(doc_id, {}).get("classification"),
                    "chunks": r.get(doc_id, {}).get("wp_chunks", {}),
                    "wp_comment": (r.get(doc_id, {}).get("wp") or {}).get("comment"),
                }
                for r in results
            ],
        }

    payload = json.dumps(
        {
            "groups": GROUPS,
            "annotators": annotators,
            "docs": docs_data,
            "fields": FIELDS,
            "fieldLabels": FIELD_LABELS,
            "valueLabels": VALUE_LABELS,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")

    return TEMPLATE.replace("__PAYLOAD__", payload)


def main() -> None:
    source = SOURCE_VIEWER.read_text()
    metadata, chunks, doc_texts = extract_source_data(source)
    results = [json.loads(p.read_text()) for p in RESULT_FILES]
    OUTPUT.write_text(build_html(metadata, chunks, doc_texts, results))
    print(f"Wrote {OUTPUT.relative_to(ROOT)} ({OUTPUT.stat().st_size:,} bytes)")


# ---------------------------------------------------------------------------
# Template
# ---------------------------------------------------------------------------

TEMPLATE = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Disagreement Review — Round 2</title>
<style>
body{font-family:system-ui,sans-serif;font-size:13px;margin:0;padding:0;background:#f9fafb;color:#111}
*{box-sizing:border-box}
/* Sticky top bar */
.top-bar{position:sticky;top:0;z-index:10;background:#f9fafb;border-bottom:1px solid #e5e7eb;padding:10px 16px 0}
h1{font-size:1.1rem;margin:0 0 8px;font-weight:800}
/* Mode toggle */
.mode-row{display:flex;gap:16px;align-items:center;margin-bottom:8px;flex-wrap:wrap}
.mode-toggle{display:flex;gap:4px}
.mode-btn{padding:4px 12px;font-size:12px;font-weight:600;cursor:pointer;background:#e5e7eb;border:1px solid #d1d5db;border-radius:4px;color:#374151}
.mode-btn.active{background:#1d4ed8;color:white;border-color:#1d4ed8}
/* Legend */
.legend{display:flex;gap:10px;font-size:11px;align-items:center}
.leg{padding:2px 8px;border-radius:3px;font-weight:700}
.leg-agree{background:#d1fae5;color:#065f46}
.leg-disagree{background:#fee2e2;color:#b91c1c}
.leg-missing{background:#fef3c7;color:#92400e}
/* Tab bar */
.tab-bar{display:flex;gap:2px;overflow-x:auto;border-bottom:2px solid #e5e7eb}
.tab-btn{padding:6px 12px;font-size:12px;font-weight:600;cursor:pointer;background:none;border:none;border-bottom:3px solid transparent;margin-bottom:-2px;color:#6b7280;white-space:nowrap;flex-shrink:0}
.tab-btn:hover{color:#1d4ed8}
.tab-btn.active{color:#1d4ed8;border-bottom-color:#1d4ed8}
.tab-count{font-weight:400;color:#9ca3af}
/* Content */
.content{padding:14px 16px}
/* Doc card */
.doc-card{background:white;border:1px solid #e5e7eb;border-radius:6px;margin-bottom:12px;overflow:hidden}
.doc-card>summary{cursor:pointer;list-style:none;padding:11px 16px;display:flex;gap:10px;align-items:baseline;border-bottom:1px solid #f3f4f6}
.doc-card>summary::-webkit-details-marker{display:none}
.doc-id{font-weight:800;font-size:17px;color:#1d4ed8;min-width:3.4em;flex-shrink:0}
.doc-prez{font-weight:700;font-size:14px}
.doc-date{color:#6b7280;font-size:13px}
.doc-type{font-style:italic;color:#6b7280;font-size:13px}
.doc-badge{margin-left:auto;padding:2px 9px;border-radius:999px;font-size:11px;font-weight:700;white-space:nowrap;flex-shrink:0}
.doc-badge.agree{background:#d1fae5;color:#065f46}
.doc-badge.disagree{background:#fee2e2;color:#b91c1c}
.doc-badge.missing{background:#fef3c7;color:#92400e}
/* Two-column body */
.doc-body{display:grid;grid-template-columns:1fr 1fr;align-items:start}
.col{padding:12px 14px;min-width:0}
.col+.col{border-left:1px solid #e5e7eb;position:sticky;top:var(--bar-height,120px);align-self:start}
.col-heading{font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:#9ca3af;margin:0 0 8px;font-weight:600}
/* Doc text */
.doc-text{white-space:pre-wrap;font-size:12px;line-height:1.65;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:#1f2937;background:#f8fafc;border:1px solid #e5e7eb;border-radius:4px;padding:8px 10px}
/* Annotation table */
.ann-table{border-collapse:collapse;width:100%;font-size:12px}
.ann-table th{text-align:left;padding:4px 8px;background:#f3f4f6;color:#6b7280;font-weight:600;border:1px solid #e5e7eb;font-size:11px}
.ann-table td{padding:5px 8px;border:1px solid #e5e7eb;vertical-align:middle}
.ann-table td.field-label{font-weight:700;color:#374151;background:#f9fafb;white-space:nowrap}
.ann-table tr.row-agree td.val-cell:not(.val-missing){background:#d1fae5;color:#065f46}
.ann-table tr.row-disagree td.val-cell:not(.val-missing){background:#fee2e2;color:#b91c1c}
.ann-table td.val-missing{background:#fef3c7;color:#92400e;font-style:italic}
/* Chunks */
.chunk-block{margin-bottom:12px}
.chunk-label{font-size:11px;font-weight:700;color:#1d4ed8;margin-bottom:4px}
.chunk-text{font-size:12px;background:#f8fafc;border-left:3px solid #93c5fd;padding:6px 10px;margin-bottom:6px;white-space:pre-wrap;line-height:1.55;color:#1f2937;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.no-chunks{font-size:12px;color:#9ca3af;font-style:italic;margin-bottom:10px}
/* WP comments */
.comments{margin-top:10px;background:#fffbeb;border:1px solid #fde68a;border-radius:4px;padding:8px 10px;font-size:12px}
.comment-heading{font-weight:700;color:#92400e;font-size:11px;margin-bottom:5px}
.comment-item{margin-bottom:3px;line-height:1.5}
.comment-who{font-weight:700;color:#374151}
@media(max-width:700px){.doc-body{grid-template-columns:1fr}.col+.col{border-left:none;border-top:1px solid #e5e7eb}}
</style>
</head>
<body>
<div class="top-bar">
  <h1>Disagreement Review — Round 2</h1>
  <div class="mode-row">
    <div class="mode-toggle">
      <button class="mode-btn active" id="btn-directive" type="button">Directive</button>
      <button class="mode-btn" id="btn-subdirective" type="button">Sub-directive</button>
    </div>
    <div class="legend">
      <span class="leg leg-agree">Agreement</span>
      <span class="leg leg-disagree">Disagreement</span>
      <span class="leg leg-missing">Missing</span>
    </div>
  </div>
  <div class="tab-bar" id="tab-bar"></div>
</div>
<div class="content" id="content"></div>
<script id="payload-data" type="application/json">__PAYLOAD__</script>
<script>
(function(){
'use strict';
var P=JSON.parse(document.getElementById('payload-data').textContent);
var groups=P.groups,annotators=P.annotators,docs=P.docs;
var fields=P.fields,fieldLabels=P.fieldLabels,valueLabels=P.valueLabels;
var mode='directive',activeTab=0;

function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
function label(v){return v==null?null:(valueLabels[v]||v);}

function rowAgreement(vals){
  var nn=vals.filter(function(v){return v!=null;});
  if(!nn.length)return 'missing';
  return(new Set(nn)).size>1?'disagree':(nn.length<vals.length?'missing':'agree');
}

function docAgreement(docId){
  var d=docs[docId];if(!d)return 'missing';
  var ann=d.annotations;
  var hasMissing=false;
  for(var fi=0;fi<fields.length;fi++){
    var f=fields[fi];
    var vals=ann.map(function(a){return a.directive?(a.directive[f]!=null?a.directive[f]:null):null;});
    var ag=rowAgreement(vals);
    if(ag==='disagree')return 'disagree';
    if(ag==='missing')hasMissing=true;
  }
  return hasMissing?'missing':'agree';
}

function annTable(rowData){
  var out='<table class="ann-table"><thead><tr><th>Field</th>';
  annotators.forEach(function(n){out+='<th>'+esc(n)+'</th>';});
  out+='</tr></thead><tbody>';
  rowData.forEach(function(row){
    var ag=rowAgreement(row.vals);
    out+='<tr class="row-'+ag+'"><td class="field-label">'+esc(row.label)+'</td>';
    row.vals.forEach(function(v){
      var cls='val-cell'+(v==null?' val-missing':'');
      out+='<td class="'+cls+'">'+(v==null?'—':esc(label(v)))+'</td>';
    });
    out+='</tr>';
  });
  return out+'</tbody></table>';
}

function makeRowData(getVal){
  return fields.map(function(f){
    return{field:f,label:fieldLabels[f],vals:annotators.map(function(_,i){return getVal(i,f);})};
  });
}

function directiveTable(ann){
  return annTable(makeRowData(function(i,f){
    var d=ann[i].directive;return d?(d[f]!=null?d[f]:null):null;
  }));
}

function chunkTable(chunkN,ann){
  return annTable(makeRowData(function(i,f){
    var c=ann[i].chunks?ann[i].chunks[chunkN]:null;return c?(c[f]!=null?c[f]:null):null;
  }));
}

function wpComments(ann){
  var items=ann.map(function(a,i){return{who:annotators[i],txt:a.wp_comment};}).filter(function(x){return x.txt;});
  if(!items.length)return '';
  var out='<div class="comments"><div class="comment-heading">Discussion notes</div>';
  items.forEach(function(x){out+='<div class="comment-item"><span class="comment-who">'+esc(x.who)+':</span> '+esc(x.txt)+'</div>';});
  return out+'</div>';
}

function rightCol(docId){
  var d=docs[docId];if(!d)return '<div class="no-chunks">No data.</div>';
  var ann=d.annotations;
  if(mode==='directive')return directiveTable(ann)+wpComments(ann);
  // subdirective
  var ckKeys=Object.keys(d.chunks||{}).sort(function(a,b){return+a-+b;});
  var out='';
  if(!ckKeys.length)out+='<div class="no-chunks">No sub-directive chunks — showing directive-level.</div>';
  else{
    ckKeys.forEach(function(n){
      out+='<div class="chunk-block"><div class="chunk-label">Chunk '+esc(n)+'</div>';
      out+='<div class="chunk-text">'+esc(d.chunks[n])+'</div>';
      out+=chunkTable(n,ann)+'</div>';
    });
  }
  out+=wpComments(ann);
  if(!ckKeys.length)out+=directiveTable(ann);
  return out;
}

function renderDoc(docId){
  var d=docs[docId];if(!d)return '';
  var m=d.metadata||{};
  var ag=docAgreement(docId);
  var badgeText=ag==='agree'?'Agreement':ag==='disagree'?'Disagreement':'Incomplete';
  var colHead=mode==='directive'?'Directive annotation':'Sub-directive annotation';
  return '<details class="doc-card" open>'
    +'<summary>'
    +'<span class="doc-id">'+esc(docId)+'</span>'
    +'<span class="doc-prez">'+esc(m.president||'')+'</span>'
    +'<span class="doc-date">'+esc(m.date||'')+'</span>'
    +'<span class="doc-type">'+esc((m.type||'').replace(/_/g,' '))+'</span>'
    +'<span class="doc-badge '+ag+'">'+badgeText+'</span>'
    +'</summary>'
    +'<div class="doc-body">'
    +'<div class="col"><p class="col-heading">Document text</p><div class="doc-text">'+esc(d.text||'(text not found)')+'</div></div>'
    +'<div class="col"><p class="col-heading">'+esc(colHead)+'</p>'+rightCol(docId)+'</div>'
    +'</div></details>';
}

function renderPanel(){
  var g=groups[activeTab];
  var seen=new Set();
  return g.docs.map(function(id){
    if(seen.has(id))return '';seen.add(id);return renderDoc(id);
  }).join('');
}

function renderTabs(){
  document.getElementById('tab-bar').innerHTML=groups.map(function(g,i){
    return'<button class="tab-btn'+(i===activeTab?' active':'')+'" data-idx="'+i+'" type="button">'
      +esc(g.label)+' <span class="tab-count">('+g.docs.length+')</span></button>';
  }).join('');
}

function render(){renderTabs();document.getElementById('content').innerHTML=renderPanel();}

document.getElementById('tab-bar').addEventListener('click',function(e){
  var btn=e.target.closest('.tab-btn');if(!btn)return;
  activeTab=+btn.dataset.idx;render();
});
document.getElementById('btn-directive').addEventListener('click',function(){
  mode='directive';
  document.getElementById('btn-directive').classList.add('active');
  document.getElementById('btn-subdirective').classList.remove('active');
  document.getElementById('content').innerHTML=renderPanel();
});
document.getElementById('btn-subdirective').addEventListener('click',function(){
  mode='subdirective';
  document.getElementById('btn-directive').classList.remove('active');
  document.getElementById('btn-subdirective').classList.add('active');
  document.getElementById('content').innerHTML=renderPanel();
});

render();

function setBarHeight(){
  var h=document.getElementById('tab-bar').getBoundingClientRect().bottom;
  document.documentElement.style.setProperty('--bar-height',h+'px');
}
setBarHeight();
window.addEventListener('resize',setBarHeight);
})();
</script>
</body>
</html>
'''


if __name__ == "__main__":
    main()
