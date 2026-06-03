"""
Generate a static HTML viewer for inspecting segmenter output.

Usage (from project root):
  python src/view_segments.py                  # 50 memos, mixed admins/lengths
  python src/view_segments.py --type letter    # different doc type
  python src/view_segments.py --n 20           # fewer docs
  python src/view_segments.py --id 42          # specific row index from CSV

Output: data/sample_segmentation/segments_viewer.html
"""

import argparse
import csv
import html
import random
import re
from pathlib import Path

from segmenter import Segment, segment

ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "data" / "4_28_2026_build.csv"
OUT_FILE = ROOT / "data" / "sample_segmentation" / "segments_viewer.html"

TYPE_COLORS = {
    "metadata":    ("#6b7280", "#f3f4f6"),  # gray
    "section":     ("#1d4ed8", "#dbeafe"),  # blue
    "paragraph":   ("#065f46", "#d1fae5"),  # green
    "boilerplate": ("#92400e", "#fef3c7"),  # amber
}


def load_rows(doc_type: str, n: int, specific_id: int | None) -> list[dict]:
    with open(DATA_FILE) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if specific_id is not None:
        return [rows[specific_id]]

    pool = [r for r in rows if r["doc_type"] == doc_type]

    # Sample across presidents and length tiers for coverage
    random.seed(0)
    tiers = [
        [r for r in pool if len(r["doc_text"]) < 1000],
        [r for r in pool if 1000 <= len(r["doc_text"]) < 5000],
        [r for r in pool if 5000 <= len(r["doc_text"]) < 15000],
        [r for r in pool if len(r["doc_text"]) >= 15000],
    ]
    per_tier = max(1, n // len(tiers))
    sample = []
    for tier in tiers:
        sample.extend(random.sample(tier, min(per_tier, len(tier))))
    return sample[:n]


def render_original(doc_text: str) -> str:
    chunks = re.split(r"  +", doc_text)
    parts = []
    for c in chunks:
        c = c.strip()
        if c:
            parts.append(f'<p class="orig-para">{html.escape(c)}</p>')
    return "\n".join(parts)


def render_segments(segments: list[Segment]) -> str:
    parts = []
    content_n = 0
    for seg in segments:
        fg, bg = TYPE_COLORS.get(seg.seg_type, ("#111", "#fff"))
        label = seg.seg_type
        text_e = html.escape(seg.text)
        if seg.seg_type == "metadata":
            parts.append(
                f'<div class="seg seg-meta" style="border-left:3px solid {fg};background:{bg}">'
                f'<span class="seg-label" style="color:{fg}">{label}</span>'
                f'<span class="seg-text">{text_e}</span></div>'
            )
        else:
            content_n += 1
            parts.append(
                f'<div class="seg" style="border-left:4px solid {fg};background:{bg}">'
                f'<span class="seg-num" style="color:{fg}">#{content_n}</span>'
                f'<span class="seg-label" style="color:{fg}">{label}</span>'
                f'<span class="seg-text">{text_e}</span></div>'
            )
    return "\n".join(parts)


def build_html(rows: list[dict]) -> str:
    doc_blocks = []
    for row in rows:
        segs = segment(row["doc_text"], row["doc_type"], split_subsections=False)
        content_segs = [s for s in segs if s.seg_type != "metadata"]
        orig_html = render_original(row["doc_text"])
        segs_html = render_segments(segs)
        url = html.escape(row["url"])
        president = html.escape(row["president"])
        date = html.escape(row["date"])
        doc_type = html.escape(row["doc_type"])
        char_len = len(row["doc_text"])
        truncated = " <span class='trunc'>[TRUNCATED]</span>" if char_len == 32766 else ""

        doc_blocks.append(f"""
<details class="doc-block" open>
  <summary>
    <span class="doc-prez">{president}</span>
    <span class="doc-date">{date}</span>
    <span class="doc-type">{doc_type}</span>
    <span class="doc-stats">{len(segs)} chunks &rarr; {len(content_segs)} segments{truncated}</span>
    <a href="{url}" target="_blank" class="doc-link">original &rarr;</a>
  </summary>
  <div class="doc-body">
    <div class="col">
      <h3>Original text</h3>
      {orig_html}
    </div>
    <div class="col">
      <h3>Segments</h3>
      {segs_html}
    </div>
  </div>
</details>
""")

    body = "\n".join(doc_blocks)

    legend_items = "".join(
        f'<span class="leg-item" style="background:{bg};border-left:4px solid {fg};color:{fg}">{t}</span>'
        for t, (fg, bg) in TYPE_COLORS.items()
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Segment viewer</title>
<style>
  body {{ font-family: system-ui, sans-serif; font-size: 13px; margin: 0; padding: 16px; background: #f9fafb; color: #111; }}
  h1 {{ font-size: 1.2rem; margin-bottom: 4px; }}
  .legend {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }}
  .leg-item {{ padding: 2px 8px; border-radius: 3px; font-size: 11px; font-weight: 600; }}
  .doc-block {{ background: white; border: 1px solid #e5e7eb; border-radius: 6px; margin-bottom: 12px; }}
  .doc-block > summary {{ cursor: pointer; padding: 10px 14px; display: flex; gap: 12px; align-items: baseline; list-style: none; }}
  .doc-block > summary::-webkit-details-marker {{ display: none; }}
  .doc-prez {{ font-weight: 600; }}
  .doc-date {{ color: #6b7280; }}
  .doc-type {{ font-style: italic; color: #6b7280; }}
  .doc-stats {{ color: #9ca3af; font-size: 11px; margin-left: auto; }}
  .doc-link {{ font-size: 11px; color: #2563eb; text-decoration: none; }}
  .doc-link:hover {{ text-decoration: underline; }}
  .trunc {{ color: #dc2626; font-weight: 600; }}
  .doc-body {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0; border-top: 1px solid #e5e7eb; }}
  .col {{ padding: 12px 16px; overflow-y: auto; max-height: 600px; }}
  .col + .col {{ border-left: 1px solid #e5e7eb; }}
  .col h3 {{ font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: #9ca3af; margin: 0 0 10px; }}
  .orig-para {{ margin: 0 0 8px; padding: 6px 8px; background: #f9fafb; border-radius: 3px; line-height: 1.5; }}
  .seg {{ margin: 0 0 6px; padding: 6px 8px; border-radius: 3px; line-height: 1.5; }}
  .seg-meta {{ opacity: .7; }}
  .seg-label {{ font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; margin-right: 6px; }}
  .seg-num {{ font-size: 10px; font-weight: 700; margin-right: 4px; }}
  .seg-text {{ }}
</style>
</head>
<body>
<h1>Segment viewer &mdash; {len(rows)} documents</h1>
<div class="legend">{legend_items}</div>
{body}
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", default="memorandum")
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--id", type=int, default=None, dest="row_id")
    args = parser.parse_args()

    rows = load_rows(args.type, args.n, args.row_id)
    html_out = build_html(rows)
    OUT_FILE.write_text(html_out)
    print(f"Wrote {OUT_FILE}  ({len(rows)} docs)")


if __name__ == "__main__":
    main()
