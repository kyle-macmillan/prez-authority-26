#!/usr/bin/env python3
"""Build a blind, readable HTML review of unique top candidates."""

from __future__ import annotations

import argparse
import csv
import html
import json
import random
import re
from collections import defaultdict
from pathlib import Path

from segmenter import _get_ordering_re
from validate_function_profiles import _read_jsonl


ROOT = Path(__file__).resolve().parents[1]


def escaped(value: object) -> str:
    return html.escape(str(value or ""))


def document_text(document: dict) -> str:
    """Return the fullest locally retained text used by the parent pipeline."""
    return str(document.get("cleaned_masked_text") or "")


def highlighted_text(document: dict, segments: list[str]) -> str:
    """Escape full text and mark source-exact operative segments."""
    text = document_text(document)
    spans = []
    for segment in segments:
        tokens = re.split(r"\s+", segment.strip())
        if not tokens:
            continue
        match = re.search(r"\s+".join(map(re.escape, tokens)), text, flags=re.I)
        if match:
            spans.append(match.span())
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    ordering_re = _get_ordering_re(extended=True)

    def render_triggers(value: str) -> str:
        pieces, trigger_cursor = [], 0
        for trigger in ordering_re.finditer(value):
            pieces.extend((escaped(value[trigger_cursor:trigger.start()]),
                           '<strong class="operative-trigger">',
                           escaped(trigger.group(0)), "</strong>"))
            trigger_cursor = trigger.end()
        pieces.append(escaped(value[trigger_cursor:]))
        return "".join(pieces)

    output, cursor = [], 0
    for start, end in merged:
        output.extend((escaped(text[cursor:start]), '<mark class="operative">',
                       render_triggers(text[start:end]), "</mark>"))
        cursor = end
    output.append(escaped(text[cursor:]))
    return "".join(output)


def source_link(document: dict) -> str:
    url = escaped(document.get("url"))
    return f'<a class="source-link" href="{url}" target="_blank" rel="noopener">Open original source ↗</a>' if url else ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--snapshot-dir", type=Path,
        default=ROOT / "data/parent_analysis/function_parent_pilot/provisional",
    )
    parser.add_argument(
        "--input-dir", type=Path, default=ROOT / "data/parent_analysis_full",
    )
    args = parser.parse_args()
    manifest = json.loads((args.snapshot_dir / "snapshot_manifest.json").read_text())
    sample = {}
    with (args.snapshot_dir / "sampled_children.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            sample[row["document_id"]] = row

    top = defaultdict(lambda: defaultdict(list))
    ranking_files = {
        "deterministic": "deterministic_rankings.jsonl",
        "qwen": "qwen_rankings.jsonl",
        "gemini_search": "gemini_rankings.jsonl",
        "gemini_search_thinking_medium": "gemini_thinking_medium_rankings.jsonl",
    }
    for method, filename in ranking_files.items():
        path = args.snapshot_dir / filename
        if path.exists():
            for row in _read_jsonl(path):
                if int(row["rank"]) == 1:
                    top[row["child_id"]][row["parent_id"]].append(method)

    gemini_decisions = defaultdict(dict)
    decision_files = {
        "Gemini (thinking off)": "gemini_decisions.jsonl",
        "Gemini (thinking medium)": "gemini_thinking_medium_decisions.jsonl",
    }
    for label, filename in decision_files.items():
        path = args.snapshot_dir / filename
        if path.exists():
            for row in _read_jsonl(path):
                gemini_decisions[str(row["child_id"])][label] = row

    wanted = set(sample) | {parent_id for parents in top.values() for parent_id in parents}
    documents = {}
    with (args.input_dir / "directive_similarity_documents.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            document_id = str(row["document_id"])
            if document_id in wanted:
                documents[document_id] = row
    operative_segments = defaultdict(list)
    with (args.input_dir / "directive_operative_segments.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            document_id = str(row["document_id"])
            if document_id in wanted:
                operative_segments[document_id].append(str(row["text"]))

    sections = []
    for child_number, child_id in enumerate(sorted(top, key=int), 1):
        child = documents[child_id]
        candidates = list(top[child_id])
        random.Random(f"{manifest['snapshot_hash']}:{child_id}").shuffle(candidates)
        candidate_labels = {
            parent_id: label for label, parent_id in enumerate(candidates, 1)
        }
        cards, selectors = [], []
        for label, parent_id in enumerate(candidates, 1):
            parent = documents[parent_id]
            active = " active" if label == 1 else ""
            selectors.append(f"""<button type="button" class="candidate-tab{active}" data-target="candidate-{child_id}-{parent_id}" aria-selected="{'true' if label == 1 else 'false'}"><span>Candidate {label}</span><strong>{escaped(parent['title'])}</strong><small>{escaped(parent['date'])}</small></button>""")
            cards.append(f"""
            <article class="candidate-card{active}" id="candidate-{child_id}-{parent_id}">
              <div class="candidate-heading">
                <div><span class="candidate-number">Candidate {label}</span>
                  <h3>{escaped(parent['title'])}</h3>
                  <p class="metadata">{escaped(parent['document_type']).replace('_', ' ').title()} · {escaped(parent['date'])}</p>
                </div>
                {source_link(parent)}
              </div>
              <details class="document-panel" open>
                <summary>Candidate directive text</summary>
                <div class="document-text">{highlighted_text(parent, operative_segments[parent_id])}</div>
              </details>
            </article>""")

        decision_options = "".join(
            f'<option value="{parent_id}">Candidate {label}: {escaped(documents[parent_id]["title"])}</option>'
            for label, parent_id in enumerate(candidates, 1)
        )

        assessment_rows = []
        for method_label, decision in gemini_decisions.get(child_id, {}).items():
            parent_id = str(decision["best_candidate_id"])
            candidate_number = candidate_labels.get(parent_id)
            candidate_name = (
                f"Candidate {candidate_number}"
                if candidate_number is not None else f"document {parent_id}"
            )
            score = float(decision["acceptance_score"])
            if decision["decision"] == "candidate":
                verdict = (
                    f'<strong class="gemini-yes">Yes — {candidate_name}</strong>'
                )
            else:
                verdict = (
                    f'<strong class="gemini-no">No plausible parent</strong>'
                    f'<span class="gemini-best">Best retrieved: {candidate_name}</span>'
                )
            assessment_rows.append(
                f'<div class="gemini-row"><span>{escaped(method_label)}</span>'
                f'<div>{verdict}<small>Plausibility {score:.0%}</small></div></div>'
            )
        gemini_panel = (
            '<aside class="gemini-assessment"><h3>Gemini parent assessment</h3>'
            + "".join(assessment_rows) + "</aside>"
            if assessment_rows else ""
        )

        sections.append(f"""
        <section class="child-section" id="child-{escaped(sample[child_id]['sample_id'])}">
          <div class="child-heading">
            <div><span class="eyebrow">Case {child_number} of {len(top)} · {escaped(sample[child_id]['sample_id'])}</span>
              <h2>{escaped(child['title'])}</h2>
              <p class="metadata">{escaped(child['document_type']).replace('_', ' ').title()} · {escaped(child['date'])}</p>
            </div>
            {source_link(child)}
          </div>
          <details class="document-panel child-document" open>
            <summary>Child directive text</summary>
            <div class="document-text">{highlighted_text(child, operative_segments[child_id])}</div>
          </details>
          <p class="highlight-key"><mark class="operative">Highlighted text with a <strong class="operative-trigger">bold trigger phrase</strong></mark> is an operative segment identified by the preprocessing pipeline.</p>
          {gemini_panel}
          <div class="candidate-workspace"><div class="candidate-stage">{''.join(cards)}</div><nav class="candidate-tabs" aria-label="Candidates for {escaped(sample[child_id]['sample_id'])}">{''.join(selectors)}</nav></div>
          <div class="case-review">
            <h3>Final case judgment</h3>
            <label for="case-{child_id}-decision">Best plausible parent</label>
            <select id="case-{child_id}-decision" data-review-field data-case-decision data-child-id="{child_id}"><option value="">Choose…</option>{decision_options}<option value="none">None of the method winners</option></select>
            <label for="case-{child_id}-explanation">Explanation</label>
            <textarea id="case-{child_id}-explanation" data-review-field data-case-explanation data-child-id="{child_id}" placeholder="Why is this the best plausible parent, or why are none of the method winners plausible?"></textarea>
          </div>
        </section>""")

    banner = "PROVISIONAL SNAPSHOT — regenerate after Flash recovery" if manifest["provisional"] else "FINAL SNAPSHOT"
    candidate_count = sum(len(parents) for parents in top.values())
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Function-parent blind review</title>
<style>
:root{{--ink:#172033;--muted:#657086;--line:#d9deea;--paper:#fff;--canvas:#f4f6fa;--navy:#183153;--blue:#2463a9;--gold:#f3c969;--shadow:0 8px 28px rgba(24,49,83,.09)}}
*{{box-sizing:border-box}} html{{scroll-behavior:smooth}} body{{margin:0;background:var(--canvas);color:var(--ink);font:16px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
.topbar{{position:sticky;top:0;z-index:10;background:rgba(24,49,83,.97);color:#fff;box-shadow:0 2px 12px rgba(0,0,0,.2)}}
.topbar-inner{{max-width:1440px;margin:auto;padding:14px 28px;display:flex;gap:18px;align-items:center;justify-content:space-between}}
.status{{font-weight:750;color:var(--gold)}} .snapshot{{font:12px ui-monospace,SFMono-Regular,Menlo,monospace;opacity:.8;word-break:break-all}}
.toolbar{{display:flex;align-items:center;gap:9px;flex-wrap:wrap;justify-content:flex-end}} .progress{{font-size:13px;font-weight:700;margin-right:4px}} .tool-button{{cursor:pointer;border:1px solid rgba(255,255,255,.5);border-radius:7px;background:transparent;color:#fff;padding:7px 10px;font:700 13px system-ui}} .tool-button:hover{{background:rgba(255,255,255,.12)}} #import-file{{display:none}}
main{{max-width:1440px;margin:30px auto;padding:0 28px 80px}} .intro{{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:24px 28px;box-shadow:var(--shadow);margin-bottom:30px}}
.intro h1{{margin:0 0 8px;font-size:30px}} .intro p{{margin:6px 0;color:var(--muted);max-width:88ch}}
.child-section{{background:var(--paper);border:1px solid var(--line);border-radius:16px;padding:28px;margin:0 0 38px;box-shadow:var(--shadow);scroll-margin-top:90px}}
.child-heading,.candidate-heading{{display:flex;justify-content:space-between;gap:20px;align-items:flex-start}} .eyebrow,.candidate-number{{display:block;color:var(--blue);font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase}}
h2{{font:700 28px/1.2 Georgia,serif;margin:6px 0}} h3{{font:700 22px/1.25 Georgia,serif;margin:5px 0}} .metadata{{margin:4px 0;color:var(--muted)}}
.source-link{{white-space:nowrap;color:var(--blue);font-weight:700;text-decoration:none;border:1px solid #b9cce5;border-radius:8px;padding:8px 11px;background:#f7fbff}} .source-link:hover{{background:#eaf3ff}}
.document-panel{{margin-top:18px;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:#fbfcfe}} .document-panel summary{{cursor:pointer;padding:12px 16px;background:#eef2f8;font-weight:750;color:var(--navy)}}
.document-text{{padding:18px 20px;white-space:pre-wrap;font:15px/1.68 Georgia,"Times New Roman",serif;max-height:620px;overflow:auto;background:#fff;border-top:1px solid var(--line)}} .child-document .document-text{{max-height:360px}}
mark.operative{{background:#fff0a8;color:inherit;border-radius:3px;padding:.08em .03em;box-shadow:inset 0 -1px 0 #e3b92f}} .operative-trigger{{font-weight:850;color:#6f3100;text-decoration:underline;text-decoration-color:#d58b32;text-decoration-thickness:2px;text-underline-offset:2px}} .highlight-key{{font-size:13px;color:var(--muted);margin:10px 2px 0}}
.candidate-workspace{{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:20px;align-items:start;margin-top:22px}} .candidate-stage{{min-width:0}} .candidate-card{{display:none;border:1px solid #cdd5e3;border-radius:13px;padding:20px;background:#fff;min-width:0}} .candidate-card.active{{display:block}}
.candidate-tabs{{position:sticky;top:92px;display:flex;flex-direction:column;gap:9px}} .candidate-tab{{cursor:pointer;text-align:left;border:1px solid #c8d1df;border-radius:10px;background:#f8faff;color:var(--ink);padding:12px 13px}} .candidate-tab:hover{{border-color:#7fa6d5;background:#f0f6ff}} .candidate-tab.active{{border-color:var(--blue);background:#eaf3ff;box-shadow:inset 4px 0 0 var(--blue)}} .candidate-tab span{{display:block;color:var(--blue);font-size:11px;font-weight:800;letter-spacing:.07em;text-transform:uppercase}} .candidate-tab strong{{display:block;font:700 15px/1.25 Georgia,serif;margin:3px 0}} .candidate-tab small{{color:var(--muted)}}
.gemini-assessment{{margin-top:18px;border:1px solid #cabee5;border-radius:12px;background:#faf8ff;padding:17px 20px}} .gemini-assessment h3{{font:750 17px/1.3 system-ui;margin:0 0 10px;color:#47366c}} .gemini-row{{display:grid;grid-template-columns:minmax(180px,240px) 1fr;gap:12px;padding:9px 0;border-top:1px solid #e3ddef}} .gemini-row:first-of-type{{border-top:0}} .gemini-row>span{{font-weight:750;color:#47366c}} .gemini-row strong,.gemini-row small,.gemini-best{{display:block}} .gemini-row small{{color:var(--muted);margin-top:2px}} .gemini-best{{font-size:14px;color:var(--muted)}} .gemini-yes{{color:#17633a}} .gemini-no{{color:#9a3e2e}}
.case-review{{display:grid;grid-template-columns:180px minmax(0,1fr);gap:10px 14px;align-items:start;margin-top:22px;padding:20px;border:1px solid #b9cce5;border-radius:12px;background:#f7fbff}} .case-review h3{{grid-column:1/-1;margin:0 0 4px}} .case-review label{{font-weight:750;color:var(--navy);padding-top:8px}}
select,textarea{{width:100%;border:1px solid #aeb8ca;border-radius:8px;padding:9px 11px;font:inherit;background:#fff}} textarea{{min-height:100px;resize:vertical}}
@media(max-width:850px){{main{{padding:0 12px}}.child-section{{padding:18px}}.topbar-inner,.child-heading,.candidate-heading{{display:block}}.toolbar{{justify-content:flex-start;margin-top:10px}}.source-link{{display:inline-block;margin-top:12px}}.candidate-workspace{{display:flex;flex-direction:column-reverse}}.candidate-tabs{{position:static;width:100%;display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}}.candidate-stage{{width:100%}}.case-review,.gemini-row{{grid-template-columns:1fr}}}}
@media print{{.topbar{{position:static}}body{{background:#fff}}main{{max-width:none}}.child-section{{break-before:page;box-shadow:none}}.document-text{{max-height:none;overflow:visible}}}}
</style></head><body>
<header class="topbar"><div class="topbar-inner"><div><div class="status">{banner}</div><div class="snapshot">Snapshot {manifest['snapshot_hash']}</div></div><div class="toolbar"><span class="progress" id="progress">0 of {len(top)} cases decided</span><button class="tool-button" id="export-review" type="button">Export review</button><button class="tool-button" id="import-review" type="button">Import review</button><input id="import-file" type="file" accept="application/json,.json"></div></div></header>
<main><div class="intro"><h1>Parent-candidate review</h1><p>Review the child directive against each unique top candidate selected by the four ranking methods. Candidate order remains reproducibly shuffled. Gemini's separate absolute parent judgments are now shown for comparison with the completed blinded review.</p><p>The displayed text is the fullest locally retained authority-masked pipeline text. Use “Open original source” for the publisher's original page.</p></div>{''.join(sections)}</main>
<script>
const snapshotHash='{manifest['snapshot_hash']}';
const storageKey='function-parent-review:'+snapshotHash;
const fields=[...document.querySelectorAll('[data-review-field]')];
try{{const saved=JSON.parse(localStorage.getItem(storageKey)||'{{}}');fields.forEach(x=>{{if(saved[x.id]!==undefined)x.value=saved[x.id]}})}}catch(_e){{}}
function values(){{const saved={{}};fields.forEach(x=>saved[x.id]=x.value);return saved}}
function updateProgress(){{const decisions=[...document.querySelectorAll('[data-case-decision]')];const done=decisions.filter(x=>x.value).length;document.getElementById('progress').textContent=`${{done}} of ${{decisions.length}} cases decided`}}
function save(){{localStorage.setItem(storageKey,JSON.stringify(values()));updateProgress()}}
fields.forEach(x=>x.addEventListener('input',save));updateProgress();
document.querySelectorAll('.candidate-tabs').forEach(nav=>{{nav.addEventListener('click',event=>{{const button=event.target.closest('.candidate-tab');if(!button)return;const section=nav.closest('.child-section');section.querySelectorAll('.candidate-tab').forEach(x=>{{x.classList.toggle('active',x===button);x.setAttribute('aria-selected',x===button?'true':'false')}});section.querySelectorAll('.candidate-card').forEach(x=>x.classList.toggle('active',x.id===button.dataset.target));}})}});
document.getElementById('export-review').addEventListener('click',()=>{{
  const cases={{}};document.querySelectorAll('[data-case-decision]').forEach(x=>{{const child=x.dataset.childId;cases[child]={{selected_parent_id:x.value&&x.value!=='none'?x.value:null,decision:x.value==='none'?'none':(x.value?'candidate':''),explanation:document.querySelector(`[data-case-explanation][data-child-id="${{child}}"]`).value}}}});
  const payload={{schema_version:2,snapshot_hash:snapshotHash,exported_at:new Date().toISOString(),cases:cases,review_fields:values()}};
  const blob=new Blob([JSON.stringify(payload,null,2)+'\\n'],{{type:'application/json'}});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`function-parent-review-${{snapshotHash.slice(0,12)}}.json`;a.click();URL.revokeObjectURL(url);
}});
const importFile=document.getElementById('import-file');document.getElementById('import-review').addEventListener('click',()=>importFile.click());
importFile.addEventListener('change',async()=>{{
  if(!importFile.files.length)return;
  try{{const payload=JSON.parse(await importFile.files[0].text());if(payload.snapshot_hash!==snapshotHash)throw new Error('This review belongs to a different snapshot.');if(payload.review_fields&&typeof payload.review_fields==='object')fields.forEach(x=>{{if(payload.review_fields[x.id]!==undefined)x.value=payload.review_fields[x.id]}});if(payload.schema_version===2&&payload.cases)Object.entries(payload.cases).forEach(([child,item])=>{{const decision=document.querySelector(`[data-case-decision][data-child-id="${{child}}"]`);const explanation=document.querySelector(`[data-case-explanation][data-child-id="${{child}}"]`);if(decision)decision.value=item.decision==='none'?'none':(item.selected_parent_id||'');if(explanation)explanation.value=item.explanation||''}});save();alert('Review imported successfully.')}}catch(error){{alert('Import failed: '+error.message)}}finally{{importFile.value=''}}
}});
</script></body></html>"""
    output = args.snapshot_dir / "blind_top_candidate_review.html"
    output.write_text(page, encoding="utf-8")
    print(json.dumps({"children": len(sections), "output": str(output), "provisional": manifest["provisional"]}))


if __name__ == "__main__":
    main()
