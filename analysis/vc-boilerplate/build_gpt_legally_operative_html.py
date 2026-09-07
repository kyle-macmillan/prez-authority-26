#!/usr/bin/env python3
"""Build standalone review viewers for GPT Code 2 or Code 3 directives."""
from __future__ import annotations

import argparse
import html
import importlib.util
from collections import Counter
from pathlib import Path

import build_legal_effect_review as sample

HERE = Path(__file__).resolve().parent
SOURCES = {
    "Executive order": HERE / "outputs" / "sol_low_eo_population",
    "Memorandum": HERE / "outputs" / "sol_low_memo_population",
    "Proclamation": HERE / "outputs" / "sol_low_proclamation_population",
    "Letter": HERE / "outputs" / "sol_low_letter_population",
}
CONFIG = {
    2: {
        "output": "gpt_code_2_directives.html",
        "title": "GPT-5.6 Sol Code 2 directives",
        "description": "The segment requires an agency or official to produce a specified later legal consequence.",
        "store": "gpt-code-2-directive-notes-v1",
        "notes_file": "gpt-code-2-directive-notes.json",
        "accent": "#6d28d9", "tint": "#f5f3ff", "badge": "#ede9fe", "badge_text": "#5b21b6",
    },
    3: {
        "output": "gpt_legally_operative_directives.html",
        "title": "GPT-5.6 Sol legally operative directives",
        "description": "The segment itself produces a legal consequence.",
        "store": "gpt-legally-operative-notes-v1",
        "notes_file": "gpt-legally-operative-notes.json",
        "accent": "#b42318", "tint": "#fff8f6", "badge": "#fee2dc", "badge_text": "#9f2d18",
    },
}


def build_viewer(code: int) -> tuple[Path, int, int]:
    config = CONFIG[code]
    spec = importlib.util.spec_from_file_location("vc_boilerplate_build_for_viewer", HERE / "build.py")
    build = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(build)
    eligible = {
        (row["doc_type"], str(row["ucsb_identifier"]))
        for row in build.select_target(build.load_source_rows())
    }
    rows = []
    for label, directory in SOURCES.items():
        rows.extend(sample.load_population(label, directory))
    label_to_type = {
        "Executive order": "executive_order", "Memorandum": "memorandum",
        "Proclamation": "proclamation", "Letter": "letter",
    }
    rows = [
        row for row in rows
        if code in row["codes"]
        and (label_to_type[row["document_type"]], row["document_id"]) in eligible
    ]
    rows.sort(key=lambda row: (row["document_type"], row["date"], int(row["document_id"])), reverse=True)
    counts = Counter(row["document_type"] for row in rows)

    cards = []
    for i, row in enumerate(rows, 1):
        segments = [s for s in row["segments"] if s["code"] == code]
        rendered = "".join(
            f'<article class="segment"><div class="segment-head"><b>Segment {html.escape(str(s["segment_index"]))}</b>'
            f'<span class="badge">GPT Code {code}</span></div><p class="text">{html.escape(s["segment_text"])}</p>'
            f'<dl><dt>Rationale</dt><dd>{html.escape(s["rationale"])}</dd>'
            f'<dt>Evidence</dt><dd>{html.escape(s["evidence"])}</dd></dl></article>'
            for s in segments
        )
        title = sample.title_from_url(row["url"], row["document_id"])
        cards.append(f'''<section class="card" data-type="{html.escape(row["document_type"])}">
<div class="eyebrow">{i}. {html.escape(row["document_type"])} · UCSB identifier {html.escape(row["document_id"])}</div>
<h2><a href="{html.escape(row["url"], quote=True)}" target="_blank" rel="noreferrer">{html.escape(title)}</a></h2>
<div class="meta">{html.escape(row["president"])} · {html.escape(row["date"])}</div>{rendered}
<details><summary>Full directive context</summary><div class="context">{html.escape(row["full_context"])}</div></details>
<label class="notes-label" for="notes-{html.escape(row['document_id'])}">Notes</label>
<textarea class="notes" id="notes-{html.escape(row['document_id'])}" data-ucsb-identifier="{html.escape(row['document_id'])}" placeholder="Add review notes…"></textarea></section>''')

    filters = ''.join(f'<button data-filter="{html.escape(k)}">{html.escape(k)} ({v})</button>' for k, v in sorted(counts.items()))
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(config["title"])}</title><style>
:root{{--ink:#172033;--muted:#637083;--line:#d9e0e8;--bg:#f3f5f8;--accent:{config["accent"]};--tint:{config["tint"]};--badge:{config["badge"]};--badge-text:{config["badge_text"]}}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,sans-serif}}header{{position:sticky;top:0;z-index:2;background:#172033;color:white;padding:18px 24px;box-shadow:0 2px 8px #0003}}header h1{{margin:0;font-size:22px}}header p{{margin:4px 0 12px;color:#d5ddea;font-size:13px}}button{{border:1px solid #8490a3;border-radius:999px;background:white;padding:6px 12px;margin:3px;cursor:pointer}}button.active{{background:var(--badge);border-color:var(--accent)}}main{{max-width:1120px;margin:24px auto;padding:0 18px}}.card{{background:white;border:1px solid var(--line);border-radius:12px;margin-bottom:22px;padding:22px;box-shadow:0 2px 8px #1e293b0d}}.eyebrow,.meta{{color:var(--muted)}}h2{{margin:3px 0 2px;font-size:21px}}h2 a{{color:inherit}}.segment{{border-left:5px solid var(--accent);background:var(--tint);padding:13px 16px;margin:15px 0;border-radius:6px}}.segment-head{{display:flex;justify-content:space-between;gap:12px}}.badge{{background:var(--badge);color:var(--badge-text);border-radius:999px;padding:2px 8px;font-size:12px;font-weight:700}}.text,.context{{white-space:pre-wrap}}dl{{display:grid;grid-template-columns:85px 1fr;gap:6px 12px}}dt{{font-weight:700}}dd{{margin:0}}details{{border-top:1px solid var(--line);padding-top:12px;margin-top:16px}}summary{{cursor:pointer;font-weight:700}}.context{{margin-top:12px;max-height:500px;overflow:auto;background:#f8fafc;padding:14px;border-radius:6px}}.notes-label{{display:block;font-weight:700;margin-top:18px}}.notes{{display:block;width:100%;min-height:100px;margin-top:6px;border:1px solid #aeb8c5;border-radius:7px;padding:10px;font:inherit;resize:vertical}}.hidden{{display:none}}@media(max-width:650px){{dl{{display:block}}dt{{margin-top:8px}}.card{{padding:15px}}}}
</style></head><body><header><h1>{html.escape(config["title"])}</h1><p>{len(rows):,} directives containing at least one GPT Code {code} segment. {html.escape(config["description"])} Notes save automatically in this browser.</p><div><button class="active filter" data-filter="all">All ({len(rows)})</button>{filters}<button id="export-notes" type="button">Export notes</button></div></header><main>{''.join(cards)}</main><script>
const STORE='{config["store"]}';
let notes={{}}; try{{notes=JSON.parse(localStorage.getItem(STORE)||'{{}}')}}catch(e){{notes={{}}}}
document.querySelectorAll('.notes').forEach(t=>{{t.value=notes[t.dataset.ucsbIdentifier]||'';t.addEventListener('input',()=>{{notes[t.dataset.ucsbIdentifier]=t.value;localStorage.setItem(STORE,JSON.stringify(notes))}})}});
document.querySelectorAll('button.filter,button[data-filter]').forEach(b=>b.onclick=()=>{{document.querySelectorAll('button[data-filter]').forEach(x=>x.classList.remove('active'));b.classList.add('active');let f=b.dataset.filter;document.querySelectorAll('.card').forEach(c=>c.classList.toggle('hidden',f!=="all"&&c.dataset.type!==f))}});
document.getElementById('export-notes').onclick=()=>{{const payload=Object.entries(notes).filter(([,note])=>note.trim()).map(([ucsb_identifier,note])=>({{ucsb_identifier,note}}));const blob=new Blob([JSON.stringify(payload,null,2)],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='{config["notes_file"]}';a.click();URL.revokeObjectURL(a.href)}};
</script></body></html>'''
    output = HERE / "outputs" / config["output"]
    segment_count = sum(len([s for s in row["segments"] if s["code"] == code]) for row in rows)
    output.write_text(page, encoding="utf-8")
    return output, len(rows), segment_count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", type=int, choices=CONFIG, default=3)
    args = parser.parse_args()
    output, directive_count, segment_count = build_viewer(args.code)
    print(f"Wrote {output} ({directive_count} directives; {segment_count} Code {args.code} segments)")


if __name__ == "__main__":
    main()
