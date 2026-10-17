#!/usr/bin/env python3
"""Render the saved Round 3 disagreement ground truth as a read-only HTML page."""

from __future__ import annotations

from collections import Counter
from html import escape
from itertools import groupby
import json
from pathlib import Path

from build_disagreement_review import extract_source_data
from view_segments import OPERATIVE_CODE_OPTIONS


ROOT = Path(__file__).resolve().parents[1]
ROUND3 = ROOT / "data/Annotations/Round 3"
SOURCE = ROUND3 / "round3-ground-truth-review.json"
VIEWER = ROUND3 / "round_3.html"
OUTPUT = ROUND3 / "round3-ground-truth-review.html"
CODE_LABELS = dict(OPERATIVE_CODE_OPTIONS)


def label(code: str | None) -> str:
    return CODE_LABELS[code] if code is not None else "—"


def sort_key(record: dict) -> tuple[int, int, int]:
    doc_id = record["round_id"]
    prefix = "".join(char for char in doc_id if not char.isdigit())
    number = int("".join(char for char in doc_id if char.isdigit()))
    return {"EO": 0, "M": 1, "L": 2, "P": 3}[prefix], number, int(record["chunk_number"])


def build_html(review: dict, metadata: dict, chunks: dict, doc_texts: dict) -> str:
    records = sorted(review["records"], key=sort_key)
    keys = [(r["round_id"], str(r["chunk_number"])) for r in records]
    if len(keys) != len(set(keys)):
        raise ValueError("Ground-truth JSON contains duplicate subdirective IDs")
    for record in records:
        doc_id, chunk_number = record["round_id"], str(record["chunk_number"])
        if chunk_number not in chunks.get(doc_id, {}):
            raise ValueError(f"No source text for {doc_id} subdirective {chunk_number}")
        if record["ground_truth_code"] not in CODE_LABELS:
            raise ValueError(f"Invalid ground-truth code for {doc_id} subdirective {chunk_number}")

    counts = Counter(r["ground_truth_code"] for r in records)
    count_html = "".join(
        f'<span class="count code-{code}">{escape(label(code))}: {counts[code]}</span>'
        for code in sorted(counts)
    )
    sections = []
    for doc_id, grouped in groupby(records, key=lambda r: r["round_id"]):
        doc_records = list(grouped)
        info = metadata.get(doc_id, {})
        subtitle = " · ".join(filter(None, (info.get("president"), info.get("date"), info.get("type"))))
        cards = []
        for record in doc_records:
            chunk_number = str(record["chunk_number"])
            code = record["ground_truth_code"]
            fields = [
                ("Disagreement", record["disagreement_type"].replace("_", " ")),
                ("Original code", label(record.get("original_code"))),
                ("Majority code", label(record.get("majority_code"))),
                ("Reviewed code", label(record.get("reviewed_code"))),
                ("Reviewed by", record.get("reviewed_by") or "—"),
            ]
            if record.get("ground_truth_edited_at"):
                fields.append(("Ground truth edited", record["ground_truth_edited_at"]))
            details = "".join(
                f"<div><dt>{escape(name)}</dt><dd>{escape(str(value))}</dd></div>"
                for name, value in fields
            )
            cards.append(
                f'<article id="{escape(doc_id)}-{escape(chunk_number)}" class="card">'
                f'<div class="card-heading"><h3>Subdirective {escape(chunk_number)}</h3>'
                f'<strong class="ground-truth code-{escape(code)}">Ground truth: {escape(label(code))}</strong></div>'
                f'<div class="card-body"><p class="chunk">{escape(chunks[doc_id][chunk_number])}</p>'
                f'<dl>{details}</dl></div></article>'
            )
        sections.append(
            f'<section class="document" id="{escape(doc_id)}">'
            f'<header><h2>{escape(doc_id)}</h2><p>{escape(subtitle)}</p></header>'
            + "".join(cards)
            + f'<details class="context"><summary>Full directive context</summary>'
              f'<pre>{escape(doc_texts[doc_id])}</pre></details></section>'
        )

    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Round 3 ground truth review</title>
<style>
:root{{--ink:#172033;--muted:#596579;--border:#dbe2ea;--paper:#fff;--background:#f4f6fa}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--background);color:var(--ink);font:15px/1.5 system-ui,sans-serif}}
main{{max-width:1180px;margin:auto;padding:24px 16px 56px}}h1{{margin:0 0 6px;font-size:28px}}h2{{margin:0;font-size:20px}}
.intro{{color:var(--muted);max-width:830px;margin:0 0 14px}}.counts{{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:24px}}
.count,.ground-truth{{display:inline-block;padding:5px 9px;border-radius:6px;font-size:13px;font-weight:700}}
.code-0{{background:#e5e7eb;color:#374151}}.code-1{{background:#dbeafe;color:#1e40af}}
.code-2{{background:#fef3c7;color:#92400e}}.code-3{{background:#dcfce7;color:#166534}}
.code-4{{background:#f3e8ff;color:#6b21a8}}.document{{background:var(--paper);border:1px solid var(--border);border-radius:9px;margin:18px 0;overflow:hidden}}
.document>header{{padding:15px 18px;background:#eaf0f9;border-bottom:1px solid var(--border)}}.document>header p{{margin:2px 0 0;color:var(--muted)}}
.card{{padding:16px 18px;border-bottom:1px solid var(--border)}}.card-heading{{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px}}
h3{{font-size:16px;margin:0}}.card-body{{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(250px,1fr);gap:18px;margin-top:12px}}
.chunk{{white-space:pre-wrap;margin:0;padding:13px;background:#f8fafc;border-left:4px solid #93c5fd}}dl{{margin:0;display:grid;align-content:start;gap:5px}}
dl>div{{display:grid;grid-template-columns:125px 1fr;gap:8px}}dt{{color:var(--muted)}}dd{{margin:0;font-weight:600}}
.context{{padding:12px 18px}}summary{{cursor:pointer;font-weight:650;color:#1d4ed8}}pre{{white-space:pre-wrap;max-height:400px;overflow:auto;padding:12px;background:#f8fafc;border:1px solid var(--border);font:12px/1.5 ui-monospace,monospace}}
@media(max-width:740px){{.card-body{{grid-template-columns:1fr}}dl>div{{grid-template-columns:110px 1fr}}}}
</style></head><body><main>
<h1>Round 3 ground truth review</h1>
<p class="intro">Read-only view of <a href="round3-ground-truth-review.json">round3-ground-truth-review.json</a>.
It contains {len(records)} adjudicated disagreements across {len(set(r["round_id"] for r in records))} directives.
Unanimously labeled subdirectives are outside this JSON file.</p>
<div class="counts">{count_html}</div>
{''.join(sections)}
</main></body></html>'''


def main() -> None:
    review = json.loads(SOURCE.read_text(encoding="utf-8"))
    metadata, chunks, doc_texts = extract_source_data(VIEWER.read_text(encoding="utf-8"))
    OUTPUT.write_text(build_html(review, metadata, chunks, doc_texts), encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)} ({len(review['records'])} records)")


if __name__ == "__main__":
    main()
