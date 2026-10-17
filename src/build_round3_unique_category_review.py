#!/usr/bin/env python3
"""Build per-annotator review of minority Round 3 sub-directive codes."""

from __future__ import annotations

import json
from pathlib import Path

from build_disagreement_review import VALUE_LABELS, extract_source_data
from build_round3_disagreement_review import ROUND3_DIR, SOURCE_VIEWER, load_results


OUTPUT = ROUND3_DIR / "unique-category-review.html"
GROUND_TRUTH_OUTPUT = ROUND3_DIR / "unique-category-review-with-ground-truth.html"
REVIEW_EXPORTS = [
    ROUND3_DIR / "round3-minority-review-claire.json",
    ROUND3_DIR / "round3-minority-review-kylem.json",
    ROUND3_DIR / "round3-minority-review-thomas-weil.json",
]
# Provisional adjudications recorded in Round 3/disagreement-notes.md.
ALL_THREE_CODES = {("EO25", "2"): "0", ("M20", "2"): "2"}


def minority_units(chunks: dict, results: list[dict]) -> list[dict]:
    """Return complete sub-directive votes where one annotator is in the minority."""
    groups = []
    for index, result in enumerate(results):
        units = []
        for doc_id, doc_chunks in chunks.items():
            for chunk_number in doc_chunks:
                codes = [
                    (other.get(doc_id, {}).get("wp_chunks", {}).get(chunk_number) or {}).get("code")
                    for other in results
                ]
                other_codes = [code for other_index, code in enumerate(codes) if other_index != index]
                if (
                    codes[index] is not None
                    and len(other_codes) == 2
                    and other_codes[0] is not None
                    and other_codes[0] == other_codes[1]
                    and codes[index] != other_codes[0]
                ):
                    units.append({
                        "docId": doc_id,
                        "chunkNumber": chunk_number,
                        "codes": codes,
                        "originalCode": codes[index],
                        "majorityCode": other_codes[0],
                    })
        groups.append({
            "label": result.get("annotator", f"Annotator {index + 1}"),
            "annotatorIndex": index,
            "units": units,
        })
    return groups


def reviewed_units(groups: list[dict], reviews: list[dict]) -> list[dict]:
    """Collect completed minority reviews, including votes the annotator retained."""
    units = []
    reviews_by_annotator = {review["annotator"]: review for review in reviews}
    for group in groups:
        review = reviews_by_annotator[group["label"]]
        originals = {(unit["docId"], unit["chunkNumber"]): unit for unit in group["units"]}
        for record in review["records"]:
            original = originals.get((record["round_id"], record["chunk_number"]))
            if (
                original is None
                or record["original_code"] != original["originalCode"]
                or record["majority_code"] != original["majorityCode"]
            ):
                raise ValueError(f"Review export does not match Round 3 votes: {record}")
            if record["reviewed_code"] is not None:
                units.append({
                    **original,
                    "reviewedBy": group["label"],
                    "minorityIndex": group["annotatorIndex"],
                    "groundTruthCode": record["reviewed_code"],
                })
    return sorted(units, key=lambda unit: (unit["docId"], int(unit["chunkNumber"])))


def all_three_units(chunks: dict, results: list[dict]) -> list[dict]:
    """Collect sub-directives with three distinct, complete category codes."""
    units = []
    for doc_id, doc_chunks in chunks.items():
        for chunk_number in doc_chunks:
            codes = [
                (result.get(doc_id, {}).get("wp_chunks", {}).get(chunk_number) or {}).get("code")
                for result in results
            ]
            if len(codes) == 3 and all(code is not None for code in codes) and len(set(codes)) == 3:
                units.append({
                    "docId": doc_id,
                    "chunkNumber": chunk_number,
                    "codes": codes,
                    "allThree": True,
                    "groundTruthCode": ALL_THREE_CODES.get((doc_id, chunk_number)),
                })
    return units


def build_html(metadata: dict, chunks: dict, doc_texts: dict, results: list[dict],
               reviews: list[dict] | None = None) -> str:
    groups = minority_units(chunks, results)
    if reviews is not None:
        ground_truth_units = reviewed_units(groups, reviews) + all_three_units(chunks, results)
        groups.append({"label": "Ground Truth", "groundTruth": True,
                       "units": sorted(ground_truth_units, key=lambda unit: (unit["docId"], int(unit["chunkNumber"])))})
    selected_docs = {unit["docId"] for group in groups for unit in group["units"]}
    payload = {
        "annotators": [result.get("annotator", f"Annotator {i + 1}") for i, result in enumerate(results)],
        "groups": groups,
        "metadata": {doc_id: metadata.get(doc_id, {}) for doc_id in selected_docs},
        "docTexts": {doc_id: doc_texts.get(doc_id, "") for doc_id in selected_docs},
        "chunks": chunks,
        "valueLabels": {code: VALUE_LABELS[code] for code in ("0", "1", "2", "3", "4")},
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    description = (
        "Each annotator tab shows sub-directives where they chose a different code while the other two agreed. "
        "Ground Truth shows all completed minority reviews and the three-way code disagreements. You can change the ground-truth code where the minority reviewer kept a different code or where all three differed."
        if reviews is not None else
        "Each tab contains only sub-directives where that annotator chose a different code while the other two annotators agreed. Choose the code you think the sub-directive should receive."
    )
    return TEMPLATE.replace("__PAYLOAD__", encoded).replace("__DESCRIPTION__", description)


def main() -> None:
    metadata, chunks, doc_texts = extract_source_data(SOURCE_VIEWER.read_text())
    results = load_results()
    groups = minority_units(chunks, results)
    OUTPUT.write_text(build_html(metadata, chunks, doc_texts, results))
    print(f"Wrote {OUTPUT.relative_to(Path.cwd())}")
    reviews = [json.loads(path.read_text()) for path in REVIEW_EXPORTS]
    GROUND_TRUTH_OUTPUT.write_text(build_html(metadata, chunks, doc_texts, results, reviews))
    print(f"Wrote {GROUND_TRUTH_OUTPUT.relative_to(Path.cwd())}")
    for group in groups:
        print(f"{group['label']}: {len(group['units'])} minority sub-directives")


TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Minority Sub-directive Review — Round 3</title>
<style>
:root{--blue:#1d4ed8;--line:#dbe2ea;--muted:#64748b;--paper:#fff;--bg:#f5f7fa;--good:#166534;--good-bg:#dcfce7;--bad:#991b1b;--bad-bg:#fee2e2}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:#172033;font:14px/1.45 system-ui,sans-serif}.top{position:sticky;top:0;z-index:10;padding:14px 18px 0;background:rgba(245,247,250,.98);border-bottom:1px solid var(--line)}h1{font-size:21px;margin:0 0 4px}.explain{margin:0 0 12px;color:var(--muted)}.toolbar{display:flex;align-items:center;gap:12px;margin-bottom:10px}.export{margin-left:auto;border:0;border-radius:6px;padding:7px 11px;background:var(--blue);color:white;font-weight:700;cursor:pointer}.progress{color:var(--muted);font-variant-numeric:tabular-nums}.tabs{display:flex;gap:2px}.tab{border:0;border-bottom:3px solid transparent;padding:7px 13px;background:none;color:var(--muted);font-weight:700;cursor:pointer}.tab.active{border-color:var(--blue);color:var(--blue)}main{max-width:1200px;margin:auto;padding:16px}.card{background:var(--paper);border:1px solid var(--line);border-radius:8px;margin-bottom:14px;overflow:hidden}.heading{display:flex;align-items:baseline;gap:10px;padding:12px 15px;border-bottom:1px solid var(--line)}.unit{font-size:17px;font-weight:850;color:var(--blue)}.meta{color:var(--muted)}.body{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(310px,1fr);gap:18px;padding:15px}.chunk{white-space:pre-wrap;padding:11px;border-left:4px solid #93c5fd;background:#f8fafc;font-family:ui-monospace,monospace;font-size:12px;line-height:1.6}.votes{display:grid;gap:6px;margin-bottom:15px}.vote{display:flex;justify-content:space-between;gap:12px;padding:7px 9px;border-radius:5px;background:#f1f5f9}.vote.minority{background:var(--bad-bg);color:var(--bad);font-weight:700}.vote.majority{background:var(--good-bg);color:var(--good)}label{display:block;font-weight:750;margin-bottom:5px}select{width:100%;padding:8px;border:1px solid #94a3b8;border-radius:5px;background:white;font:inherit}.saved{margin-top:6px;color:var(--good);font-size:12px;min-height:18px}.context{margin-top:12px}.context summary{cursor:pointer;color:var(--blue);font-weight:650}.full{white-space:pre-wrap;max-height:330px;overflow:auto;margin-top:7px;padding:10px;background:#f8fafc;border:1px solid var(--line);font:11px/1.55 ui-monospace,monospace}.empty{padding:50px;text-align:center;color:var(--muted)}@media(max-width:750px){.body{grid-template-columns:1fr}.top{position:static}.toolbar{flex-wrap:wrap}.export{margin-left:0}}
</style></head><body>
<header class="top"><h1>Minority Sub-directive Review — Round 3</h1><p class="explain">__DESCRIPTION__</p><div class="toolbar"><span class="progress" id="progress"></span><button class="export" id="export" type="button">Export this annotator’s review</button></div><nav class="tabs" id="tabs"></nav></header>
<main id="content"></main><script id="payload" type="application/json">__PAYLOAD__</script>
<script>(function(){'use strict';
var P=JSON.parse(document.getElementById('payload').textContent),active=0,key='round3-minority-subdirective-review-v1',groundTruthKey='round3-ground-truth-review-v1',answers={},groundTruthAnswers={};try{answers=JSON.parse(localStorage.getItem(key)||'{}')}catch(e){}try{groundTruthAnswers=JSON.parse(localStorage.getItem(groundTruthKey)||'{}')}catch(e){}
function esc(v){return String(v==null?'':v).replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}function unitKey(g,u){return g.annotatorIndex+'|'+u.docId+'|'+u.chunkNumber}function gtKey(u){return u.docId+'|'+u.chunkNumber}function gtCode(u){return(groundTruthAnswers[gtKey(u)]||{}).code||u.groundTruthCode||''}function label(code){return P.valueLabels[code]||code}
function renderTabs(){document.getElementById('tabs').innerHTML=P.groups.map(function(g,i){return'<button class="tab'+(i===active?' active':'')+'" data-i="'+i+'" type="button">'+esc(g.label)+' ('+g.units.length+')</button>'}).join('')}
function options(selected,allowBlank){var out=allowBlank?'<option value="">— choose category —</option>':'';Object.keys(P.valueLabels).forEach(function(code){out+='<option value="'+code+'"'+(selected===code?' selected':'')+'>'+esc(label(code))+'</option>'});return out}
function card(g,u){var m=P.metadata[u.docId]||{},k=unitKey(g,u),chosen=(answers[k]||{}).reviewedCode||'',minority=g.groundTruth?u.minorityIndex:g.annotatorIndex;var votes=u.codes.map(function(code,i){return'<div class="vote '+(u.allThree?'':i===minority?'minority':'majority')+'"><span>'+esc(P.annotators[i])+'</span><span>'+esc(label(code))+'</span></div>'}).join(''),outcome=u.allThree?'Three-way disagreement · provisional code from notes':esc(u.reviewedBy)+' · '+(u.groundTruthCode===u.majorityCode?'Changed to majority':'Kept original'),gtEdit=groundTruthAnswers[gtKey(u)],gtStatus=(gtEdit?'Saved locally · ':'')+outcome,gtDecision=!u.allThree&&u.groundTruthCode===u.majorityCode?'<div class="vote majority">'+esc(label(u.groundTruthCode))+'</div>':'<select data-ground-truth-key="'+esc(gtKey(u))+'">'+options(gtCode(u),!u.groundTruthCode)+'</select>',decision=g.groundTruth?'<label>Ground truth category</label>'+gtDecision+'<div class="saved">'+gtStatus+'</div>':'<label for="decision-'+esc(k)+'">Your reviewed category</label><select id="decision-'+esc(k)+'" data-key="'+esc(k)+'">'+options(chosen,true)+'</select><div class="saved">'+(chosen?'Saved':'')+'</div>';return'<article class="card"><div class="heading"><span class="unit">'+esc(u.docId)+' · Sub-directive '+esc(u.chunkNumber)+'</span><span class="meta">'+esc(m.president||'')+' · '+esc(m.date||'')+' · '+esc((m.type||'').replace(/_/g,' '))+'</span></div><div class="body"><div><div class="chunk">'+esc((P.chunks[u.docId]||{})[u.chunkNumber]||'')+'</div><details class="context"><summary>Show full directive context</summary><div class="full">'+esc(P.docTexts[u.docId]||'')+'</div></details></div><div><div class="votes">'+votes+'</div>'+decision+'</div></div></article>'}
function updateProgress(){var g=P.groups[active];if(g.groundTruth){var three=g.units.filter(function(u){return u.allThree}).length;document.getElementById('progress').textContent=(g.units.length-three)+' reviewed + '+three+' three-way';return}var done=g.units.filter(function(u){return(answers[unitKey(g,u)]||{}).reviewedCode}).length;document.getElementById('progress').textContent=done+' of '+g.units.length+' reviewed'}
function render(){var g=P.groups[active];renderTabs();document.getElementById('export').textContent=g.groundTruth?'Export ground truth':'Export this annotator’s review';document.getElementById('content').innerHTML=g.units.length?g.units.map(function(u){return card(g,u)}).join(''):'<div class="empty">No minority sub-directives for this annotator.</div>';updateProgress()}
document.getElementById('tabs').addEventListener('click',function(e){var b=e.target.closest('[data-i]');if(b){active=+b.dataset.i;render()}});document.getElementById('content').addEventListener('change',function(e){var s=e.target;if(s.matches('select[data-ground-truth-key]')){var g=P.groups[active],u=g.units.find(function(unit){return gtKey(unit)===s.dataset.groundTruthKey});if(!s.value||s.value===u.groundTruthCode)delete groundTruthAnswers[gtKey(u)];else groundTruthAnswers[gtKey(u)]={code:s.value,editedAt:new Date().toISOString()};localStorage.setItem(groundTruthKey,JSON.stringify(groundTruthAnswers));s.nextElementSibling.textContent=(groundTruthAnswers[gtKey(u)]?'Saved locally · ':'')+(u.allThree?'Three-way disagreement · provisional code from notes':u.reviewedBy+' · Kept original');return}if(!s.matches('select[data-key]'))return;if(s.value)answers[s.dataset.key]={reviewedCode:s.value,reviewedAt:new Date().toISOString()};else delete answers[s.dataset.key];localStorage.setItem(key,JSON.stringify(answers));s.nextElementSibling.textContent=s.value?'Saved':'';updateProgress()});
document.getElementById('export').addEventListener('click',function(){var g=P.groups[active],records,out,name;if(g.groundTruth){records=g.units.map(function(u){var edit=groundTruthAnswers[gtKey(u)]||{};return{round_id:u.docId,chunk_number:u.chunkNumber,disagreement_type:u.allThree?'all_three':'minority',reviewed_by:u.reviewedBy||null,original_code:u.originalCode||null,majority_code:u.majorityCode||null,reviewed_code:u.groundTruthCode||null,ground_truth_code:gtCode(u)||null,ground_truth_edited_at:edit.editedAt||null}});out={schema:'round3-ground-truth-review',schema_version:1,exported_at:new Date().toISOString(),records:records};name='round3-ground-truth-review.json'}else{records=g.units.map(function(u){var a=answers[unitKey(g,u)]||{};return{annotator:g.label,round_id:u.docId,chunk_number:u.chunkNumber,original_code:u.originalCode,majority_code:u.majorityCode,reviewed_code:a.reviewedCode||null,reviewed_at:a.reviewedAt||null}});out={schema:'round3-minority-subdirective-review',schema_version:1,exported_at:new Date().toISOString(),annotator:g.label,records:records};name='round3-minority-review-'+g.label.toLowerCase().replace(/[^a-z0-9]+/g,'-')+'.json'}var blob=new Blob([JSON.stringify(out,null,2)+'\n'],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();URL.revokeObjectURL(url)});render()})();</script></body></html>'''


if __name__ == "__main__":
    main()
