#!/usr/bin/env python3
"""Build the standalone sample-100 annotation comparison viewer."""

from __future__ import annotations

import html
import argparse
import json
import math
import re
from pathlib import Path

import krippendorff
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
ANNOTATIONS_DIR = ROOT / "data" / "Annotations"
DATASETS = {
    "sample100": {
        "label": "Sample 100",
        "schema": "policy",
        "source_viewer": ANNOTATIONS_DIR / "Sandbox 1" / "viewer-100.html",
        "results_dir": ANNOTATIONS_DIR / "Sandbox 1" / "results",
        "output": ANNOTATIONS_DIR / "Sandbox 1" / "annotation-comparison.html",
        "result_files": (
            "TW_annotations-viewer1-thomas_weil-2026-06-22.json",
            "annotations-viewer1-jennifer_nou-2026-06-22.json",
            "annotations-viewer1-kylem-2026-06-22.json",
            "CM Parts 1 + 2.json",
        ),
        "fields": {
            "directive": ("category", "legal_effect", "scope", "national_security", "emergency"),
            "chunk": ("category", "legal_effect", "scope", "national_security"),
        },
        "field_labels": {
            "category": "Category",
            "legal_effect": "Legal effect",
            "scope": "Scope",
            "national_security": "National security",
            "emergency": "Emergency",
        },
        "value_labels": {
            "ceremonial": "Ceremonial / Expressive",
            "internal": "Internal Management",
            "policy": "Policy Setting",
            "operative_congress": "Operative Actions to Congress",
            "other": "Other",
            "legal": "Likely legal effect",
            "nonlegal": "Non-legally binding",
            "domestic": "Domestic",
            "foreign": "Foreign",
            "yes": "Yes",
            "no": "No",
            "self_executing": "Self-executing",
            "policy_legal": "Policy-setting (likely legal effect)",
            "policy_no_legal": "Policy-setting (w/o legal effect)",
            "internal_management": "Internal Management",
        },
        "field_options": {
            "category": ("self_executing", "policy_legal", "policy_no_legal", "internal", "ceremonial", "other"),
            "legal_effect": ("legal", "nonlegal"),
            "scope": ("domestic", "foreign"),
            "national_security": ("yes", "no"),
            "emergency": ("yes", "no"),
        },
        "chunk_strategy": None,
    },
    "round2": {
        "label": "Sample 100 round 2",
        "schema": "round2",
        "source_viewer": ANNOTATIONS_DIR / "Sandbox 2" / "sample_100_v2.html",
        "results_dir": ANNOTATIONS_DIR / "Sandbox 2",
        "output": ANNOTATIONS_DIR / "Sandbox 2" / "annotation-comparison.html",
        "result_files": (
            "7.16.2026 Tweil_annotations.json",
            "CM-annotations-part2.json",
            "annotations-viewer2-kylem-2026-07-17.json",
        ),
        "fields": {
            "directive": ("code", "diplomacy", "military_ops"),
            "chunk": ("code", "diplomacy", "military_ops"),
        },
        "field_labels": {
            "code": "Code",
            "diplomacy": "Diplomacy / recognition",
            "military_ops": "Military / intel ops",
        },
        "value_labels": {
            "0": "0 - Outside scope",
            "1": "1 - Discretionary executive direction / internal management",
            "2": "2 - Dictated agency legal outcome",
            "3": "3 - Self-executing legal effect",
            "4": "4 - Unclear / inseparable mixed",
            "yes": "Yes",
            "no": "No",
        },
        "field_options": {
            "code": ("0", "1", "2", "3", "4"),
            "diplomacy": ("yes", "no"),
            "military_ops": ("yes", "no"),
        },
        "chunk_strategy": "wp",
        "alpha_rater_indices": (0, 2),  # Thomas Weil and Kyle only
    },
}


def extract_json_assignment(source: str, var_name: str) -> object:
    prefix = f"var {var_name}="
    start = source.find(prefix)
    if start < 0:
        raise ValueError(f"Could not find {var_name} assignment")
    start += len(prefix)
    while start < len(source) and source[start].isspace():
        start += 1
    if start >= len(source) or source[start] not in "[{":
        raise ValueError(f"{var_name} assignment does not start with JSON")

    opener = source[start]
    closer = "}" if opener == "{" else "]"
    depth = 0
    in_string = False
    escape = False
    for pos in range(start, len(source)):
        ch = source[pos]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return json.loads(source[start : pos + 1])
    raise ValueError(f"Could not parse {var_name} JSON assignment")


def extract_source_data(source: str, chunk_strategy: str | None = None) -> tuple[dict, dict, dict]:
    doc_texts = extract_json_assignment(source, "DOC_TEXTS")

    metadata = {}
    for match in re.finditer(
        r'<span class="doc-id">([^<]*)</span>\s*'
        r'(?:<span class="global-id">[^<]*</span>\s*)?'
        r'<span class="doc-prez">([^<]*)</span>\s*'
        r'<span class="doc-date">([^<]*)</span>\s*'
        r'<span class="doc-type">([^<]*)</span>',
        source,
        re.S,
    ):
        doc_id, president, date, doc_type = (html.unescape(v.strip()) for v in match.groups())
        metadata[doc_id] = {"president": president, "date": date, "type": doc_type}

    chunks: dict[str, dict[str, str]] = {}
    for match in re.finditer(
        r'<div class="seg seg-chunk"(?P<attrs>[^>]*)>.*?'
        r'<span class="seg-text">(?P<chunk_html>.*?)</span><span class="chunk-badge"',
        source,
        re.S,
    ):
        attrs = dict(re.findall(r'data-([a-zA-Z0-9_-]+)="([^"]*)"', match.group("attrs")))
        if chunk_strategy and attrs.get("strategy") != chunk_strategy:
            continue
        doc_id = attrs.get("doc")
        chunk_number = attrs.get("chunkn")
        if not doc_id or not chunk_number:
            continue
        chunk_html = match.group("chunk_html")
        chunk_text = re.sub(r"<[^>]+>", "", chunk_html)
        chunks.setdefault(doc_id, {})[chunk_number] = html.unescape(chunk_text).strip()

    return metadata, chunks, doc_texts


def load_results(config: dict) -> list[dict]:
    return [json.loads((config["results_dir"] / filename).read_text()) for filename in config["result_files"]]


def compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def field_value(raw: dict | None, field: str, mode: str, schema: str) -> str | None:
    if not raw or not raw.get("category"):
        if schema == "round2":
            return raw.get(field) if raw else None
        return None
    if field == "legal_effect" and raw["category"] != "policy":
        return None
    if field == "national_security" and raw.get("scope") != "foreign":
        return None
    if field == "emergency" and mode != "directive":
        return None
    return raw.get(field)


def compute_alphas(results: list[dict], metadata: dict, chunks: dict, config: dict) -> dict:
    fields = config["fields"]
    schema = config["schema"]
    rater_indices = config.get("alpha_rater_indices")
    alpha_results = [results[i] for i in rater_indices] if rater_indices is not None else results
    output = {}
    for mode, mode_fields in fields.items():
        units = []
        for doc_id in metadata:
            if mode == "directive":
                units.append((doc_id, None))
            else:
                units.extend((doc_id, chunk_number) for chunk_number in chunks.get(doc_id, {}))

        output[mode] = {}
        for field in mode_fields:
            values = []
            for result in alpha_results:
                row = []
                for doc_id, chunk_number in units:
                    doc = result.get(doc_id, {})
                    raw = (
                        doc.get("classification")
                        if chunk_number is None
                        else doc.get("wp_chunks", {}).get(chunk_number) or doc.get("chunks", {}).get(chunk_number)
                    )
                    row.append(field_value(raw, field, mode, schema))
                values.append(row)

            labels = sorted({value for row in values for value in row if value is not None})
            encoded = {label: index for index, label in enumerate(labels)}
            matrix = np.array(
                [[np.nan if value is None else encoded[value] for value in row] for row in values],
                dtype=float,
            )
            try:
                alpha = float(
                    krippendorff.alpha(
                        reliability_data=matrix,
                        level_of_measurement="nominal",
                    )
                )
            except (ValueError, ZeroDivisionError):
                alpha = math.nan
            output[mode][field] = alpha if math.isfinite(alpha) else None
    return output


def build_html(metadata: dict, chunks: dict, doc_texts: dict, results: list[dict], config: dict) -> str:
    payload = compact_json(
        {
            "config": {
                "label": config["label"],
                "schema": config["schema"],
                "fields": config["fields"],
                "fieldLabels": config["field_labels"],
                "valueLabels": config["value_labels"],
                "fieldOptions": config["field_options"],
            },
            "metadata": metadata,
            "chunks": chunks,
            "docTexts": doc_texts,
            "results": results,
            "alpha": compute_alphas(results, metadata, chunks, config),
        }
    )
    return TEMPLATE.replace("__PAYLOAD__", payload)


TEMPLATE = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Annotation agreement</title>
<style>
:root{--ink:#172033;--muted:#64748b;--line:#d9e1ea;--paper:#fff;--bg:#f4f6f8;--blue:#174ea6;--blue-soft:#e8f0fe;--good:#17643a;--good-bg:#e8f5ec;--bad:#a02727;--bad-bg:#fff0f0;--warn:#8a5a00;--warn-bg:#fff7df}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}button{font:inherit}.shell{max-width:1500px;margin:auto;padding:22px}.top{position:sticky;top:0;z-index:5;background:rgba(244,246,248,.97);padding:0 0 12px;border-bottom:1px solid var(--line)}h1{font-size:24px;margin:0 0 3px}.subtitle{color:var(--muted);margin:0 0 14px}.toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.toggle{display:inline-flex;border:1px solid #b8c4d1;border-radius:7px;overflow:hidden;background:white}.toggle button{border:0;border-right:1px solid #b8c4d1;background:white;padding:7px 13px;cursor:pointer}.toggle button:last-child{border-right:0}.toggle button.active{background:var(--blue);color:white}.check{display:flex;align-items:center;gap:7px;font-weight:650;margin-left:5px}.count{margin-left:auto;color:var(--muted);font-variant-numeric:tabular-nums}.stats{background:var(--paper);border:1px solid var(--line);border-radius:9px;margin:16px 0;padding:14px 16px}.stats summary{cursor:pointer;font-weight:750;font-size:15px}.stat-note{color:var(--muted);font-size:12px;margin:8px 0 10px}.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(245px,1fr));gap:10px}.stat-card{border:1px solid var(--line);border-radius:7px;padding:10px}.stat-card h3{font-size:13px;margin:0 0 7px}.stat-line{display:flex;justify-content:space-between;gap:12px;border-top:1px solid #edf1f5;padding:4px 0}.stat-line:first-of-type{border-top:0}.metric{font-variant-numeric:tabular-nums;font-weight:700}.documents{display:grid;gap:12px}.doc{background:var(--paper);border:1px solid var(--line);border-radius:9px;overflow:hidden}.doc>summary{cursor:pointer;list-style:none;padding:13px 15px;display:flex;gap:12px;align-items:baseline}.doc>summary::-webkit-details-marker{display:none}.doc-id{font-size:17px;font-weight:850;color:var(--blue);min-width:43px}.doc-title{font-weight:750}.doc-meta{color:var(--muted)}.status{margin-left:auto;border-radius:999px;padding:2px 9px;font-size:11px;font-weight:800;white-space:nowrap}.status.agree{color:var(--good);background:var(--good-bg)}.status.disagree{color:var(--bad);background:var(--bad-bg)}.status.incomplete,.status.custom{color:var(--warn);background:var(--warn-bg)}.doc-body{padding:0 15px 15px}.source{margin:0 0 12px;border-top:1px solid var(--line);padding-top:9px}.source summary{cursor:pointer;color:var(--blue);font-size:12px;font-weight:700}.source-text{white-space:pre-wrap;max-height:330px;overflow:auto;background:#f8fafc;border:1px solid var(--line);border-radius:6px;padding:10px;margin-top:7px;font:12px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace}.comparison{border:1px solid var(--line);border-radius:7px;overflow:auto}.chunk+.chunk{margin-top:10px}.chunk-head{display:flex;gap:10px;align-items:center;margin-bottom:5px}.chunk-number{font-weight:800;color:var(--blue)}.chunk-text{background:#f8fafc;border-left:3px solid #a7b8cb;padding:8px 10px;margin-bottom:6px;white-space:pre-wrap}.annotation-grid{display:grid;min-width:920px}.cell{padding:7px 9px;border-top:1px solid var(--line);border-left:1px solid var(--line)}.cell.head{border-top:0}.cell.field{border-left:0;background:#f8fafc;font-weight:700;color:#475569}.head{font-weight:800;background:#eef3f8}.value{display:block;padding:2px 5px;border-radius:4px;min-height:24px}.value.same{background:var(--good-bg);color:var(--good)}.value.diff{background:var(--bad-bg);color:var(--bad);font-weight:700}.value.missing{background:var(--warn-bg);color:var(--warn);font-style:italic}.value.na{color:#94a3b8}.custom-note{font-size:12px;color:var(--warn);font-weight:700}.empty{text-align:center;color:var(--muted);padding:50px 15px;background:white;border:1px solid var(--line);border-radius:9px}@media(max-width:750px){.shell{padding:12px}.count{width:100%;margin-left:0}.doc-meta{display:none}}.cell.gt{background:#f0f4ff}.head.gt{background:#dce8fb}.na-cell{opacity:.5}.gt-select{width:100%;font:inherit;font-size:13px;border:1px solid #b8c4d1;border-radius:4px;padding:3px 5px;background:white;cursor:pointer;color:inherit}.gt-select:disabled{background:#f1f5f9;color:var(--muted)}
</style>
</head>
<body>
<main class="shell">
  <section class="top">
    <h1>Annotation agreement</h1>
    <p class="subtitle"><span id="sample-label"></span> · <span id="annotator-count"></span> · missing ratings excluded from agreement</p>
    <div class="toolbar">
      <div class="toggle" aria-label="Comparison level">
        <button id="directive-mode" class="active" type="button">Directive level</button>
        <button id="chunk-mode" type="button">Sub-directive level</button>
      </div>
      <label class="check"><input id="hide-agreements" type="checkbox"> Hide agreements</label>
      <span class="count" id="visible-count"></span>
    </div>
  </section>
  <details class="stats">
    <summary>Agreement statistics</summary>
    <p class="stat-note">Unanimous uses only directives that are fully annotated. Pairwise Pairwise agreement is the percentage of all available annotator pairs that gave the same rating on a unit; each pair is counted whenever both annotators supplied that rating. Alpha is nominal Krippendorff’s α.</p>
    <div class="stats-grid" id="stats-grid"></div>
  </details>
  <section class="documents" id="documents"></section>
</main>
<script id="comparison-data" type="application/json">__PAYLOAD__</script>
<script>
(function(){
'use strict';
var payload=JSON.parse(document.getElementById('comparison-data').textContent);
var config=payload.config||{};
var results=payload.results;
var annotators=results.map(function(r){return r.annotator||'Unknown';});
var mode='directive';
var hideAgreements=false;
var FIELD_LABELS=config.fieldLabels||{};
var VALUE_LABELS=config.valueLabels||{};
var FIELD_OPTIONS=config.fieldOptions||{};
var SCHEMA=config.schema||'policy';
var GT_KEY='annotation-comparison-gt-'+SCHEMA+'-v1';
var groundTruth={};try{groundTruth=JSON.parse(localStorage.getItem(GT_KEY)||'{}');}catch(e){}
function gtKey(docId,chunkN){return chunkN==null||chunkN===''?docId:docId+'#'+chunkN;}
function gtEligible(docId,chunkN,field,currentMode){if(SCHEMA==='round2')return true;if(field==='category'||field==='scope')return true;if(field==='emergency')return currentMode==='directive';var gt=groundTruth[gtKey(docId,chunkN)]||{};if(field==='legal_effect')return gt.category==='policy';if(field==='national_security')return gt.scope==='foreign';return true;}
function handleGTChange(sel){var docId=sel.dataset.doc,chunkN=sel.dataset.chunk===''?null:sel.dataset.chunk,field=sel.dataset.field,value=sel.value||null;var key=gtKey(docId,chunkN);if(!groundTruth[key])groundTruth[key]={};if(value==null)delete groundTruth[key][field];else groundTruth[key][field]=value;if(SCHEMA!=='round2'){if(field==='category'&&value!=='policy')delete groundTruth[key].legal_effect;if(field==='scope'&&value!=='foreign')delete groundTruth[key].national_security;}localStorage.setItem(GT_KEY,JSON.stringify(groundTruth));updateGTCells(docId,chunkN);}
function updateGTCells(docId,chunkN){var attr=chunkN==null?'':chunkN;var sels=document.querySelectorAll('.gt-select[data-doc="'+CSS.escape(docId)+'"][data-chunk="'+CSS.escape(attr)+'"]');var gt=groundTruth[gtKey(docId,chunkN)]||{};sels.forEach(function(sel){var field=sel.dataset.field,elig=gtEligible(docId,chunkN,field,mode);sel.disabled=!elig;sel.closest('.cell').classList.toggle('na-cell',!elig);if(!elig)sel.value='';else sel.value=gt[field]||'';});}

function esc(value){return String(value==null?'':value).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
function docSort(a,b){var pa={EO:0,M:1,L:2,P:3};var ma=/^([A-Z]+)(\d+)$/.exec(a),mb=/^([A-Z]+)(\d+)$/.exec(b);if(!ma||!mb)return a.localeCompare(b);return (pa[ma[1]]-pa[mb[1]])||(+ma[2]-+mb[2]);}
function chunkSort(a,b){return (+a)-(+b);}
function fieldsFor(currentMode){return (config.fields&&config.fields[currentMode])||[];}
function rawRating(docId,chunkNumber,raterIndex){var d=results[raterIndex][docId]||{};return chunkNumber==null?d.classification:((d.wp_chunks||{})[chunkNumber]||(d.chunks||{})[chunkNumber]);}
function normalized(raw,currentMode){
  if(SCHEMA==='round2'){var out2={};fieldsFor(currentMode).forEach(function(f){out2[f]=raw&&raw[f]!=null?raw[f]:null;});return raw?out2:null;}
  if(!raw||!raw.category)return null;
  var out={category:raw.category,legal_effect:raw.category==='policy'?(raw.legal_effect||null):null,scope:raw.scope||null,national_security:raw.scope==='foreign'?(raw.national_security||null):null};
  if(currentMode==='directive')out.emergency=raw.emergency||null;
  return out;
}
function fieldEligible(raw,field,currentMode){
  if(SCHEMA==='round2')return true;
  if(field==='category'||field==='scope')return true;
  if(field==='emergency')return currentMode==='directive';
  if(!raw||!raw.category)return false;
  if(field==='legal_effect')return raw.category==='policy';
  if(field==='national_security')return raw.scope==='foreign';
  return true;
}
function fieldValue(raw,field,currentMode){return fieldEligible(raw,field,currentMode)&&raw&&raw[field]!=null?raw[field]:null;}
function complete(raw,currentMode){
  if(SCHEMA==='round2')return !!raw&&fieldsFor(currentMode).every(function(field){return raw[field]!=null&&raw[field]!=='';});
  if(!raw||!raw.category||!raw.scope)return false;
  if(raw.category==='policy'&&!raw.legal_effect)return false;
  if(raw.scope==='foreign'&&!raw.national_security)return false;
  return currentMode!=='directive'||!!raw.emergency;
}
function exactValue(raw,currentMode){return complete(raw,currentMode)?JSON.stringify(normalized(raw,currentMode)):null;}
function statusFor(raws,currentMode){var vals=raws.map(function(r){return exactValue(r,currentMode);});if(vals.some(function(v){return v==null;}))return 'incomplete';return vals.every(function(v){return v===vals[0];})?'agree':'disagree';}
function label(value){return value==null?'Missing':(VALUE_LABELS[value]||value);}
function percent(n,d){return d?((100*n/d).toFixed(1)+'%'):'N/A';}

function unitsFor(currentMode){
  var ids=Object.keys(payload.metadata).sort(docSort),units=[];
  if(currentMode==='directive')ids.forEach(function(id){units.push({id:id,raws:results.map(function(_,i){return rawRating(id,null,i);})});});
  else ids.forEach(function(id){Object.keys(payload.chunks[id]||{}).sort(chunkSort).forEach(function(n){units.push({id:id+'#'+n,raws:results.map(function(_,i){return rawRating(id,n,i);})});});});
  return units;
}
function agreement(values){
  var all=values.every(function(v){return v!=null;}),unanimous=all&&values.every(function(v){return v===values[0];});
  var pairs=0,agree=0;for(var i=0;i<values.length;i++)for(var j=i+1;j<values.length;j++)if(values[i]!=null&&values[j]!=null){pairs++;if(values[i]===values[j])agree++;}
  return {all:all,unanimous:unanimous,pairs:pairs,pairAgree:agree};
}
function calculateStats(currentMode){
  var units=unitsFor(currentMode),fields=fieldsFor(currentMode),cards=[];
  var exactMatrix=units.map(function(u){return u.raws.map(function(r){return exactValue(r,currentMode);});});
  var exactAgg={unanimous:0,complete:0,pairAgree:0,pairs:0};
  exactMatrix.forEach(function(row){var a=agreement(row);if(a.all){exactAgg.complete++;if(a.unanimous)exactAgg.unanimous++;}exactAgg.pairAgree+=a.pairAgree;exactAgg.pairs+=a.pairs;});
  cards.push({name:'Exact annotation',unanimous:percent(exactAgg.unanimous,exactAgg.complete),pairwise:percent(exactAgg.pairAgree,exactAgg.pairs),coverageText:results.map(function(_,i){return exactMatrix.filter(function(row){return row[i]!=null;}).length+'/'+units.length;}).join(' · ')});
  fields.forEach(function(field){
    var matrix=units.map(function(u){return u.raws.map(function(r){return fieldValue(r,field,currentMode);});});
    var eligible=results.map(function(){return 0;}),rated=results.map(function(){return 0;}),agg={unanimous:0,complete:0,pairAgree:0,pairs:0};
    units.forEach(function(u,unitIndex){u.raws.forEach(function(r,i){if(fieldEligible(r,field,currentMode)){eligible[i]++;if(matrix[unitIndex][i]!=null)rated[i]++;}});var a=agreement(matrix[unitIndex]);if(a.all){agg.complete++;if(a.unanimous)agg.unanimous++;}agg.pairAgree+=a.pairAgree;agg.pairs+=a.pairs;});
    cards.push({name:FIELD_LABELS[field],unanimous:percent(agg.unanimous,agg.complete),pairwise:percent(agg.pairAgree,agg.pairs),coverageText:rated.map(function(n,i){return n+'/'+eligible[i];}).join(' · '),alpha:payload.alpha[currentMode][field]});
  });
  return {units:units.length,cards:cards};
}
function renderStats(){
  var stats=calculateStats(mode),out='';
  stats.cards.forEach(function(c){out+='<article class="stat-card"><h3>'+esc(c.name)+'</h3><div class="stat-line"><span>Unanimous</span><span class="metric">'+c.unanimous+'</span></div><div class="stat-line"><span>Pairwise</span><span class="metric">'+c.pairwise+'</span></div>'+('alpha' in c?'<div class="stat-line"><span>Krippendorff’s α</span><span class="metric">'+(c.alpha==null?'N/A':c.alpha.toFixed(3))+'</span></div>':'')+'<div class="stat-line"><span title="'+esc(annotators.join(' · '))+'">Coverage</span><span class="metric" title="'+esc(annotators.join(' · '))+'">'+esc(c.coverageText)+'</span></div></article>';});
  document.getElementById('stats-grid').innerHTML=out;
}
function annotationGrid(raws,currentMode,docId,chunkN){
  var fields=fieldsFor(currentMode),chunkAttr=chunkN==null?'':chunkN;
  var out='<div class="annotation-grid" style="grid-template-columns:126px repeat('+(annotators.length+1)+',minmax(190px,1fr))"><div class="cell head field">Field</div>';
  annotators.forEach(function(name){out+='<div class="cell head">'+esc(name)+'</div>';});
  out+='<div class="cell head gt">Ground Truth</div>';
  var gt=groundTruth[gtKey(docId,chunkN)]||{};
  fields.forEach(function(field){var vals=raws.map(function(r){return fieldValue(r,field,currentMode);}),available=vals.filter(function(v){return v!=null;}),different=(new Set(available)).size>1;out+='<div class="cell field">'+esc(FIELD_LABELS[field])+'</div>';vals.forEach(function(value,i){var eligible=fieldEligible(raws[i],field,currentMode),cls=!eligible?'na':value==null?'missing':different?'diff':available.length===annotators.length?'same':'';out+='<div class="cell"><span class="value '+cls+'">'+(eligible?esc(label(value)):'N/A')+'</span></div>';});var elig=gtEligible(docId,chunkN,field,currentMode);out+='<div class="cell gt'+(elig?'':' na-cell')+'">';out+='<select class="gt-select" data-doc="'+esc(docId)+'" data-chunk="'+esc(chunkAttr)+'" data-field="'+esc(field)+'"'+(elig?'':' disabled')+'><option value="">— select —</option>';(FIELD_OPTIONS[field]||[]).forEach(function(opt){out+='<option value="'+esc(opt)+'"'+(gt[field]===opt?' selected':'')+'>'+esc(label(opt))+'</option>';});out+='</select>';out+='</div>';});
  return out+'</div>';
}
function sourceDetails(id){return '<details class="source"><summary>Document text</summary><div class="source-text">'+esc(payload.docTexts[id]||'')+'</div></details>';}
function docSummary(id,status,extra){var m=payload.metadata[id]||{};return '<summary><span class="doc-id">'+esc(id)+'</span><span class="doc-title">'+esc(m.president||'')+'</span><span class="doc-meta">'+esc(m.date||'')+' · '+esc((m.type||'').replaceAll('_',' '))+'</span><span class="status '+status+'">'+esc(extra||(status==='agree'?'Agreement':status==='disagree'?'Disagreement':'Incomplete'))+'</span></summary>';}
function directiveDoc(id){var raws=results.map(function(_,i){return rawRating(id,null,i);}),status=statusFor(raws,'directive');if(hideAgreements&&status==='agree')return '';return '<details class="doc" data-status="'+status+'" open>'+docSummary(id,status)+ '<div class="doc-body">'+sourceDetails(id)+'<div class="comparison">'+annotationGrid(raws,'directive',id,null)+'</div></div></details>';}
function customRows(id){
  var rows=[];results.forEach(function(result,i){((result[id]||{}).annotations||[]).forEach(function(a,index){if(a.label!=='order_action')return;var raws=results.map(function(){return null;});raws[i]=a.classification||null;var text=(payload.docTexts[id]||'').slice(a.start,a.end);rows.push('<section class="chunk" data-status="custom"><div class="chunk-head"><span class="chunk-number">Custom span</span><span class="status custom">'+esc(annotators[i])+'</span></div><div class="custom-note">Character range '+a.start+'–'+a.end+'; not inferred to match numbered chunks</div><div class="chunk-text">'+esc(text)+'</div><div class="comparison">'+annotationGrid(raws,'chunk',id,'c'+a.start)+'</div></section>');});});return rows;
}
function chunkDoc(id){
  var rows=[];Object.keys(payload.chunks[id]||{}).sort(chunkSort).forEach(function(n){var raws=results.map(function(_,i){return rawRating(id,n,i);}),status=statusFor(raws,'chunk');if(hideAgreements&&status==='agree')return;rows.push('<section class="chunk" data-status="'+status+'"><div class="chunk-head"><span class="chunk-number">Directive #'+esc(n)+'</span><span class="status '+status+'">'+(status==='agree'?'Agreement':status==='disagree'?'Disagreement':'Incomplete')+'</span></div><div class="chunk-text">'+esc(payload.chunks[id][n])+'</div><div class="comparison">'+annotationGrid(raws,'chunk',id,n)+'</div></section>');});
  rows=rows.concat(customRows(id));if(!rows.length)return '';var docStatus=rows.some(function(r){return r.indexOf('data-status="disagree"')>=0;})?'disagree':rows.some(function(r){return r.indexOf('data-status="incomplete"')>=0||r.indexOf('data-status="custom"')>=0;})?'incomplete':'agree';return '<details class="doc" data-status="'+docStatus+'" open>'+docSummary(id,docStatus,rows.length+' row'+(rows.length===1?'':'s'))+'<div class="doc-body">'+rows.join('')+'</div></details>';
}
function render(){
  renderStats();var ids=Object.keys(payload.metadata).sort(docSort),htmlOut=ids.map(mode==='directive'?directiveDoc:chunkDoc).filter(Boolean);document.getElementById('documents').innerHTML=htmlOut.length?htmlOut.join(''):'<div class="empty">No comparison rows match this filter.</div>';document.getElementById('visible-count').textContent=htmlOut.length+' of '+ids.length+' documents shown';
  document.getElementById('directive-mode').classList.toggle('active',mode==='directive');document.getElementById('chunk-mode').classList.toggle('active',mode==='chunk');
}
document.getElementById('directive-mode').addEventListener('click',function(){mode='directive';render();});
document.getElementById('chunk-mode').addEventListener('click',function(){mode='chunk';render();});
document.getElementById('hide-agreements').addEventListener('change',function(e){hideAgreements=e.target.checked;render();});
document.addEventListener('change',function(e){if(e.target.classList.contains('gt-select'))handleGTChange(e.target);});
window.__comparison={calculateStats:calculateStats,statusFor:statusFor,normalized:normalized};
document.getElementById('sample-label').textContent=config.label||'Sample';
document.getElementById('annotator-count').textContent=annotators.length+' annotators';
render();
})();
</script>
</body>
</html>
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        choices=sorted(DATASETS),
        default="sample100",
        help="dataset configuration to build",
    )
    args = parser.parse_args()
    config = DATASETS[args.dataset]

    metadata, chunks, doc_texts = extract_source_data(
        config["source_viewer"].read_text(),
        chunk_strategy=config["chunk_strategy"],
    )
    output = config["output"]
    output.write_text(build_html(metadata, chunks, doc_texts, load_results(config), config))
    print(f"Wrote {output.relative_to(ROOT)} ({output.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
