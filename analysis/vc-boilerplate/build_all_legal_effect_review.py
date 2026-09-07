#!/usr/bin/env python3
"""Build a full Code 2/3 review viewer across all boilerplate-vesting populations."""
from __future__ import annotations

import html
import json
from collections import Counter
from pathlib import Path

import build_legal_effect_review as sample


HERE = Path(__file__).resolve().parent
OUT = HERE / "outputs" / "legal_effect_review_all_code_2_3.html"
SOURCES = {
    "Executive order": HERE / "outputs" / "sol_low_eo_population",
    "Memorandum": HERE / "outputs" / "sol_low_memo_population",
    "Proclamation": HERE / "outputs" / "sol_low_proclamation_population",
    "Letter": HERE / "outputs" / "sol_low_letter_population",
}


def all_documents() -> list[dict]:
    documents = []
    for label, directory in SOURCES.items():
        documents.extend(sample.load_population(label, directory))
    return sorted(documents, key=lambda row: (row["document_type"], row["date"], int(row["document_id"])), reverse=True)


def render_document(row: dict, index: int) -> str:
    codes = " ".join(f"code-{code}" for code in row["codes"])
    badges = " ".join(f'<span class="badge code-{code}">Code {code}</span>' for code in row["codes"])
    segments = "".join(sample.render_segment(segment) for segment in row["segments"])
    title = sample.title_from_url(row["url"], row["document_id"])
    return f"""
    <section class="document {codes}" id="doc-{index}" data-type="{html.escape(row['document_type'])}" data-codes="{' '.join(map(str, row['codes']))}">
      <header><div class="eyebrow">{index}. {html.escape(row['document_type'])} · ID {html.escape(row['document_id'])}</div>
      <h2><a href="{html.escape(row['url'], quote=True)}" target="_blank" rel="noreferrer">{html.escape(title)}</a></h2>
      <div class="meta">{html.escape(row['president'])} · {html.escape(row['date'])} · {badges}</div></header>
      <h3>Code 2/3 operative segments</h3>{segments}
      <details><summary>Full directive context</summary><div class="full-context">{html.escape(row['full_context'])}</div></details>
    </section>"""


def build() -> tuple[str, list[dict]]:
    rows = all_documents()
    type_counts = Counter(row["document_type"] for row in rows)
    segment_counts = Counter(segment["code"] for row in rows for segment in row["segments"])
    documents = "".join(render_document(row, index) for index, row in enumerate(rows, 1))
    buttons = [
        ("all", f"All {len(rows):,}"), ("2", f"Code 2 ({segment_counts[2]:,} segments)"),
        ("3", f"Code 3 ({segment_counts[3]:,} segments)"),
    ] + [(document_type, f"{document_type.title()} ({count:,})") for document_type, count in sorted(type_counts.items())]
    controls = "".join(
        f'<button class="{"active" if key == "all" else ""}" data-filter="{html.escape(key)}">{html.escape(label)}</button>'
        for key, label in buttons
    )
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>All Code 2/3 boilerplate-vesting classifications</title><style>
:root{{--ink:#172033;--muted:#637083;--line:#d9e0e8;--paper:#fff;--bg:#f3f5f8;--two:#8b5cf6;--three:#dc5a3f}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,sans-serif}}
.top{{position:sticky;top:0;z-index:2;background:#172033;color:#fff;padding:16px 24px;box-shadow:0 2px 8px #0003}}.top h1{{font-size:20px;margin:0 0 4px}}.top p{{margin:0 0 9px;color:#cad4e2;font-size:13px}}.controls{{display:flex;gap:8px;flex-wrap:wrap}}button{{border:1px solid #8490a3;border-radius:999px;background:#fff;color:#172033;padding:6px 12px;cursor:pointer}}button.active{{background:#dbeafe;border-color:#60a5fa}}
main{{max-width:1120px;margin:24px auto;padding:0 18px}}.document{{background:var(--paper);border:1px solid var(--line);border-radius:12px;margin:0 0 24px;padding:22px;box-shadow:0 2px 8px #1e293b0d}}.eyebrow,.meta{{color:var(--muted)}}h2{{margin:3px 0 4px;font-size:21px}}h2 a{{color:inherit}}h3{{font-size:14px;text-transform:uppercase;letter-spacing:.04em;margin-top:22px}}.badge{{display:inline-block;border-radius:999px;padding:2px 8px;font-weight:700;font-size:12px;background:#e8edf3}}.badge.code-2{{background:#ede9fe;color:#5b21b6}}.badge.code-3{{background:#fee2dc;color:#9f2d18}}
.segment{{border-left:5px solid var(--line);background:#fafbfc;padding:14px 16px;margin:12px 0;border-radius:6px}}.segment.code-2{{border-color:var(--two)}}.segment.code-3{{border-color:var(--three)}}.segment-head{{display:flex;justify-content:space-between;gap:12px;margin-bottom:10px}}.segment-text,.full-context{{white-space:pre-wrap}}dl{{display:grid;grid-template-columns:80px 1fr;gap:6px 12px;margin:14px 0 0}}dt{{font-weight:700}}dd{{margin:0}}details{{margin-top:16px;border-top:1px solid var(--line);padding-top:12px}}summary{{cursor:pointer;font-weight:700}}.full-context{{margin-top:12px;max-height:480px;overflow:auto;background:#f8fafc;padding:14px;border-radius:6px}}.hidden{{display:none}}@media(max-width:650px){{dl{{display:block}}dt{{margin-top:8px}}.document{{padding:15px}}}}
</style></head><body><div class="top"><h1>All Code 2/3 boilerplate-vesting classifications</h1><p>{len(rows):,} directives · {segment_counts[2]:,} Code 2 segments · {segment_counts[3]:,} Code 3 segments · original frozen prompt</p><div class="controls">{controls}</div></div><main>{documents}</main>
<script>document.querySelectorAll('button[data-filter]').forEach(b=>b.onclick=()=>{{document.querySelectorAll('button').forEach(x=>x.classList.remove('active'));b.classList.add('active');const f=b.dataset.filter;document.querySelectorAll('.document').forEach(d=>d.classList.toggle('hidden',!(f==='all'||d.dataset.type===f||d.dataset.codes.split(' ').includes(f))))}});</script></body></html>"""
    return page, rows


def main() -> None:
    page, rows = build()
    OUT.write_text(page, encoding="utf-8")
    counts = Counter(segment["code"] for row in rows for segment in row["segments"])
    print(json.dumps({"output": str(OUT), "directives": len(rows), "code_2_segments": counts[2], "code_3_segments": counts[3]}, indent=2))


if __name__ == "__main__":
    main()
