#!/usr/bin/env python3
"""Build a blind, readable HTML review of unique top candidates."""

from __future__ import annotations

import argparse
import csv
import html
import json
import random
from collections import defaultdict
from pathlib import Path

from validate_function_profiles import _read_jsonl


ROOT = Path(__file__).resolve().parents[1]


def escaped(value: object) -> str:
    return html.escape(str(value or ""))


def document_text(document: dict) -> str:
    """Return the fullest locally retained text used by the parent pipeline."""
    return str(document.get("cleaned_masked_text") or "")


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
    for method in ("deterministic", "qwen", "gemini"):
        path = args.snapshot_dir / f"{method}_rankings.jsonl"
        if path.exists():
            for row in _read_jsonl(path):
                if int(row["rank"]) == 1:
                    top[row["child_id"]][row["parent_id"]].append(method)

    wanted = set(sample) | {parent_id for parents in top.values() for parent_id in parents}
    documents = {}
    with (args.input_dir / "directive_similarity_documents.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            document_id = str(row["document_id"])
            if document_id in wanted:
                documents[document_id] = row

    sections = []
    for child_number, child_id in enumerate(sorted(top, key=int), 1):
        child = documents[child_id]
        candidates = list(top[child_id])
        random.Random(f"{manifest['snapshot_hash']}:{child_id}").shuffle(candidates)
        cards = []
        for label, parent_id in enumerate(candidates, 1):
            parent = documents[parent_id]
            field_id = f"{sample[child_id]['sample_id']}-candidate-{label}"
            cards.append(f"""
            <article class="candidate-card">
              <div class="candidate-heading">
                <div><span class="candidate-number">Candidate {label}</span>
                  <h3>{escaped(parent['title'])}</h3>
                  <p class="metadata">{escaped(parent['document_type']).replace('_', ' ').title()} · {escaped(parent['date'])}</p>
                </div>
                {source_link(parent)}
              </div>
              <details class="document-panel" open>
                <summary>Candidate directive text</summary>
                <div class="document-text">{escaped(document_text(parent))}</div>
              </details>
              <div class="review-fields">
                <label for="{field_id}-decision">Decision</label>
                <select id="{field_id}-decision" data-review-field>
                  <option value="">Choose…</option><option value="parent">Parent</option>
                  <option value="not_parent">Not parent</option><option value="none_available">None available</option>
                </select>
                <label for="{field_id}-notes">Explanation</label>
                <textarea id="{field_id}-notes" data-review-field placeholder="Why is or isn't this a plausible parent?"></textarea>
              </div>
            </article>""")

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
            <div class="document-text">{escaped(document_text(child))}</div>
          </details>
          <div class="candidate-grid">{''.join(cards)}</div>
        </section>""")

    banner = "PROVISIONAL SNAPSHOT — regenerate after Flash recovery" if manifest["provisional"] else "FINAL SNAPSHOT"
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Function-parent blind review</title>
<style>
:root{{--ink:#172033;--muted:#657086;--line:#d9deea;--paper:#fff;--canvas:#f4f6fa;--navy:#183153;--blue:#2463a9;--gold:#f3c969;--shadow:0 8px 28px rgba(24,49,83,.09)}}
*{{box-sizing:border-box}} html{{scroll-behavior:smooth}} body{{margin:0;background:var(--canvas);color:var(--ink);font:16px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
.topbar{{position:sticky;top:0;z-index:10;background:rgba(24,49,83,.97);color:#fff;box-shadow:0 2px 12px rgba(0,0,0,.2)}}
.topbar-inner{{max-width:1440px;margin:auto;padding:14px 28px;display:flex;gap:24px;align-items:center;justify-content:space-between}}
.status{{font-weight:750;color:var(--gold)}} .snapshot{{font:12px ui-monospace,SFMono-Regular,Menlo,monospace;opacity:.8;word-break:break-all}}
main{{max-width:1440px;margin:30px auto;padding:0 28px 80px}} .intro{{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:24px 28px;box-shadow:var(--shadow);margin-bottom:30px}}
.intro h1{{margin:0 0 8px;font-size:30px}} .intro p{{margin:6px 0;color:var(--muted);max-width:88ch}}
.child-section{{background:var(--paper);border:1px solid var(--line);border-radius:16px;padding:28px;margin:0 0 38px;box-shadow:var(--shadow);scroll-margin-top:90px}}
.child-heading,.candidate-heading{{display:flex;justify-content:space-between;gap:20px;align-items:flex-start}} .eyebrow,.candidate-number{{display:block;color:var(--blue);font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase}}
h2{{font:700 28px/1.2 Georgia,serif;margin:6px 0}} h3{{font:700 22px/1.25 Georgia,serif;margin:5px 0}} .metadata{{margin:4px 0;color:var(--muted)}}
.source-link{{white-space:nowrap;color:var(--blue);font-weight:700;text-decoration:none;border:1px solid #b9cce5;border-radius:8px;padding:8px 11px;background:#f7fbff}} .source-link:hover{{background:#eaf3ff}}
.document-panel{{margin-top:18px;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:#fbfcfe}} .document-panel summary{{cursor:pointer;padding:12px 16px;background:#eef2f8;font-weight:750;color:var(--navy)}}
.document-text{{padding:18px 20px;white-space:pre-wrap;font:15px/1.68 Georgia,"Times New Roman",serif;max-height:560px;overflow:auto;background:#fff;border-top:1px solid var(--line)}} .child-document .document-text{{max-height:420px}}
.candidate-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,480px),1fr));gap:22px;margin-top:24px}} .candidate-card{{border:1px solid #cdd5e3;border-radius:13px;padding:20px;background:#fff;min-width:0}}
.review-fields{{display:grid;grid-template-columns:max-content 1fr;gap:10px 14px;align-items:start;margin-top:18px;padding-top:16px;border-top:1px solid var(--line)}} .review-fields label{{font-weight:750;color:var(--navy);padding-top:8px}}
select,textarea{{width:100%;border:1px solid #aeb8ca;border-radius:8px;padding:9px 11px;font:inherit;background:#fff}} textarea{{min-height:100px;resize:vertical}}
@media(max-width:700px){{main{{padding:0 12px}}.child-section{{padding:18px}}.topbar-inner,.child-heading,.candidate-heading{{display:block}}.source-link{{display:inline-block;margin-top:12px}}.review-fields{{grid-template-columns:1fr}}}}
@media print{{.topbar{{position:static}}body{{background:#fff}}main{{max-width:none}}.child-section{{break-before:page;box-shadow:none}}.document-text{{max-height:none;overflow:visible}}}}
</style></head><body>
<header class="topbar"><div class="topbar-inner"><span class="status">{banner}</span><span class="snapshot">Snapshot {manifest['snapshot_hash']}</span></div></header>
<main><div class="intro"><h1>Blinded parent-candidate review</h1><p>Review the child directive against each unique top candidate. Candidate order is deterministic and method identity is hidden.</p><p>The displayed text is the fullest locally retained authority-masked pipeline text. Use “Open original source” for the publisher's original page.</p></div>{''.join(sections)}</main>
<script>
const storageKey='function-parent-review:{manifest['snapshot_hash']}';
const fields=[...document.querySelectorAll('[data-review-field]')];
try{{const saved=JSON.parse(localStorage.getItem(storageKey)||'{{}}');fields.forEach(x=>{{if(saved[x.id]!==undefined)x.value=saved[x.id]}})}}catch(_e){{}}
fields.forEach(x=>x.addEventListener('input',()=>{{const saved={{}};fields.forEach(y=>saved[y.id]=y.value);localStorage.setItem(storageKey,JSON.stringify(saved))}}));
</script></body></html>"""
    output = args.snapshot_dir / "blind_top_candidate_review.html"
    output.write_text(page, encoding="utf-8")
    print(json.dumps({"children": len(sections), "output": str(output), "provisional": manifest["provisional"]}))


if __name__ == "__main__":
    main()
