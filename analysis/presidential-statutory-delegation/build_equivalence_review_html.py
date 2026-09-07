#!/usr/bin/env python3
"""Render proposed citation-bundle consolidations as a searchable local page."""
from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=OUTPUTS / "citation_equivalence_review.csv")
    parser.add_argument("--output", type=Path, default=OUTPUTS / "citation_equivalence_review.html")
    args = parser.parse_args()
    with args.input.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    payload = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Citation equivalence review</title><style>
body{{font:15px system-ui,sans-serif;margin:0;background:#f5f3ee;color:#24231f}}header{{position:sticky;top:0;background:#173b37;color:white;padding:18px 4vw;z-index:2}}h1{{margin:0 0 8px}}input{{width:min(720px,90%);padding:10px;border:0;border-radius:5px}}main{{max-width:1200px;margin:20px auto;padding:0 18px}}article{{background:white;border:1px solid #d8d3c8;border-radius:8px;margin:12px 0;padding:16px}}code{{background:#edf2ef;padding:2px 5px}}.meta{{color:#625f57}}.clause{{line-height:1.45}}.forms{{color:#71420b}}a{{color:#12605a}}#count{{margin-left:12px}}</style></head><body>
<header><h1>Citation equivalence review</h1><input id="search" autofocus placeholder="Search authority, printed form, clause, document…"><span id="count"></span></header>
<main id="rows"></main><script>const data={payload};
const esc=s=>String(s||'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
function render(){{const q=document.querySelector('#search').value.toLowerCase();const shown=data.filter(r=>Object.values(r).join(' ').toLowerCase().includes(q));document.querySelector('#count').textContent=`${{shown.length}} / ${{data.length}} bundles`;document.querySelector('#rows').innerHTML=shown.map(r=>`<article><div><code>${{esc(r.target_authority_ids)}}</code></div><p class="forms"><b>Printed forms:</b> ${{esc(r.printed_forms)}}</p><p class="clause">${{esc(r.raw_clause)}}</p><div class="meta">${{esc(r.document_id)}} · ${{esc(r.date)}} · clause ${{esc(r.clause_index)}} · ${{esc(r.component_rules)}} · ${{esc(r.equivalence_basis)}} · <a href="${{esc(r.url)}}">source</a></div></article>`).join('')}}
document.querySelector('#search').addEventListener('input',render);render();</script></body></html>"""
    args.output.write_text(page, encoding="utf-8")
    print(f"Wrote {len(rows)} bundles to {args.output}")


if __name__ == "__main__":
    main()
