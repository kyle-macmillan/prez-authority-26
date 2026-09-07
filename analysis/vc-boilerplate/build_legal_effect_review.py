#!/usr/bin/env python3
"""Build a standalone review viewer for sampled Code 2/3 EOs and memoranda."""
from __future__ import annotations

import csv
import html
import json
import random
from collections import defaultdict
from pathlib import Path


HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"
OUT = OUTPUTS / "legal_effect_review_30.html"
SEED = 20260820
PER_TYPE = 15

SOURCES = {
    "Executive order": OUTPUTS / "sol_low_eo_population",
    "Memorandum": OUTPUTS / "sol_low_memo_population",
}


def load_population(label: str, directory: Path) -> list[dict]:
    requests = {
        str(row["document_id"]): row
        for row in json.loads((directory / "requests.json").read_text(encoding="utf-8"))
    }
    classified: dict[str, list[dict]] = defaultdict(list)
    with (directory / "classifications.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if int(row["code"]) in (2, 3):
                row["code"] = int(row["code"])
                row["segment_index"] = int(row["segment_index"])
                classified[str(row["document_id"])].append(row)
    documents = []
    for document_id, segments in classified.items():
        request = requests[document_id]
        documents.append({
            "document_id": document_id,
            "document_type": label,
            "url": request["url"],
            "date": request["date"],
            "president": request["president"],
            "full_context": request["full_context"],
            "segments": sorted(segments, key=lambda row: row["segment_index"]),
            "codes": sorted({row["code"] for row in segments}),
        })
    return documents


def sample_documents(documents: list[dict], seed_offset: int) -> list[dict]:
    rng = random.Random(SEED + seed_offset)
    code2 = [row for row in documents if 2 in row["codes"]]
    code3 = [row for row in documents if 3 in row["codes"]]
    rng.shuffle(code2)
    rng.shuffle(code3)
    selected = code2[:8]
    selected_ids = {row["document_id"] for row in selected}
    selected.extend(row for row in code3 if row["document_id"] not in selected_ids)
    selected = selected[:PER_TYPE]
    if len(selected) != PER_TYPE or not {2, 3}.issubset({code for row in selected for code in row["codes"]}):
        raise ValueError("insufficient distinct Code 2/3 documents for balanced review sample")
    rng.shuffle(selected)
    return selected


def title_from_url(url: str, document_id: str) -> str:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    title = slug.replace("-", " ").strip().title()
    return title or f"Document {document_id}"


def render_segment(row: dict) -> str:
    code = row["code"]
    return f"""
      <article class="segment code-{code}" data-code="{code}">
        <div class="segment-head"><span class="badge">Code {code}</span><code>{html.escape(row['segment_id'])}</code></div>
        <div class="segment-text">{html.escape(row['segment_text'])}</div>
        <dl>
          <dt>Rationale</dt><dd>{html.escape(row['rationale'])}</dd>
          <dt>Evidence</dt><dd><q>{html.escape(row['evidence'])}</q></dd>
        </dl>
      </article>"""


def render_document(row: dict, index: int) -> str:
    codes = " ".join(f"code-{code}" for code in row["codes"])
    code_badges = " ".join(f'<span class="badge code-{code}">Code {code}</span>' for code in row["codes"])
    segments = "".join(render_segment(segment) for segment in row["segments"])
    title = title_from_url(row["url"], row["document_id"])
    return f"""
    <section class="document {codes}" id="doc-{index}" data-type="{html.escape(row['document_type'])}" data-codes="{' '.join(map(str, row['codes']))}">
      <header>
        <div class="eyebrow">{index}. {html.escape(row['document_type'])} · ID {html.escape(row['document_id'])}</div>
        <h2><a href="{html.escape(row['url'], quote=True)}" target="_blank" rel="noreferrer">{html.escape(title)}</a></h2>
        <div class="meta">{html.escape(row['president'])} · {html.escape(row['date'])} · {code_badges}</div>
      </header>
      <h3>Code 2/3 operative segments</h3>
      {segments}
      <details><summary>Full directive context</summary><div class="full-context">{html.escape(row['full_context'])}</div></details>
    </section>"""


def build() -> tuple[str, list[dict]]:
    sampled = []
    for offset, (label, directory) in enumerate(SOURCES.items()):
        sampled.extend(sample_documents(load_population(label, directory), offset))
    # Interleave document types while keeping the sample itself deterministic.
    eos = [row for row in sampled if row["document_type"] == "Executive order"]
    memos = [row for row in sampled if row["document_type"] == "Memorandum"]
    ordered = [row for pair in zip(eos, memos) for row in pair]
    documents = "".join(render_document(row, index) for index, row in enumerate(ordered, 1))
    payload = json.dumps([
        {"index": index, "document_id": row["document_id"], "document_type": row["document_type"],
         "codes": row["codes"]}
        for index, row in enumerate(ordered, 1)
    ])
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Code 2/3 EO and Memorandum Review</title>
<style>
:root{{--ink:#172033;--muted:#637083;--line:#d9e0e8;--paper:#fff;--bg:#f3f5f8;--two:#8b5cf6;--three:#dc5a3f}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,sans-serif}}
.top{{position:sticky;top:0;z-index:2;background:#172033;color:white;padding:16px 24px;box-shadow:0 2px 8px #0003}}
.top h1{{font-size:20px;margin:0 0 8px}} .controls{{display:flex;gap:8px;flex-wrap:wrap}}
button{{border:1px solid #8490a3;border-radius:999px;background:#fff;color:#172033;padding:6px 12px;cursor:pointer}} button.active{{background:#dbeafe;border-color:#60a5fa}}
main{{max-width:1120px;margin:24px auto;padding:0 18px}} .document{{background:var(--paper);border:1px solid var(--line);border-radius:12px;margin:0 0 24px;padding:22px;box-shadow:0 2px 8px #1e293b0d}}
.eyebrow,.meta{{color:var(--muted)}} h2{{margin:3px 0 4px;font-size:21px}} h2 a{{color:inherit}} h3{{font-size:14px;text-transform:uppercase;letter-spacing:.04em;margin-top:22px}}
.badge{{display:inline-block;border-radius:999px;padding:2px 8px;font-weight:700;font-size:12px;background:#e8edf3}} .badge.code-2{{background:#ede9fe;color:#5b21b6}} .badge.code-3{{background:#fee2dc;color:#9f2d18}}
.segment{{border-left:5px solid var(--line);background:#fafbfc;padding:14px 16px;margin:12px 0;border-radius:6px}} .segment.code-2{{border-color:var(--two)}} .segment.code-3{{border-color:var(--three)}}
.segment-head{{display:flex;justify-content:space-between;gap:12px;margin-bottom:10px}} .segment-text,.full-context{{white-space:pre-wrap}} dl{{display:grid;grid-template-columns:80px 1fr;gap:6px 12px;margin:14px 0 0}} dt{{font-weight:700}} dd{{margin:0}}
details{{margin-top:16px;border-top:1px solid var(--line);padding-top:12px}} summary{{cursor:pointer;font-weight:700}} .full-context{{margin-top:12px;max-height:480px;overflow:auto;background:#f8fafc;padding:14px;border-radius:6px}}
.hidden{{display:none}} @media(max-width:650px){{dl{{display:block}}dt{{margin-top:8px}}.document{{padding:15px}}}}
</style></head><body>
<div class="top"><h1>Code 2/3 review · 15 executive orders + 15 memoranda</h1><div class="controls">
<button class="active" data-filter="all">All 30</button><button data-filter="Executive order">Executive orders</button><button data-filter="Memorandum">Memoranda</button><button data-filter="2">Contains Code 2</button><button data-filter="3">Contains Code 3</button>
</div></div><main>{documents}</main>
<script>const MANIFEST={payload};document.querySelectorAll('button[data-filter]').forEach(b=>b.onclick=()=>{{document.querySelectorAll('button').forEach(x=>x.classList.remove('active'));b.classList.add('active');const f=b.dataset.filter;document.querySelectorAll('.document').forEach(d=>d.classList.toggle('hidden',!(f==='all'||d.dataset.type===f||d.dataset.codes.split(' ').includes(f))))}});</script>
</body></html>"""
    return page, ordered


def main() -> None:
    page, rows = build()
    OUT.write_text(page, encoding="utf-8")
    counts = defaultdict(int)
    for row in rows:
        counts[row["document_type"]] += 1
    print(json.dumps({"output": str(OUT), "documents": len(rows), "counts": dict(counts), "seed": SEED}, indent=2))


if __name__ == "__main__":
    main()
