"""
Generate a static HTML viewer for inspecting segmenter output.

Documents are presented in tabs, one tab per document type.  Each document
gets an alphanumeric ID that restarts per tab (EO1, EO2, …; M1, M2, …;
L1, L2, …; P1, P2, …).

A toggle in the top bar switches between two segmentation strategies:
  "Section/Paragraph" — structural segmentation (segment())
  "Woolley & Peters"  — ordering-phrase segmentation (segment_ordering())

The left column of each document is a free-form annotation canvas: select
any span of text, then click a label in the floating picker.  Annotations
are saved to localStorage and can be exported as JSON.

Usage (from project root):
  python src/view_segments.py              # 5 docs per type (20 total)
  python src/view_segments.py --n 10       # 10 docs per type
  python src/view_segments.py --id 42      # one specific row by CSV index

Output: data/sample_segmentation/segments_viewer.html
"""

import argparse
import csv
import html
import json
import random
import re
import statistics
from collections import Counter
from pathlib import Path

from segmenter import Segment, segment, segment_ordering, _get_ordering_re

ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "data" / "4_28_2026_build_dev.csv"
OUT_FILE = ROOT / "data" / "sample_segmentation" / "segments_viewer.html"
HOLDOUT_IDS: set[int] = set(json.load(open(ROOT / "data" / "holdout_ids.json")))

# Document types to show, in tab order, with their prefix and label
DOC_TYPES = [
    ("executive_order", "EO", "Executive Orders"),
    ("memorandum",      "M",  "Memos"),
    ("letter",          "L",  "Letters"),
    ("proclamation",    "P",  "Proclamations"),
]

# Section/Paragraph strategy colors
SP_COLORS = {
    "metadata":       ("#6b7280", "#f3f4f6"),  # gray
    "vesting_clause": ("#6d28d9", "#ede9fe"),  # purple
    "section":        ("#1d4ed8", "#dbeafe"),  # blue
    "paragraph":      ("#065f46", "#d1fae5"),  # green
    "boilerplate":    ("#92400e", "#fef3c7"),  # amber
}

# Woolley & Peters strategy colors
WP_COLORS = {
    "preamble":        ("#6b7280", "#f3f4f6"),  # gray
    "ordering_phrase": ("#0f766e", "#ccfbf1"),  # teal
    "order_action":    ("#b91c1c", "#fee2e2"),  # red
    "metadata":        ("#6b7280", "#f3f4f6"),  # gray   (same as S/P)
    "boilerplate":     ("#92400e", "#fef3c7"),  # amber  (same as S/P)
    "vesting_clause":  ("#6d28d9", "#ede9fe"),  # purple (same as S/P)
}

# All label colors used by the annotation picker (superset of both strategies)
ANNOTATION_COLORS = {
    "preamble":        ("#6b7280", "#f3f4f6"),
    "ordering_phrase": ("#0f766e", "#ccfbf1"),
    "order_action":    ("#b91c1c", "#fee2e2"),
    "vesting_clause":  ("#6d28d9", "#ede9fe"),
    "metadata":        ("#6b7280", "#f3f4f6"),
    "boilerplate":     ("#92400e", "#fef3c7"),
    "section":         ("#1d4ed8", "#dbeafe"),
    "paragraph":       ("#065f46", "#d1fae5"),
}

# ── Classification taxonomy ───────────────────────────────────────────────────
CATEGORIES = [
    ("ceremonial",  "Ceremonial/Expressive"),
    ("internal",    "Internal Management"),
    ("policy",      "Policy Setting"),
    ("other",       "Other"),
]
LEGAL_EFFECT_OPTIONS = [
    ("legal",    "Likely legal effect"),
    ("nonlegal", "Non-legally binding"),
]
SCOPE_OPTIONS = [
    ("domestic", "Domestic"),
    ("foreign",  "Foreign"),
]


def load_rows(doc_type: str, n: int, seed: int = 42) -> list[dict]:
    with open(DATA_FILE) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    pool = [r for r in rows if r["doc_type"] == doc_type and int(r[""]) not in HOLDOUT_IDS]

    # Sample across length tiers for coverage
    random.seed(seed)
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


def display_text(doc_text: str) -> str:
    """Join double-space-separated chunks with blank lines for readable display."""
    return "\n\n".join(c.strip() for c in re.split(r"  +", doc_text) if c.strip())


def render_classification_form(prefix: str) -> str:
    """HTML for the full classification taxonomy, namespaced by prefix.

    prefix should be unique per form instance (e.g. 'EO1-doc' or 'EO1-chunk-3').
    JS will read/write values using data-prefix attributes.
    """
    cat_radios = "".join(
        f'<label class="clf-radio-label">'
        f'<input type="radio" name="{prefix}-cat" value="{val}" class="clf-cat-radio" data-prefix="{prefix}"> {lbl}'
        f'</label>'
        for val, lbl in CATEGORIES
    )
    legal_radios = "".join(
        f'<label class="clf-radio-label">'
        f'<input type="radio" name="{prefix}-legal" value="{val}" class="clf-legal-radio" data-prefix="{prefix}"> {lbl}'
        f'</label>'
        for val, lbl in LEGAL_EFFECT_OPTIONS
    )
    scope_radios = "".join(
        f'<label class="clf-radio-label">'
        f'<input type="radio" name="{prefix}-scope" value="{val}" class="clf-scope-radio" data-prefix="{prefix}"> {lbl}'
        f'</label>'
        for val, lbl in SCOPE_OPTIONS
    )
    return f"""<div class="clf-form" data-prefix="{prefix}">
  <div class="clf-row">
    <span class="clf-label">Category</span>
    <button type="button" class="clf-help-btn" title="Category descriptions">?</button>
    <div class="clf-radios">{cat_radios}</div>
  </div>
  <div class="clf-row clf-legal-row" style="display:none">
    <span class="clf-label">Legal effect</span>
    <div class="clf-radios">{legal_radios}</div>
  </div>
  <div class="clf-row">
    <span class="clf-label">Scope</span>
    <div class="clf-radios">{scope_radios}</div>
  </div>
  <div class="clf-row clf-ns-row" style="display:none">
    <span class="clf-label">National security?</span>
    <div class="clf-radios">
      <label class="clf-radio-label"><input type="radio" name="{prefix}-ns" value="yes" class="clf-ns-radio" data-prefix="{prefix}"> Yes</label>
      <label class="clf-radio-label"><input type="radio" name="{prefix}-ns" value="no"  class="clf-ns-radio" data-prefix="{prefix}"> No</label>
    </div>
  </div>
  <div class="clf-row">
    <span class="clf-label">Emergency?</span>
    <div class="clf-radios">
      <label class="clf-radio-label"><input type="radio" name="{prefix}-emerg" value="yes" class="clf-emerg-radio" data-prefix="{prefix}"> Yes</label>
      <label class="clf-radio-label"><input type="radio" name="{prefix}-emerg" value="no"  class="clf-emerg-radio" data-prefix="{prefix}"> No</label>
    </div>
  </div>
</div>"""


def render_annotation_area(doc_text: str, doc_id: str) -> str:
    """Left column: full document text as a free-form annotation canvas."""
    escaped = html.escape(display_text(doc_text))
    return (
        f'<div class="annot-area" data-doc="{doc_id}">'
        f'<div class="annot-text">{escaped}</div>'
        f'</div>'
    )


def render_sp_segments(segments: list[Segment]) -> str:
    """Render Section/Paragraph strategy segments."""
    parts = []
    content_n = 0
    for seg in segments:
        fg, bg = SP_COLORS.get(seg.seg_type, ("#111", "#fff"))
        label = seg.seg_type
        text_e = html.escape(seg.text)
        if seg.seg_type == "metadata":
            parts.append(
                f'<div class="seg seg-meta" style="border-left:3px solid {fg};background:{bg}">'
                f'<span class="seg-label" style="color:{fg}">{label}</span>'
                f'<span class="seg-text">{text_e}</span></div>'
            )
        elif seg.seg_type in ("boilerplate", "vesting_clause"):
            parts.append(
                f'<div class="seg" style="border-left:3px solid {fg};background:{bg}">'
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


def _highlight_ordering_phrases(text_escaped: str) -> str:
    """Wrap matched ordering phrases in <strong class='op'> for visibility."""
    ordering_re = _get_ordering_re()
    def replacer(m: re.Match) -> str:
        return f'<strong class="op">{m.group(0)}</strong>'
    return ordering_re.sub(replacer, text_escaped)


def render_wp_segments(segments: list[Segment], doc_id: str = "") -> str:
    """Render Woolley & Peters ordering-phrase strategy segments."""
    parts = []
    directive_n = 0
    for seg in segments:
        fg, bg = WP_COLORS.get(seg.seg_type, ("#111", "#fff"))
        label = seg.seg_type
        text_e = html.escape(seg.text)
        if seg.seg_type == "order_action":
            directive_n += 1
            text_highlighted = _highlight_ordering_phrases(text_e)
            chunk_key = f"{doc_id}-chunk-{directive_n}"
            parts.append(
                f'<div class="seg seg-chunk" style="border-left:4px solid {fg};background:{bg};cursor:pointer"'
                f' data-chunkkey="{chunk_key}" data-doc="{doc_id}" data-chunkn="{directive_n}"'
                f' title="Click to classify this directive">'
                f'<span class="seg-num" style="color:{fg}">#{directive_n}</span>'
                f'<span class="seg-label" style="color:{fg}">{label}</span>'
                f'<span class="seg-text">{text_highlighted}</span>'
                f'<span class="chunk-badge" id="badge-{chunk_key}"></span>'
                f'</div>'
            )
        elif seg.seg_type == "ordering_phrase":
            text_highlighted = _highlight_ordering_phrases(text_e)
            parts.append(
                f'<div class="seg" style="border-left:3px solid {fg};background:{bg}">'
                f'<span class="seg-label" style="color:{fg}">{label}</span>'
                f'<span class="seg-text">{text_highlighted}</span></div>'
            )
        else:
            parts.append(
                f'<div class="seg seg-meta" style="border-left:3px solid {fg};background:{bg}">'
                f'<span class="seg-label" style="color:{fg}">{label}</span>'
                f'<span class="seg-text">{text_e}</span></div>'
            )
    return "\n".join(parts)


def build_doc_block(row: dict, doc_id: str) -> str:
    # Section/Paragraph segmentation
    sp_segs = segment(row["doc_text"], row["doc_type"], split_subsections=False)
    sp_content = [s for s in sp_segs if s.seg_type not in ("metadata",)]
    sp_html = render_sp_segments(sp_segs)

    # Woolley & Peters segmentation
    wp_segs = segment_ordering(row["doc_text"], row["doc_type"])
    wp_directives = [s for s in wp_segs if s.seg_type == "order_action"]
    wp_html = render_wp_segments(wp_segs, doc_id=doc_id)

    annot_html = render_annotation_area(row["doc_text"], doc_id)
    url = html.escape(row["url"])
    president = html.escape(row["president"])
    date = html.escape(row["date"])
    doc_type = html.escape(row["doc_type"])
    char_len = len(row["doc_text"])
    truncated = " <span class='trunc'>[TRUNCATED]</span>" if char_len == 32766 else ""

    return f"""
<details class="doc-block" open>
  <summary>
    <span class="doc-id">{doc_id}</span>
    <span class="doc-prez">{president}</span>
    <span class="doc-date">{date}</span>
    <span class="doc-type">{doc_type}</span>
    <span class="doc-stats mode-sp-stat">{len(sp_segs)} chunks &rarr; {len(sp_content)} segments{truncated}</span>
    <span class="doc-stats mode-wp-stat">{len(wp_directives)} directives{truncated}</span>
    <a href="{url}" target="_blank" class="doc-link">original &rarr;</a>
  </summary>
  <div class="doc-body">
    <div class="col">
      <h3>Annotate &mdash; select text, then choose a label</h3>
      {annot_html}
    </div>
    <div class="col">
      <div class="seg-view view-sp">
        <h3>Section / Paragraph &mdash; {len(sp_content)} segments</h3>
        {sp_html}
      </div>
      <div class="seg-view view-wp">
        <h3>Woolley &amp; Peters &mdash; {len(wp_directives)} directives</h3>
        {wp_html}
      </div>
    </div>
  </div>
  <div class="clf-panel" data-doc="{doc_id}">
    <div class="clf-panel-header">
      <span class="clf-panel-title">Document classification &mdash; {doc_id}</span>
      <span class="clf-panel-hint">Classify the document as a whole, then click each W&amp;P directive (right column) to classify it individually.</span>
    </div>
    {render_classification_form(f"{doc_id}-doc")}
  </div>
  <div class="feedback-bar fb-sp">
    <span class="fb-label">S/P quality:</span>
    <button class="fb-btn fb-ok"  data-doc="{doc_id}" data-val="correct"        data-strategy="sp">&#10003; Correct</button>
    <button class="fb-btn fb-bad" data-doc="{doc_id}" data-val="needs-revision" data-strategy="sp">&#10007; Needs revision</button>
    <textarea class="fb-comment" data-doc="{doc_id}" data-strategy="sp" placeholder="Optional notes…" rows="2"></textarea>
  </div>
  <div class="feedback-bar fb-wp">
    <span class="fb-label">W&amp;P quality:</span>
    <button class="fb-btn fb-ok"  data-doc="{doc_id}" data-val="correct"        data-strategy="wp">&#10003; Correct</button>
    <button class="fb-btn fb-bad" data-doc="{doc_id}" data-val="needs-revision" data-strategy="wp">&#10007; Needs revision</button>
    <textarea class="fb-comment" data-doc="{doc_id}" data-strategy="wp" placeholder="Optional notes…" rows="2"></textarea>
  </div>
</details>"""


def compute_label_stats(rows_by_type):
    """Per-label count stats (min/median/max/std dev) across all docs in the sample."""
    sp_counts = {label: [] for label in SP_COLORS}
    wp_counts = {label: [] for label in WP_COLORS}
    for _, _, _, rows in rows_by_type:
        for row in rows:
            sp_segs = segment(row["doc_text"], row["doc_type"], split_subsections=False)
            wp_segs = segment_ordering(row["doc_text"], row["doc_type"])
            sp_doc = Counter(s.seg_type for s in sp_segs)
            wp_doc = Counter(s.seg_type for s in wp_segs)
            for label in SP_COLORS:
                sp_counts[label].append(sp_doc.get(label, 0))
            for label in WP_COLORS:
                wp_counts[label].append(wp_doc.get(label, 0))

    def _stats(counts):
        return {
            "min": min(counts),
            "median": round(statistics.median(counts), 1),
            "max": max(counts),
            "std": round(statistics.stdev(counts) if len(counts) > 1 else 0.0, 2),
        }

    return (
        {lbl: _stats(v) for lbl, v in sp_counts.items()},
        {lbl: _stats(v) for lbl, v in wp_counts.items()},
    )


def _legend_html(colors: dict) -> str:
    return "".join(
        f'<span class="leg-item" style="background:{bg};border-left:4px solid {fg};color:{fg}">{t}</span>'
        for t, (fg, bg) in colors.items()
    )


def build_html(rows_by_type: list[tuple[str, str, str, list[dict]]], seed: int = 42, viewer_num: int = 1) -> str:
    """Build the full HTML page with doc-type tabs and a strategy toggle."""
    # Category descriptions for the help modal
    cat_desc_path = ROOT / "methodology" / "category_descriptions.md"
    cat_desc_escaped = html.escape(cat_desc_path.read_text()) if cat_desc_path.exists() else "(descriptions not found)"

    sp_legend = _legend_html(SP_COLORS)
    wp_legend = _legend_html(WP_COLORS)

    total_docs = sum(len(rows) for _, _, _, rows in rows_by_type)

    # Aggregate label stats across all docs in the sample
    sp_stats, wp_stats = compute_label_stats(rows_by_type)

    def _stats_rows(stats_dict, colors):
        parts = []
        for label, s in stats_dict.items():
            fg, _ = colors[label]
            parts.append(
                f'<tr><td style="color:{fg};font-weight:700">{label}</td>'
                f'<td>{s["min"]}</td><td>{s["median"]}</td>'
                f'<td>{s["max"]}</td><td>{s["std"]}</td></tr>'
            )
        return "\n".join(parts)

    stats_html = f"""<details class="stats-panel">
  <summary>Aggregate label stats &mdash; {total_docs} docs (counts per document)</summary>
  <div class="stats-sp">
    <table class="stats-table">
      <tr><th>Label</th><th>Min</th><th>Median</th><th>Max</th><th>Std dev</th></tr>
      {_stats_rows(sp_stats, SP_COLORS)}
    </table>
  </div>
  <div class="stats-wp">
    <table class="stats-table">
      <tr><th>Label</th><th>Min</th><th>Median</th><th>Max</th><th>Std dev</th></tr>
      {_stats_rows(wp_stats, WP_COLORS)}
    </table>
  </div>
</details>"""

    # Build DOC_TEXTS for the annotation JS (plain display text per doc_id)
    doc_texts: dict[str, str] = {}
    for _, prefix, _, rows in rows_by_type:
        for j, row in enumerate(rows, start=1):
            doc_texts[f"{prefix}{j}"] = display_text(row["doc_text"])
    doc_texts_js = "var DOC_TEXTS=" + json.dumps(doc_texts, ensure_ascii=False) + ";"

    # Annotation label picker buttons (one per label, styled to match colors)
    picker_btns = "".join(
        f'<button class="pick-btn" data-label="{lbl}"'
        f' style="background:{bg};border-color:{fg};color:{fg}">{lbl}</button>'
        for lbl, (fg, bg) in ANNOTATION_COLORS.items()
    )

    # Strategy toggle
    strategy_toggle = """
<div class="strategy-toggle">
  <span class="strategy-label">Strategy:</span>
  <button class="strat-btn active" data-mode="sp">Section / Paragraph</button>
  <button class="strat-btn" data-mode="wp">Woolley &amp; Peters</button>
</div>"""

    # Doc-type tabs
    tab_buttons = []
    tab_panels = []

    for i, (doc_type_key, prefix, tab_label, rows) in enumerate(rows_by_type):
        panel_id = f"panel-{doc_type_key}"
        active_btn   = " active" if i == 0 else ""
        active_panel = " active" if i == 0 else ""

        tab_buttons.append(
            f'<button class="tab-btn{active_btn}" data-panel="{panel_id}">'
            f'{tab_label} <span class="tab-count">({len(rows)})</span></button>'
        )

        doc_blocks = []
        for j, row in enumerate(rows, start=1):
            doc_blocks.append(build_doc_block(row, f"{prefix}{j}"))

        tab_panels.append(
            f'<div class="tab-panel{active_panel}" id="{panel_id}">'
            + "\n".join(doc_blocks)
            + '</div>'
        )

    tab_bar    = "\n".join(tab_buttons)
    panels_html = "\n".join(tab_panels)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Segment viewer</title>
<style>
  body {{ font-family: system-ui, sans-serif; font-size: 13px; margin: 0; padding: 16px; background: #f9fafb; color: #111; }}
  h1 {{ font-size: 1.2rem; margin-bottom: 4px; }}
  /* Top bar */
  .top-bar {{ position: sticky; top: 0; z-index: 10; background: #f9fafb; padding-bottom: 0; }}
  /* Strategy toggle */
  .strategy-toggle {{ display: flex; align-items: center; gap: 6px; margin-bottom: 8px; }}
  .strategy-label {{ font-size: 12px; font-weight: 600; color: #6b7280; }}
  .strat-btn {{
    padding: 4px 12px; font-size: 12px; font-weight: 600; cursor: pointer;
    background: #e5e7eb; border: 1px solid #d1d5db; border-radius: 4px; color: #374151;
  }}
  .strat-btn.active {{ background: #1d4ed8; color: white; border-color: #1d4ed8; }}
  /* Legends */
  .legend {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }}
  .leg-item {{ padding: 2px 8px; border-radius: 3px; font-size: 11px; font-weight: 600; }}
  /* Tab bar */
  .tab-bar {{ display: flex; gap: 4px; border-bottom: 2px solid #e5e7eb; margin-bottom: 0; }}
  .tab-btn {{
    padding: 6px 14px; font-size: 13px; font-weight: 600; cursor: pointer;
    background: none; border: none; border-bottom: 3px solid transparent;
    margin-bottom: -2px; color: #6b7280;
  }}
  .tab-btn:hover {{ color: #1d4ed8; }}
  .tab-btn.active {{ color: #1d4ed8; border-bottom-color: #1d4ed8; }}
  .tab-count {{ font-weight: 400; color: #9ca3af; }}
  /* Tab panels */
  .tab-panel {{ display: none; padding-top: 12px; }}
  .tab-panel.active {{ display: block; }}
  /* Doc blocks */
  .doc-block {{ background: white; border: 1px solid #e5e7eb; border-radius: 6px; margin-bottom: 12px; }}
  .doc-block > summary {{
    cursor: pointer; padding: 14px 18px; display: flex; gap: 14px;
    align-items: baseline; list-style: none; border-bottom: 1px solid #f3f4f6;
  }}
  .doc-block > summary::-webkit-details-marker {{ display: none; }}
  .doc-id    {{ font-weight: 800; font-size: 17px; color: #1d4ed8; min-width: 3.2em; }}
  .doc-prez  {{ font-weight: 700; font-size: 16px; }}
  .doc-date  {{ color: #6b7280; font-size: 14px; }}
  .doc-type  {{ font-style: italic; color: #6b7280; font-size: 14px; }}
  .doc-stats {{ color: #9ca3af; font-size: 12px; margin-left: auto; }}
  .doc-link  {{ font-size: 12px; color: #2563eb; text-decoration: none; }}
  .doc-link:hover {{ text-decoration: underline; }}
  .trunc {{ color: #dc2626; font-weight: 600; }}
  /* Two-column body */
  .doc-body {{ display: grid; grid-template-columns: 1fr 1fr; border-top: 1px solid #e5e7eb; }}
  .col {{ padding: 12px 16px; overflow-y: auto; max-height: 600px; }}
  .col + .col {{ border-left: 1px solid #e5e7eb; }}
  .col > h3 {{ font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: #9ca3af; margin: 0 0 10px; }}
  /* Annotation canvas (left column) */
  .annot-area {{ }}
  .annot-text {{
    white-space: pre-wrap; word-wrap: break-word;
    font-size: 12px; line-height: 1.75; cursor: text;
  }}
  .ann-span {{ border-radius: 2px; cursor: pointer; }}
  .ann-tag {{
    font-size: 9px; font-weight: 700; text-transform: uppercase;
    letter-spacing: .03em; margin-left: 3px; vertical-align: super; cursor: pointer;
    user-select: none; -webkit-user-select: none;
  }}
  /* Floating label picker */
  #label-picker {{
    display: none; position: fixed; z-index: 200;
    background: white; border: 1px solid #d1d5db; border-radius: 8px;
    box-shadow: 0 4px 16px rgba(0,0,0,.18); padding: 8px; min-width: 150px;
  }}
  .pick-btn {{
    display: block; width: 100%; text-align: left; padding: 5px 10px; margin-bottom: 3px;
    font-size: 11px; font-weight: 700; cursor: pointer; border: 1px solid; border-radius: 4px;
  }}
  .pick-btn:last-of-type {{ margin-bottom: 0; }}
  .pick-clear {{
    display: none; width: 100%; margin-top: 6px; padding: 5px 10px;
    font-size: 11px; font-weight: 700; cursor: pointer;
    background: #fee2e2; border: 1px solid #fca5a5; border-radius: 4px; color: #b91c1c;
  }}
  /* Segment views (right column) */
  .seg-view h3 {{ font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: #9ca3af; margin: 0 0 10px; }}
  .seg {{ margin: 0 0 6px; padding: 6px 8px; border-radius: 3px; line-height: 1.5; }}
  .seg-meta {{ opacity: .7; }}
  .seg-label {{ font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; margin-right: 6px; }}
  .seg-num   {{ font-size: 10px; font-weight: 700; margin-right: 4px; }}
  .seg-text  {{ }}
  strong.op  {{ background: rgba(185,28,28,.12); border-radius: 2px; padding: 0 2px; }}
  /* Feedback bar */
  .feedback-bar {{
    border-top: 2px solid #e5e7eb; padding: 10px 18px;
    display: flex; flex-wrap: wrap; gap: 8px; align-items: flex-start;
    background: #f9fafb; border-radius: 0 0 6px 6px;
  }}
  .fb-label {{ font-size: 12px; font-weight: 600; color: #6b7280; line-height: 28px; }}
  .fb-btn {{
    padding: 5px 14px; font-size: 12px; font-weight: 700; cursor: pointer;
    border-radius: 4px; border: 2px solid transparent;
  }}
  .fb-ok  {{ background: #d1fae5; color: #065f46; border-color: #6ee7b7; }}
  .fb-ok.active  {{ background: #059669; color: white; border-color: #059669; }}
  .fb-bad {{ background: #fee2e2; color: #b91c1c; border-color: #fca5a5; }}
  .fb-bad.active {{ background: #dc2626; color: white; border-color: #dc2626; }}
  .fb-comment {{
    display: none; width: 100%; margin-top: 4px; box-sizing: border-box;
    font-size: 12px; font-family: inherit; border: 1px solid #d1d5db;
    border-radius: 4px; padding: 6px 8px; resize: vertical;
  }}
  /* Export button */
  .export-btn {{
    margin-left: auto; padding: 4px 12px; font-size: 12px; font-weight: 600;
    cursor: pointer; background: #e5e7eb; border: 1px solid #d1d5db;
    border-radius: 4px; color: #374151;
  }}
  .export-btn:hover {{ background: #d1d5db; }}
  /* Annotator name input */
  #annotator-name {{
    font-size: 15px; padding: 6px 10px; border: 2px solid #6b7280;
    border-radius: 6px; font-family: inherit; width: 200px; font-weight: 600;
  }}
  #annotator-name:focus {{ outline: none; border-color: #2563eb; box-shadow: 0 0 0 3px #bfdbfe; }}
  /* Mode-controlled visibility */
  body.mode-sp .view-wp {{ display: none; }}
  body.mode-wp .view-sp {{ display: none; }}
  body.mode-sp .mode-wp-stat {{ display: none; }}
  body.mode-wp .mode-sp-stat {{ display: none; }}
  body.mode-sp .leg-wp {{ display: none; }}
  body.mode-wp .leg-sp {{ display: none; }}
  body.mode-sp .fb-wp {{ display: none; }}
  body.mode-wp .fb-sp {{ display: none; }}
  /* Aggregate stats panel */
  .stats-panel {{ border: 1px solid #e5e7eb; border-radius: 6px; background: white; padding: 8px 12px; margin-bottom: 12px; }}
  .stats-panel > summary {{ cursor: pointer; font-size: 12px; font-weight: 600; color: #6b7280; user-select: none; }}
  .stats-table {{ border-collapse: collapse; font-size: 12px; margin-top: 6px; }}
  .stats-table th, .stats-table td {{ padding: 3px 20px 3px 0; text-align: right; }}
  .stats-table th:first-child, .stats-table td:first-child {{ text-align: left; padding-right: 16px; }}
  .stats-table th {{ color: #9ca3af; font-weight: 600; border-bottom: 1px solid #e5e7eb; }}
  body.mode-sp .stats-wp {{ display: none; }}
  body.mode-wp .stats-sp {{ display: none; }}
  /* Classification panel */
  .clf-panel {{
    border-top: 2px solid #e5e7eb; padding: 10px 18px 14px;
    background: #f0f4ff;
  }}
  .clf-panel-header {{ display: flex; align-items: baseline; gap: 12px; margin-bottom: 8px; }}
  .clf-panel-title {{ font-size: 12px; font-weight: 700; color: #1d4ed8; }}
  .clf-panel-hint {{ font-size: 11px; color: #6b7280; }}
  /* Classification form rows */
  .clf-form {{ display: flex; flex-direction: column; gap: 6px; }}
  .clf-row {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
  .clf-label {{ font-size: 14px; font-weight: 700; color: #374151; min-width: 120px; white-space: nowrap; }}
  .clf-radios {{ display: flex; gap: 10px; flex-wrap: wrap; }}
  .clf-radio-label {{ font-size: 14px; display: flex; align-items: center; gap: 4px; cursor: pointer; }}
  .clf-help-btn {{
    padding: 1px 6px; font-size: 11px; font-weight: 700; cursor: pointer;
    background: #dbeafe; border: 1px solid #93c5fd; border-radius: 10px; color: #1d4ed8;
    line-height: 1.4;
  }}
  .clf-help-btn:hover {{ background: #bfdbfe; }}
  /* Chunk badge */
  .chunk-badge {{
    display: inline-block; margin-left: 8px; font-size: 10px; font-weight: 700;
    background: #1d4ed8; color: white; padding: 1px 6px; border-radius: 8px;
    vertical-align: middle; white-space: nowrap;
  }}
  .chunk-badge:empty {{ display: none; }}
  /* Clickable chunk hover */
  .seg-chunk:hover {{ filter: brightness(0.95); }}
  /* Inline classification badge on left-side annotation spans */
  .ann-clf-badge {{
    font-size: 9px; font-weight: 700; background: #1d4ed8; color: white;
    padding: 1px 5px; border-radius: 6px; margin-left: 3px; vertical-align: super;
    user-select: none; -webkit-user-select: none;
  }}
  /* Context menu for ann-span clicks (order_action spans) */
  #ann-context-menu {{
    display: none; position: fixed; z-index: 250;
    background: white; border: 1px solid #d1d5db; border-radius: 6px;
    box-shadow: 0 3px 12px rgba(0,0,0,.16); padding: 4px;
    min-width: 140px;
  }}
  .ann-ctx-btn {{
    display: block; width: 100%; text-align: left; padding: 6px 10px;
    font-size: 12px; font-weight: 600; cursor: pointer; border: none;
    background: none; border-radius: 4px; color: #374151;
  }}
  .ann-ctx-btn:hover {{ background: #f3f4f6; }}
  /* Chunk classification popup */
  #chunk-popup {{
    display: none; position: fixed; z-index: 300;
    background: white; border: 1px solid #d1d5db; border-radius: 8px;
    box-shadow: 0 4px 20px rgba(0,0,0,.2); padding: 12px 14px;
    min-width: 320px; max-width: 420px;
  }}
  .chunk-popup-header {{
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 10px;
  }}
  .chunk-popup-title {{ font-size: 12px; font-weight: 700; color: #b91c1c; }}
  .chunk-popup-close {{
    background: none; border: none; font-size: 16px; cursor: pointer; color: #6b7280; line-height: 1;
  }}
  /* Category descriptions modal */
  #cat-modal-overlay {{
    display: none; position: fixed; inset: 0; z-index: 400;
    background: rgba(0,0,0,.45);
  }}
  #cat-modal {{
    position: fixed; top: 50%; left: 50%; transform: translate(-50%,-50%);
    z-index: 401; background: white; border-radius: 8px;
    box-shadow: 0 8px 40px rgba(0,0,0,.25); padding: 20px 24px;
    max-width: 700px; width: 90vw; max-height: 80vh; overflow-y: auto;
  }}
  #cat-modal h2 {{ font-size: 14px; margin: 0 0 12px; color: #111; }}
  #cat-modal pre {{ white-space: pre-wrap; font-size: 12px; line-height: 1.65; font-family: inherit; margin: 0; }}
  .cat-modal-close {{
    float: right; background: none; border: none; font-size: 18px;
    cursor: pointer; color: #6b7280; line-height: 1; margin-left: 12px;
  }}
</style>
</head>
<body class="mode-sp">

<!-- Category descriptions modal -->
<div id="cat-modal-overlay">
  <div id="cat-modal">
    <button class="cat-modal-close" id="cat-modal-close" title="Close">&times;</button>
    <h2>Category Descriptions</h2>
    <pre>{cat_desc_escaped}</pre>
  </div>
</div>

<!-- Chunk classification popup -->
<div id="chunk-popup">
  <div class="chunk-popup-header">
    <span class="chunk-popup-title" id="chunk-popup-title">Classify directive</span>
    <button class="chunk-popup-close" id="chunk-popup-close" title="Close">&times;</button>
  </div>
  <div id="chunk-popup-form"></div>
</div>

<!-- Context menu for clicking an existing order_action annotation span -->
<div id="ann-context-menu">
  <button class="ann-ctx-btn" id="ann-ctx-relabel">&#9998; Re-label / remove</button>
  <button class="ann-ctx-btn" id="ann-ctx-classify">&#9776; Classify&hellip;</button>
</div>

<!-- Floating annotation label picker (shared across all docs) -->
<div id="label-picker">
  {picker_btns}
  <button class="pick-clear">&#10007; remove annotation</button>
</div>

<div class="top-bar">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:4px;">
    <h1 style="margin:0;">Segment viewer &mdash; {total_docs} documents</h1>
    <label for="annotator-name" style="font-size:15px;font-weight:700;color:#374151;white-space:nowrap;">Annotator:</label>
    <input id="annotator-name" type="text" placeholder="Your name">
    <button class="export-btn" id="export-btn">&#8659; Export annotations</button>
  </div>
  {strategy_toggle}
  <div class="legend leg-sp">{sp_legend}</div>
  <div class="legend leg-wp">{wp_legend}</div>
  <div class="tab-bar">
{tab_bar}
  </div>
</div>
{stats_html}
{panels_html}
<script>
// ── Strategy toggle ───────────────────────────────────────────────────────────
document.querySelectorAll('.strat-btn').forEach(function(btn) {{
  btn.addEventListener('click', function() {{
    document.querySelectorAll('.strat-btn').forEach(function(b) {{ b.classList.remove('active'); }});
    btn.classList.add('active');
    document.body.className = 'mode-' + btn.dataset.mode;
  }});
}});

// ── Tab switching ─────────────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(function(btn) {{
  btn.addEventListener('click', function() {{
    document.querySelectorAll('.tab-btn').forEach(function(b) {{ b.classList.remove('active'); }});
    document.querySelectorAll('.tab-panel').forEach(function(p) {{ p.classList.remove('active'); }});
    btn.classList.add('active');
    document.getElementById(btn.dataset.panel).classList.add('active');
  }});
}});

// ── Annotation engine ─────────────────────────────────────────────────────────
{doc_texts_js}

var STORAGE_KEY = 'seg-annotations-v2-{seed}';
var VIEWER_NUM = {viewer_num};
var LABEL_COLORS = {{
  'preamble':        {{bg:'#f3f4f6', border:'#6b7280'}},
  'ordering_phrase': {{bg:'#ccfbf1', border:'#0f766e'}},
  'order_action':    {{bg:'#fee2e2', border:'#b91c1c'}},
  'vesting_clause':  {{bg:'#ede9fe', border:'#6d28d9'}},
  'metadata':        {{bg:'#f3f4f6', border:'#6b7280'}},
  'boilerplate':     {{bg:'#fef3c7', border:'#92400e'}},
  'section':         {{bg:'#dbeafe', border:'#1d4ed8'}},
  'paragraph':       {{bg:'#d1fae5', border:'#065f46'}},
}};

function loadData() {{
  try {{ return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{{}}'); }} catch(e) {{ return {{}}; }}
}}
function saveData(d) {{ localStorage.setItem(STORAGE_KEY, JSON.stringify(d)); }}

function escH(s) {{
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}}

// Re-render an annotation area from stored annotations + raw text
function renderAnnotArea(docId) {{
  var el = document.querySelector('.annot-area[data-doc="' + docId + '"] .annot-text');
  if (!el) return;
  var text = DOC_TEXTS[docId] || '';
  var d = loadData()[docId] || {{}};
  var anns = (d.annotations || []).slice().sort(function(a,b){{return a.start-b.start;}});
  var out = '', pos = 0;
  for (var i = 0; i < anns.length; i++) {{
    var a = anns[i];
    if (a.end <= pos) continue;
    if (a.start > pos) out += escH(text.slice(pos, a.start));
    var c = LABEL_COLORS[a.label] || {{bg:'#fff', border:'#aaa'}};
    var clfBadge = '';
    if (a.label === 'order_action' && a.classification) {{
      var bt = clfBadgeText(a.classification);
      if (bt) clfBadge = '<span class="ann-clf-badge">' + escH(bt) + '</span>';
    }}
    var titleAttr = a.label === 'order_action'
      ? 'click to re-label/remove or classify'
      : 'click to relabel or remove';
    out += '<span class="ann-span" data-doc="' + docId + '" data-idx="' + i + '"'
         + ' title="' + titleAttr + '"'
         + ' style="background:' + c.bg + ';border-bottom:3px solid ' + c.border + '">'
         + escH(text.slice(a.start, a.end))
         + '<sup class="ann-tag" style="color:' + c.border + '">'
         + escH(a.label) + '</sup>'
         + clfBadge + '</span>';
    pos = a.end;
  }}
  if (pos < text.length) out += escH(text.slice(pos));
  el.innerHTML = out;
  // Attach click handlers to annotation spans
  el.querySelectorAll('.ann-span').forEach(function(span) {{
    span.addEventListener('click', function(e) {{
      var sel = window.getSelection();
      if (sel && !sel.isCollapsed) return; // ignore — user is mid-selection
      e.stopPropagation();
      var idx = parseInt(span.dataset.idx);
      var d = loadData();
      var ann = ((d[docId] || {{}}).annotations || [])[idx];
      if (ann && ann.label === 'order_action') {{
        showAnnContextMenu(e.clientX, e.clientY, docId, idx);
      }} else {{
        showPicker(e.clientX, e.clientY, docId, null, null, idx);
      }}
    }});
  }});
}}

// Get character offset of a boundary point within root, excluding text inside
// .ann-tag superscripts (label decorations, not document text). Works for both
// text-node boundaries (offset = char index) and element-node boundaries
// (offset = child index), which browsers produce on double-click or paragraph-end.
function getCharOffset(root, targetNode, targetOff) {{
  var r = document.createRange();
  r.setStart(root, 0);
  r.setEnd(targetNode, targetOff);
  var frag = r.cloneContents();
  frag.querySelectorAll('.ann-tag').forEach(function(el) {{ el.remove(); }});
  return frag.textContent.length;
}}

var _ps = null; // picker state: {{docId, start, end, annIdx}}

function showPicker(x, y, docId, start, end, annIdx) {{
  _ps = {{docId:docId, start:start, end:end, annIdx:annIdx}};
  var pk = document.getElementById('label-picker');
  pk.querySelector('.pick-clear').style.display = (annIdx !== null) ? 'block' : 'none';
  pk.style.display = 'block';
  // Position near cursor, clamped to viewport
  var left = x + 8, top = y + 8;
  if (left + 180 > window.innerWidth)  left = x - 188;
  if (top  + 280 > window.innerHeight) top  = y - 288;
  pk.style.left = Math.max(4, left) + 'px';
  pk.style.top  = Math.max(4, top)  + 'px';
}}
function hidePicker() {{
  document.getElementById('label-picker').style.display = 'none';
  _ps = null;
}}

// Show picker when text is selected inside an annotation area
document.querySelectorAll('.annot-area').forEach(function(area) {{
  area.addEventListener('mouseup', function(e) {{
    var sel = window.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount) return;
    var range = sel.getRangeAt(0);
    var textEl = area.querySelector('.annot-text');
    if (!textEl.contains(range.commonAncestorContainer)) return;
    var start = getCharOffset(textEl, range.startContainer, range.startOffset);
    var end   = getCharOffset(textEl, range.endContainer,   range.endOffset);
    if (start >= end) return;
    showPicker(e.clientX, e.clientY, area.dataset.doc, start, end, null);
  }});
}});

// Apply a label from the picker
document.querySelectorAll('.pick-btn').forEach(function(btn) {{
  btn.addEventListener('click', function(e) {{
    e.stopPropagation();
    if (!_ps) return;
    var ps = _ps, label = btn.dataset.label;
    var d = loadData();
    var doc = d[ps.docId] = d[ps.docId] || {{}};
    doc.annotations = doc.annotations || [];
    if (ps.annIdx !== null) {{
      // Relabel existing annotation
      doc.annotations[ps.annIdx].label = label;
    }} else {{
      // New annotation — remove any fully-overlapped ones first
      var s = ps.start, end = ps.end;
      doc.annotations = doc.annotations.filter(function(a) {{ return a.end <= s || a.start >= end; }});
      doc.annotations.push({{start:s, end:end, label:label}});
      doc.annotations.sort(function(a,b){{return a.start-b.start;}});
    }}
    saveData(d);
    renderAnnotArea(ps.docId);
    hidePicker();
    window.getSelection().removeAllRanges();
    // Auto-open classification popup for new order_action annotations.
    if (label === 'order_action' && ps.annIdx === null) {{
      var newIdx = (loadData()[ps.docId].annotations || []).length - 1;
      if (newIdx >= 0) {{
        setTimeout(function() {{ openChunkPopup(e.clientX, e.clientY, ps.docId, null, newIdx); }}, 50);
      }}
    }}
  }});
}});

// Remove an annotation
document.querySelector('.pick-clear').addEventListener('click', function(e) {{
  e.stopPropagation();
  if (!_ps || _ps.annIdx === null) return;
  var ps = _ps, idx = ps.annIdx;
  var d = loadData();
  var doc = d[ps.docId] = d[ps.docId] || {{}};
  doc.annotations = (doc.annotations || []).filter(function(_,i) {{ return i !== idx; }});
  saveData(d);
  renderAnnotArea(ps.docId);
  hidePicker();
}});

// Close picker on mousedown outside it.
document.addEventListener('mousedown', function(e) {{
  if (!document.getElementById('label-picker').contains(e.target)) hidePicker();
}});

// ── Feedback bar ──────────────────────────────────────────────────────────────
document.querySelectorAll('.fb-btn').forEach(function(btn) {{
  btn.addEventListener('click', function() {{
    var docId = btn.dataset.doc, val = btn.dataset.val, strat = btn.dataset.strategy;
    var bar = btn.closest('.feedback-bar');
    var ta  = bar.querySelector('.fb-comment');
    var d = loadData();
    var doc = d[docId] = d[docId] || {{}};
    var stratData = doc[strat] = doc[strat] || {{}};
    bar.querySelectorAll('.fb-btn').forEach(function(b) {{ b.classList.remove('active'); }});
    if (stratData.status === val) {{
      stratData.status = null; ta.style.display = 'none';
    }} else {{
      btn.classList.add('active');
      stratData.status = val;
      ta.style.display = 'block';
      ta.placeholder = (val === 'needs-revision') ? 'Describe what needs fixing…' : 'Optional notes…';
    }}
    saveData(d);
  }});
}});

document.querySelectorAll('.fb-comment').forEach(function(ta) {{
  ta.addEventListener('input', function() {{
    var strat = ta.dataset.strategy;
    var d = loadData();
    var doc = d[ta.dataset.doc] = d[ta.dataset.doc] || {{}};
    (doc[strat] = doc[strat] || {{}}).comment = ta.value;
    saveData(d);
  }});
}});

// ── Annotator name ────────────────────────────────────────────────────────────
var NAME_KEY = 'seg-annotator-name';
document.getElementById('annotator-name').value = localStorage.getItem(NAME_KEY) || '';
document.getElementById('annotator-name').addEventListener('input', function() {{
  localStorage.setItem(NAME_KEY, this.value);
}});

// ── Export ────────────────────────────────────────────────────────────────────
document.getElementById('export-btn').addEventListener('click', function() {{
  var out = loadData();
  var name = (localStorage.getItem(NAME_KEY) || '').trim();
  if (name) out = Object.assign({{annotator: name}}, out);
  var safeName = name ? name.replace(/\s+/g, '_').toLowerCase() : 'unknown';
  var today = new Date().toISOString().slice(0, 10);
  var filename = 'annotations-viewer' + VIEWER_NUM + '-' + safeName + '-' + today + '.json';
  var blob = new Blob([JSON.stringify(out, null, 2)], {{type:'application/json'}});
  var a = Object.assign(document.createElement('a'), {{
    href: URL.createObjectURL(blob), download: filename
  }});
  a.click(); URL.revokeObjectURL(a.href);
}});

// ── Classification helpers ────────────────────────────────────────────────────

// Conditionally show/hide sub-fields based on current form values.
function updateClfConditions(prefix) {{
  var form = document.querySelector('.clf-form[data-prefix="' + prefix + '"]');
  if (!form) return;
  var cat = form.querySelector('input[name="' + prefix + '-cat"]:checked');
  var scope = form.querySelector('input[name="' + prefix + '-scope"]:checked');
  var legalRow = form.querySelector('.clf-legal-row');
  var nsRow    = form.querySelector('.clf-ns-row');
  if (legalRow) legalRow.style.display = (cat && cat.value === 'policy') ? '' : 'none';
  if (nsRow)    nsRow.style.display    = (scope && scope.value === 'foreign') ? '' : 'none';
}}

// Save classification values from a form to localStorage.
function saveClfForm(prefix, docId, chunkN) {{
  var form = document.querySelector('.clf-form[data-prefix="' + prefix + '"]');
  if (!form) return;
  var getRadio = function(name) {{
    var el = form.querySelector('input[name="' + name + '"]:checked');
    return el ? el.value : null;
  }};
  var obj = {{
    category: getRadio(prefix + '-cat'),
    legal_effect: getRadio(prefix + '-legal'),
    scope: getRadio(prefix + '-scope'),
    national_security: getRadio(prefix + '-ns'),
    emergency: getRadio(prefix + '-emerg'),
  }};
  var d = loadData();
  d[docId] = d[docId] || {{}};
  if (chunkN === null && (_cp === null || _cp.annIdx === null)) {{
    // Sample-level classification (doc panel form)
    d[docId].classification = obj;
  }} else if (chunkN !== null) {{
    // W&P chunk classification
    d[docId].chunks = d[docId].chunks || {{}};
    d[docId].chunks[String(chunkN)] = obj;
    renderChunkBadge(docId, chunkN, obj);
  }} else {{
    // Left-side annotation classification (annIdx path)
    var annIdx = _cp.annIdx;
    d[docId].annotations = d[docId].annotations || [];
    if (d[docId].annotations[annIdx]) {{
      d[docId].annotations[annIdx].classification = obj;
      saveData(d);
      renderAnnotArea(docId);
      return;
    }}
  }}
  saveData(d);
}}

// Restore classification form from stored data.
function restoreClfForm(prefix, obj) {{
  if (!obj) return;
  var form = document.querySelector('.clf-form[data-prefix="' + prefix + '"]');
  if (!form) return;
  var setRadio = function(name, val) {{
    if (!val) return;
    var el = form.querySelector('input[name="' + name + '"][value="' + val + '"]');
    if (el) el.checked = true;
  }};
  setRadio(prefix + '-cat',   obj.category);
  setRadio(prefix + '-legal', obj.legal_effect);
  setRadio(prefix + '-scope', obj.scope);
  setRadio(prefix + '-ns',    obj.national_security);
  setRadio(prefix + '-emerg', obj.emergency);
  updateClfConditions(prefix);
}}

// Build a short badge text from a classification object.
function clfBadgeText(obj) {{
  if (!obj || !obj.category) return '';
  var labels = {{ ceremonial:'Cer', internal:'Intl', policy:'Pol', other:'Other' }};
  var legal  = {{ legal:'Legal', nonlegal:'Non-legal' }};
  var scope  = {{ domestic:'Dom', foreign:'For' }};
  var parts = [labels[obj.category] || obj.category];
  if (obj.category === 'policy' && obj.legal_effect) parts.push(legal[obj.legal_effect] || obj.legal_effect);
  if (obj.scope) parts.push(scope[obj.scope] || obj.scope);
  if (obj.national_security === 'yes') parts.push('NatSec');
  if (obj.emergency === 'yes') parts.push('Emerg');
  return parts.join(' · ');
}}

function renderChunkBadge(docId, chunkN, obj) {{
  var badge = document.getElementById('badge-' + docId + '-chunk-' + chunkN);
  if (!badge) return;
  badge.textContent = clfBadgeText(obj);
}}

// Wire up change/input events for a classification form.
function bindClfForm(form, docId, chunkN) {{
  form.querySelectorAll('.clf-cat-radio').forEach(function(r) {{
    r.addEventListener('change', function() {{
      updateClfConditions(form.dataset.prefix);
      saveClfForm(form.dataset.prefix, docId, chunkN);
    }});
  }});
  form.querySelectorAll('.clf-legal-radio, .clf-scope-radio').forEach(function(r) {{
    r.addEventListener('change', function() {{
      updateClfConditions(form.dataset.prefix);
      saveClfForm(form.dataset.prefix, docId, chunkN);
    }});
  }});
  form.querySelectorAll('.clf-ns-radio, .clf-emerg-radio').forEach(function(r) {{
    r.addEventListener('change', function() {{
      saveClfForm(form.dataset.prefix, docId, chunkN);
    }});
  }});
  // Help button opens category descriptions modal
  form.querySelectorAll('.clf-help-btn').forEach(function(btn) {{
    btn.addEventListener('click', function(e) {{
      e.stopPropagation();
      document.getElementById('cat-modal-overlay').style.display = 'block';
    }});
  }});
}}

// ── Wire up sample-level classification forms on page load ────────────────────
document.querySelectorAll('.clf-panel').forEach(function(panel) {{
  var docId = panel.dataset.doc;
  var form  = panel.querySelector('.clf-form');
  if (!form) return;
  bindClfForm(form, docId, null);
  var d = loadData();
  restoreClfForm(form.dataset.prefix, (d[docId] || {{}}).classification);
}});

// ── Category descriptions modal ───────────────────────────────────────────────
document.getElementById('cat-modal-close').addEventListener('click', function() {{
  document.getElementById('cat-modal-overlay').style.display = 'none';
}});
document.getElementById('cat-modal-overlay').addEventListener('click', function(e) {{
  if (e.target === this) this.style.display = 'none';
}});

// ── Left-side annotation context menu (order_action spans) ───────────────────
var _actx = null; // {{docId, annIdx, x, y}}

function showAnnContextMenu(x, y, docId, annIdx) {{
  _actx = {{docId: docId, annIdx: annIdx, x: x, y: y}};
  var menu = document.getElementById('ann-context-menu');
  menu.style.display = 'block';
  var left = x + 8, top = y + 8;
  if (left + 160 > window.innerWidth)  left = x - 168;
  if (top  + 80  > window.innerHeight) top  = y - 88;
  menu.style.left = Math.max(4, left) + 'px';
  menu.style.top  = Math.max(4, top)  + 'px';
}}
function hideAnnContextMenu() {{
  document.getElementById('ann-context-menu').style.display = 'none';
  _actx = null;
}}

document.getElementById('ann-ctx-relabel').addEventListener('click', function(e) {{
  e.stopPropagation();
  if (!_actx) return;
  var ctx = _actx;
  hideAnnContextMenu();
  showPicker(ctx.x, ctx.y, ctx.docId, null, null, ctx.annIdx);
}});

document.getElementById('ann-ctx-classify').addEventListener('click', function(e) {{
  e.stopPropagation();
  if (!_actx) return;
  var ctx = _actx;
  hideAnnContextMenu();
  openChunkPopup(ctx.x, ctx.y, ctx.docId, null, ctx.annIdx);
}});

document.addEventListener('mousedown', function(e) {{
  var menu = document.getElementById('ann-context-menu');
  if (menu.style.display !== 'none' && !menu.contains(e.target)) hideAnnContextMenu();
}});

// ── Chunk classification popup ────────────────────────────────────────────────
var _cp = null; // {{docId, chunkN, annIdx}} — annIdx set when opened from left-side annotation

// Inlined classification form template (matches render_classification_form output structure)
var CLF_CAT_OPTS = [
  ['ceremonial','Ceremonial/Expressive'],
  ['internal',  'Internal Management'],
  ['policy',    'Policy Setting'],
  ['other',     'Other'],
];
var CLF_LEGAL_OPTS = [
  ['legal',    'Likely legal effect'],
  ['nonlegal', 'Non-legally binding'],
];
var CLF_SCOPE_OPTS = [
  ['domestic', 'Domestic'],
  ['foreign',  'Foreign'],
];

function buildClfFormHTML(prefix) {{
  function radios(name, opts, cls) {{
    return opts.map(function(o) {{
      return '<label class="clf-radio-label"><input type="radio" name="' + name + '" value="' + o[0] + '" class="' + cls + '" data-prefix="' + prefix + '"> ' + o[1] + '</label>';
    }}).join('');
  }}
  return '<div class="clf-form" data-prefix="' + prefix + '">'
    + '<div class="clf-row"><span class="clf-label">Category</span>'
    + '<button type="button" class="clf-help-btn" title="Category descriptions">?</button>'
    + '<div class="clf-radios">' + radios(prefix+'-cat', CLF_CAT_OPTS, 'clf-cat-radio') + '</div></div>'
    + '<div class="clf-row clf-legal-row" style="display:none"><span class="clf-label">Legal effect</span>'
    + '<div class="clf-radios">' + radios(prefix+'-legal', CLF_LEGAL_OPTS, 'clf-legal-radio') + '</div></div>'
    + '<div class="clf-row"><span class="clf-label">Scope</span>'
    + '<div class="clf-radios">' + radios(prefix+'-scope', CLF_SCOPE_OPTS, 'clf-scope-radio') + '</div></div>'
    + '<div class="clf-row clf-ns-row" style="display:none"><span class="clf-label">National security?</span>'
    + '<div class="clf-radios">'
    + '<label class="clf-radio-label"><input type="radio" name="' + prefix + '-ns" value="yes" class="clf-ns-radio" data-prefix="' + prefix + '"> Yes</label>'
    + '<label class="clf-radio-label"><input type="radio" name="' + prefix + '-ns" value="no" class="clf-ns-radio" data-prefix="' + prefix + '"> No</label>'
    + '</div></div>'
    + '<div class="clf-row"><span class="clf-label">Emergency?</span>'
    + '<div class="clf-radios">'
    + '<label class="clf-radio-label"><input type="radio" name="' + prefix + '-emerg" value="yes" class="clf-emerg-radio" data-prefix="' + prefix + '"> Yes</label>'
    + '<label class="clf-radio-label"><input type="radio" name="' + prefix + '-emerg" value="no" class="clf-emerg-radio" data-prefix="' + prefix + '"> No</label>'
    + '</div></div>'
    + '</div>';
}}

function openChunkPopup(x, y, docId, chunkN, annIdx) {{
  _cp = {{docId: docId, chunkN: chunkN, annIdx: (annIdx !== undefined ? annIdx : null)}};
  var isAnn = (_cp.annIdx !== null);
  var prefix = isAnn ? (docId + '-ann-' + annIdx) : (docId + '-chunk-' + chunkN);
  var titleEl = document.getElementById('chunk-popup-title');
  if (isAnn) {{
    titleEl.textContent = 'Classify annotation (' + docId + ')';
  }} else {{
    titleEl.textContent = 'Classify directive #' + chunkN + ' (' + docId + ')';
  }}
  document.getElementById('chunk-popup-form').innerHTML = buildClfFormHTML(prefix);
  // Restore saved values
  var d = loadData();
  var saved = isAnn
    ? (((d[docId] || {{}}).annotations || [])[annIdx] || {{}}).classification
    : ((d[docId] || {{}}).chunks || {{}})[String(chunkN)];
  restoreClfForm(prefix, saved);
  // Wire up events
  var form = document.querySelector('#chunk-popup-form .clf-form');
  bindClfForm(form, docId, chunkN);
  // Position
  var pop = document.getElementById('chunk-popup');
  pop.style.display = 'block';
  var left = x + 10, top = y + 10;
  if (left + 440 > window.innerWidth)  left = x - 448;
  if (top  + 320 > window.innerHeight) top  = y - 328;
  pop.style.left = Math.max(4, left) + 'px';
  pop.style.top  = Math.max(4, top)  + 'px';
}}

function closeChunkPopup() {{
  document.getElementById('chunk-popup').style.display = 'none';
  _cp = null;
}}

document.getElementById('chunk-popup-close').addEventListener('click', closeChunkPopup);

document.addEventListener('mousedown', function(e) {{
  var pop = document.getElementById('chunk-popup');
  if (pop.style.display !== 'none' && !pop.contains(e.target)) closeChunkPopup();
}});

// Clicking a W&P directive chunk opens the classification popup.
document.querySelectorAll('.seg-chunk').forEach(function(seg) {{
  seg.addEventListener('click', function(e) {{
    e.stopPropagation();
    var docId  = seg.dataset.doc;
    var chunkN = parseInt(seg.dataset.chunkn);
    openChunkPopup(e.clientX, e.clientY, docId, chunkN);
  }});
}});

// ── Restore saved state on page load ─────────────────────────────────────────
(function() {{
  var d = loadData();
  // Feedback bars
  document.querySelectorAll('.feedback-bar').forEach(function(bar) {{
    var firstBtn = bar.querySelector('.fb-btn');
    var docId = firstBtn.dataset.doc, strat = firstBtn.dataset.strategy;
    var saved = ((d[docId] || {{}})[strat]) || {{}};
    if (saved.status) {{
      var btn = bar.querySelector('.fb-btn[data-val="' + saved.status + '"]');
      if (btn) btn.classList.add('active');
    }}
    var ta = bar.querySelector('.fb-comment');
    if (saved.comment) ta.value = saved.comment;
    if (saved.status) {{
      ta.style.display = 'block';
      ta.placeholder = (saved.status === 'needs-revision') ? 'Describe what needs fixing…' : 'Optional notes…';
    }}
  }});
  // Annotation areas
  document.querySelectorAll('.annot-area').forEach(function(area) {{
    renderAnnotArea(area.dataset.doc);
  }});
  // Chunk badges
  for (var docId in d) {{
    if (!d[docId].chunks) continue;
    for (var chunkN in d[docId].chunks) {{
      renderChunkBadge(docId, parseInt(chunkN), d[docId].chunks[chunkN]);
    }}
  }}
}})();
</script>
</body>
</html>"""


def load_pilot(per_type: int = 5, seed: int = 99) -> list[tuple[str, str, str, list[dict]]]:
    """Return per_type docs per doc type sampled round-robin across administrations."""
    with open(DATA_FILE) as f:
        all_rows = list(csv.DictReader(f))

    rng = random.Random(seed)
    result: list[tuple[str, str, str, list[dict]]] = []

    for doc_type_key, prefix, tab_label in DOC_TYPES:
        pool = [r for r in all_rows if r["doc_type"] == doc_type_key and int(r[""]) not in HOLDOUT_IDS]
        by_prez: dict[str, list[dict]] = {}
        for r in pool:
            by_prez.setdefault(r["president"], []).append(r)
        for bucket in by_prez.values():
            rng.shuffle(bucket)
        presidents = sorted(by_prez.keys())
        iters = {p: iter(by_prez[p]) for p in presidents}

        rows: list[dict] = []
        while len(rows) < per_type:
            made_progress = False
            for p in presidents:
                if len(rows) < per_type:
                    row = next(iters[p], None)
                    if row is not None:
                        rows.append(row)
                        made_progress = True
            if not made_progress:
                break

        if rows:
            result.append((doc_type_key, prefix, tab_label, rows[:per_type]))

    return result


def load_balanced_dual(per_type: int = 25, seed: int = 42) -> tuple[
    list[tuple[str, str, str, list[dict]]],
    list[tuple[str, str, str, list[dict]]],
]:
    """Return two disjoint row_by_type sets, each with per_type docs per doc type.

    Within each doc type, a round-robin across presidents takes one doc per president
    for viewer A and one for viewer B per cycle, ensuring both viewers have coverage
    from every administration (subject to each president having enough documents).
    """
    with open(DATA_FILE) as f:
        all_rows = list(csv.DictReader(f))

    rng = random.Random(seed)

    set_a: list[tuple[str, str, str, list[dict]]] = []
    set_b: list[tuple[str, str, str, list[dict]]] = []

    for doc_type_key, prefix, tab_label in DOC_TYPES:
        pool = [r for r in all_rows if r["doc_type"] == doc_type_key and int(r[""]) not in HOLDOUT_IDS]
        by_prez: dict[str, list[dict]] = {}
        for r in pool:
            by_prez.setdefault(r["president"], []).append(r)
        for bucket in by_prez.values():
            rng.shuffle(bucket)
        presidents = sorted(by_prez.keys())
        # Iterators: each president contributes up to 2 docs per cycle (1→A, 1→B).
        iters = {p: iter(by_prez[p]) for p in presidents}

        rows_a: list[dict] = []
        rows_b: list[dict] = []
        while len(rows_a) < per_type or len(rows_b) < per_type:
            made_progress = False
            for p in presidents:
                if len(rows_a) < per_type:
                    row = next(iters[p], None)
                    if row is not None:
                        rows_a.append(row)
                        made_progress = True
                if len(rows_b) < per_type:
                    row = next(iters[p], None)
                    if row is not None:
                        rows_b.append(row)
                        made_progress = True
            if not made_progress:
                break  # all presidents exhausted

        rows_a = rows_a[:per_type]
        rows_b = rows_b[:per_type]
        if rows_a:
            set_a.append((doc_type_key, prefix, tab_label, rows_a))
        if rows_b:
            set_b.append((doc_type_key, prefix, tab_label, rows_b))

    return set_a, set_b


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=5, help="Docs per document type (default 5)")
    parser.add_argument("--n-memo", type=int, default=None, dest="n_memo",
                        help="Override doc count for memoranda (default matches --n)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for sampling (default 42)")
    parser.add_argument("--out", type=str, default=None, help="Output HTML filename (default segments_viewer.html)")
    parser.add_argument("--id", type=int, default=None, dest="row_id",
                        help="Load a single row by CSV index instead of sampling")
    parser.add_argument("--dual", action="store_true",
                        help="Build two disjoint 100-doc classification viewers (25 per type)")
    parser.add_argument("--pilot", action="store_true",
                        help="Build pilot_20.html: 5 docs per type sampled round-robin across admins")
    args = parser.parse_args()

    if args.pilot:
        rows_by_type = load_pilot(per_type=5, seed=args.seed)
        out_file = OUT_FILE.with_name("pilot_20.html")
        html_out = build_html(rows_by_type, seed=args.seed, viewer_num=0)
        out_file.write_text(html_out)
        doc_id_map: dict[str, int] = {}
        for _, prefix, _, rows in rows_by_type:
            for j, row in enumerate(rows, start=1):
                doc_id_map[f"{prefix}{j}"] = int(row[""])
        map_file = OUT_FILE.with_name("doc_id_map_pilot_20.json")
        map_file.write_text(json.dumps(doc_id_map, indent=2))
        total = sum(len(rows) for _, _, _, rows in rows_by_type)
        print(f"Wrote {out_file}  ({total} docs, {len(rows_by_type)} tabs)")
        print(f"Wrote {map_file}")
        return

    if args.dual:
        set_a, set_b = load_balanced_dual(per_type=25, seed=args.seed)
        dual_names = ["entries_100", "classification_viewer_2"]
        for idx, (rows_by_type, viewer_seed, name) in enumerate(
            zip([set_a, set_b], [args.seed, args.seed + 1000], dual_names), start=1
        ):
            out_file = OUT_FILE.with_name(f"{name}.html")
            html_out = build_html(rows_by_type, seed=viewer_seed, viewer_num=idx)
            out_file.write_text(html_out)
            doc_id_map: dict[str, int] = {}
            for _, prefix, _, rows in rows_by_type:
                for j, row in enumerate(rows, start=1):
                    doc_id_map[f"{prefix}{j}"] = int(row[""])
            map_file = OUT_FILE.with_name(f"doc_id_map_{name}.json")
            map_file.write_text(json.dumps(doc_id_map, indent=2))
            total = sum(len(rows) for _, _, _, rows in rows_by_type)
            print(f"Wrote {out_file}  ({total} docs, {len(rows_by_type)} tabs)")
            print(f"Wrote {map_file}")
        return

    if args.row_id is not None:
        with open(DATA_FILE) as f:
            all_rows = list(csv.DictReader(f))
        row = all_rows[args.row_id]
        doc_type = row["doc_type"]
        prefix = next((p for k, p, _ in DOC_TYPES if k == doc_type), "D")
        rows_by_type = [(doc_type, prefix, doc_type, [row])]
    else:
        rows_by_type = []
        for doc_type_key, prefix, tab_label in DOC_TYPES:
            n = args.n_memo if (doc_type_key == "memorandum" and args.n_memo is not None) else args.n
            rows = load_rows(doc_type_key, n, seed=args.seed)
            if rows:
                rows_by_type.append((doc_type_key, prefix, tab_label, rows))

    # Build doc_id → CSV row-index map for annotation parsing
    doc_id_map: dict[str, int] = {}
    for _, prefix, _, rows in rows_by_type:
        for j, row in enumerate(rows, start=1):
            doc_id_map[f"{prefix}{j}"] = int(row[""])

    out_file = OUT_FILE.with_name(args.out) if args.out else OUT_FILE
    html_out = build_html(rows_by_type, seed=args.seed if hasattr(args, "seed") else 42)
    out_file.write_text(html_out)
    map_file = out_file.with_name(f"doc_id_map_{out_file.stem}.json")
    map_file.write_text(json.dumps(doc_id_map, indent=2))
    total = sum(len(rows) for _, _, _, rows in rows_by_type)
    print(f"Wrote {out_file}  ({total} docs, {len(rows_by_type)} tabs)")
    print(f"Wrote {map_file}")


if __name__ == "__main__":
    main()
