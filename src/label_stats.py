"""
Compute aggregate segmentation label stats across the full dataset.

For each doc type and segmentation strategy, reports the distribution
(min, median, mean, max, std dev) of per-document label counts.

Usage (from project root):
  python src/label_stats.py                        # all doc types, both strategies
  python src/label_stats.py --type memorandum
  python src/label_stats.py --strategy sp
  python src/label_stats.py --csv data/4_28_2026_build_holdout.csv
  python src/label_stats.py --out data/sample_segmentation/label_stats.html
"""

import argparse
import csv
import html
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from segmenter import segment, segment_ordering

ROOT = Path(__file__).parent.parent
DEFAULT_CSV = ROOT / "data" / "4_28_2026_build_dev.csv"

DOC_TYPES = ["executive_order", "memorandum", "letter", "proclamation"]
DOC_TYPE_LABELS = {
    "executive_order": "Executive Orders",
    "memorandum": "Memoranda",
    "letter": "Letters",
    "proclamation": "Proclamations",
}

SP_LABELS = ["vesting_clause", "paragraph", "section", "boilerplate", "metadata"]
WP_LABELS = ["vesting_clause", "preamble", "order_action", "boilerplate", "metadata"]

LABEL_COLORS = {
    "vesting_clause": "#6d28d9",
    "paragraph":      "#065f46",
    "section":        "#1d4ed8",
    "boilerplate":    "#92400e",
    "metadata":       "#6b7280",
    "preamble":       "#6b7280",
    "order_action":   "#b91c1c",
}


def compute_stats(counts: list[int]) -> dict:
    n = len(counts)
    if n == 0:
        return {"n": 0, "min": 0, "median": 0.0, "mean": 0.0, "max": 0, "std": 0.0,
                "raw": []}
    return {
        "n": n,
        "min": min(counts),
        "median": round(statistics.median(counts), 2),
        "mean": round(statistics.mean(counts), 2),
        "max": max(counts),
        "std": round(statistics.stdev(counts) if n > 1 else 0.0, 2),
        "raw": counts,
    }


def collect_counts(rows: list[dict], labels: list[str], strategy: str) -> dict[str, list[int]]:
    counts: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        if strategy == "sp":
            segs = segment(row["doc_text"], row["doc_type"], split_subsections=False)
        else:
            segs = segment_ordering(row["doc_text"], row["doc_type"])
        doc_counts = Counter(s.seg_type for s in segs)
        for label in labels:
            counts[label].append(doc_counts.get(label, 0))
    return counts


# ── Terminal output ────────────────────────────────────────────────────────────

def run_terminal(csv_path: Path, doc_types: list[str], strategies: list[str]) -> None:
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))

    print(f"Dataset: {csv_path.name}  ({len(rows)} total rows)\n")

    for doc_type in doc_types:
        pool = [r for r in rows if r["doc_type"] == doc_type]
        if not pool:
            print(f"[{doc_type}] — no rows found\n")
            continue

        print(f"{'=' * 60}")
        print(f"  {doc_type.upper()}  (n={len(pool)} docs)")
        print(f"{'=' * 60}")

        if "sp" in strategies:
            sp_counts = collect_counts(pool, SP_LABELS, "sp")
            print("\n  Section / Paragraph strategy")
            _print_table(sp_counts, SP_LABELS)

        if "wp" in strategies:
            wp_counts = collect_counts(pool, WP_LABELS, "wp")
            print("\n  Woolley & Peters strategy")
            _print_table(wp_counts, WP_LABELS)

        print()


def _print_table(counts_by_label: dict, labels: list[str]) -> None:
    header = f"  {'label':<18} {'n':>6} {'min':>6} {'median':>8} {'mean':>8} {'max':>6} {'std':>8}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for label in labels:
        s = compute_stats(counts_by_label[label])
        print(
            f"  {label:<18} {s['n']:>6} {s['min']:>6} {s['median']:>8} "
            f"{s['mean']:>8} {s['max']:>6} {s['std']:>8}"
        )


# ── HTML output ────────────────────────────────────────────────────────────────

def _heat_bg(value: float, col_max: float, hue: str = "red") -> str:
    """Return an inline background-color style scaled from white to a tint."""
    if col_max == 0:
        return "background:#fff"
    t = min(value / col_max, 1.0)
    palettes = {
        "red":    (254, 226, 226),   # red-100
        "amber":  (254, 243, 199),   # amber-100
        "purple": (237, 233, 254),   # violet-100
        "blue":   (219, 234, 254),   # blue-100
    }
    r0, g0, b0 = palettes.get(hue, palettes["red"])
    r = int(255 - t * (255 - r0))
    g = int(255 - t * (255 - g0))
    b = int(255 - t * (255 - b0))
    return f"background:rgb({r},{g},{b})"


def _html_stats_table(counts_by_label: dict, labels: list[str], strategy: str) -> str:
    stats = {lbl: compute_stats(counts_by_label[lbl]) for lbl in labels}

    # Column maxes for heat scaling
    col_maxes = {
        col: max((stats[lbl][col] for lbl in labels), default=0)
        for col in ("max", "std", "mean", "median")
    }
    hues = {"max": "red", "std": "amber", "mean": "blue", "median": "purple"}

    rows_html = []
    for lbl in labels:
        s = stats[lbl]
        color = LABEL_COLORS.get(lbl, "#6b7280")
        cells = [f'<td style="color:{color};font-weight:700;text-align:left">{html.escape(lbl)}</td>']
        cells.append(f'<td>{s["n"]:,}</td>')
        cells.append(f'<td>{s["min"]}</td>')

        for col in ("median", "mean", "max", "std"):
            bg = _heat_bg(float(s[col]), float(col_maxes[col]), hues[col])
            cells.append(f'<td style="{bg}">{s[col]}</td>')

        # Sparkline data (distribution of counts, clamped to p99 for display)
        p99 = sorted(s["raw"])[int(len(s["raw"]) * 0.99)] if s["raw"] else 0
        spark_data = json.dumps([min(v, p99 + 1) for v in s["raw"]])
        spark_max = max(p99 + 1, 1)
        cells.append(
            f'<td class="spark-cell">'
            f'<canvas class="sparkline" width="120" height="28" '
            f'data-counts=\'{spark_data}\' data-max="{spark_max}"></canvas>'
            f'</td>'
        )

        rows_html.append(f'<tr>{"".join(cells)}</tr>')

    label_col = "Section / Paragraph labels" if strategy == "sp" else "Woolley &amp; Peters labels"
    return f"""<table class="stats-tbl">
  <thead><tr>
    <th style="text-align:left">{label_col}</th>
    <th>n docs</th><th>min</th>
    <th class="col-median">median</th>
    <th class="col-mean">mean</th>
    <th class="col-max">max</th>
    <th class="col-std">std dev</th>
    <th>distribution</th>
  </tr></thead>
  <tbody>{''.join(rows_html)}</tbody>
</table>"""


def build_html_report(
    csv_path: Path,
    doc_types: list[str],
    strategies: list[str],
) -> str:
    with open(csv_path) as f:
        all_rows = list(csv.DictReader(f))

    total_rows = len(all_rows)

    # Collect all data up front
    data: dict = {}  # doc_type -> strategy -> label -> stats
    pool_sizes: dict[str, int] = {}
    for doc_type in doc_types:
        pool = [r for r in all_rows if r["doc_type"] == doc_type]
        pool_sizes[doc_type] = len(pool)
        data[doc_type] = {}
        if "sp" in strategies:
            data[doc_type]["sp"] = collect_counts(pool, SP_LABELS, "sp")
        if "wp" in strategies:
            data[doc_type]["wp"] = collect_counts(pool, WP_LABELS, "wp")

    # Build tab buttons and panels
    tab_buttons = []
    tab_panels = []
    for i, doc_type in enumerate(doc_types):
        label = DOC_TYPE_LABELS.get(doc_type, doc_type)
        n = pool_sizes[doc_type]
        active_btn   = " active" if i == 0 else ""
        active_panel = " active" if i == 0 else ""
        tab_buttons.append(
            f'<button class="tab-btn{active_btn}" data-panel="panel-{doc_type}">'
            f'{html.escape(label)} <span class="tab-count">({n:,})</span></button>'
        )

        strat_sections = []
        if "sp" in strategies:
            tbl = _html_stats_table(data[doc_type]["sp"], SP_LABELS, "sp")
            strat_sections.append(
                f'<div class="strat-view view-sp"><h3>Section / Paragraph</h3>{tbl}</div>'
            )
        if "wp" in strategies:
            tbl = _html_stats_table(data[doc_type]["wp"], WP_LABELS, "wp")
            strat_sections.append(
                f'<div class="strat-view view-wp"><h3>Woolley &amp; Peters</h3>{tbl}</div>'
            )

        tab_panels.append(
            f'<div class="tab-panel{active_panel}" id="panel-{doc_type}">'
            + "\n".join(strat_sections)
            + "</div>"
        )

    tab_bar = "\n".join(tab_buttons)
    panels_html = "\n".join(tab_panels)
    dataset_name = html.escape(csv_path.name)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Label stats — {dataset_name}</title>
<style>
  body {{ font-family: system-ui, sans-serif; font-size: 13px; margin: 0; padding: 16px; background: #f9fafb; color: #111; }}
  h1 {{ font-size: 1.1rem; margin: 0 0 4px; }}
  .subtitle {{ font-size: 12px; color: #6b7280; margin-bottom: 12px; }}
  /* Strategy toggle */
  .strategy-toggle {{ display: flex; align-items: center; gap: 6px; margin-bottom: 10px; }}
  .strategy-label {{ font-size: 12px; font-weight: 600; color: #6b7280; }}
  .strat-btn {{
    padding: 4px 12px; font-size: 12px; font-weight: 600; cursor: pointer;
    background: #e5e7eb; border: 1px solid #d1d5db; border-radius: 4px; color: #374151;
  }}
  .strat-btn.active {{ background: #1d4ed8; color: white; border-color: #1d4ed8; }}
  /* Tabs */
  .tab-bar {{ display: flex; gap: 4px; border-bottom: 2px solid #e5e7eb; margin-bottom: 14px; }}
  .tab-btn {{
    padding: 6px 14px; font-size: 13px; font-weight: 600; cursor: pointer;
    background: none; border: none; border-bottom: 3px solid transparent;
    margin-bottom: -2px; color: #6b7280;
  }}
  .tab-btn:hover {{ color: #1d4ed8; }}
  .tab-btn.active {{ color: #1d4ed8; border-bottom-color: #1d4ed8; }}
  .tab-count {{ font-weight: 400; color: #9ca3af; }}
  .tab-panel {{ display: none; }}
  .tab-panel.active {{ display: block; }}
  /* Tables */
  h3 {{ font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: #9ca3af; margin: 0 0 8px; }}
  .stats-tbl {{ border-collapse: collapse; font-size: 12px; margin-bottom: 20px; }}
  .stats-tbl th, .stats-tbl td {{ padding: 5px 16px 5px 0; border-bottom: 1px solid #f3f4f6; white-space: nowrap; }}
  .stats-tbl th {{ color: #9ca3af; font-weight: 600; border-bottom: 2px solid #e5e7eb; padding-bottom: 6px; }}
  .stats-tbl td {{ text-align: right; }}
  .stats-tbl tr:hover td {{ background: #f9fafb !important; }}
  .col-median {{ color: #6d28d9 !important; }}
  .col-mean   {{ color: #1d4ed8 !important; }}
  .col-max    {{ color: #b91c1c !important; }}
  .col-std    {{ color: #92400e !important; }}
  .spark-cell {{ padding-right: 0; }}
  /* Strategy visibility */
  body.mode-sp .view-wp {{ display: none; }}
  body.mode-wp .view-sp {{ display: none; }}
</style>
</head>
<body class="mode-sp">
<h1>Label stats &mdash; {dataset_name}</h1>
<div class="subtitle">{total_rows:,} total documents &nbsp;|&nbsp; counts are per-document</div>

<div class="strategy-toggle">
  <span class="strategy-label">Strategy:</span>
  <button class="strat-btn active" data-mode="sp">Section / Paragraph</button>
  <button class="strat-btn" data-mode="wp">Woolley &amp; Peters</button>
</div>

<div class="tab-bar">
{tab_bar}
</div>
{panels_html}

<script>
// ── Strategy toggle ────────────────────────────────────────────────────────────
document.querySelectorAll('.strat-btn').forEach(function(btn) {{
  btn.addEventListener('click', function() {{
    document.querySelectorAll('.strat-btn').forEach(function(b) {{ b.classList.remove('active'); }});
    btn.classList.add('active');
    document.body.className = 'mode-' + btn.dataset.mode;
    drawAllSparklines();
  }});
}});

// ── Tab switching ──────────────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(function(btn) {{
  btn.addEventListener('click', function() {{
    document.querySelectorAll('.tab-btn').forEach(function(b) {{ b.classList.remove('active'); }});
    document.querySelectorAll('.tab-panel').forEach(function(p) {{ p.classList.remove('active'); }});
    btn.classList.add('active');
    document.getElementById(btn.dataset.panel).classList.add('active');
    drawAllSparklines();
  }});
}});

// ── Sparklines ─────────────────────────────────────────────────────────────────
function drawSparkline(canvas) {{
  var counts = JSON.parse(canvas.dataset.counts);
  var maxVal = parseFloat(canvas.dataset.max) || 1;
  var ctx = canvas.getContext('2d');
  var W = canvas.width, H = canvas.height;
  ctx.clearRect(0, 0, W, H);

  // Build a histogram with ~30 buckets
  var nBins = 30;
  var bins = new Array(nBins).fill(0);
  counts.forEach(function(v) {{
    var b = Math.min(Math.floor(v / maxVal * nBins), nBins - 1);
    bins[b]++;
  }});
  var binMax = Math.max.apply(null, bins) || 1;
  var barW = W / nBins;

  ctx.fillStyle = '#bfdbfe';
  bins.forEach(function(cnt, i) {{
    var h = (cnt / binMax) * (H - 2);
    ctx.fillRect(i * barW + 0.5, H - h, barW - 1, h);
  }});
}}

function drawAllSparklines() {{
  document.querySelectorAll('.tab-panel.active .sparkline').forEach(drawSparkline);
  document.querySelectorAll('.tab-panel.active .strat-view:not([style*="none"]) .sparkline').forEach(drawSparkline);
}}

// Draw on initial load
document.querySelectorAll('.tab-panel.active .sparkline').forEach(drawSparkline);
</script>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=str, default=None,
                        help=f"Input CSV path (default: {DEFAULT_CSV.name})")
    parser.add_argument("--type", type=str, default=None, dest="doc_type",
                        help="Restrict to one doc type (e.g. memorandum)")
    parser.add_argument("--strategy", choices=["sp", "wp", "both"], default="both",
                        help="Which segmentation strategy to show (default: both)")
    parser.add_argument("--out", type=str, default=None,
                        help="Write HTML report to this path instead of printing to terminal")
    args = parser.parse_args()

    csv_path = Path(args.csv) if args.csv else DEFAULT_CSV
    doc_types = [args.doc_type] if args.doc_type else DOC_TYPES
    strategies = ["sp", "wp"] if args.strategy == "both" else [args.strategy]

    if args.out:
        out_path = Path(args.out)
        html_out = build_html_report(csv_path, doc_types, strategies)
        out_path.write_text(html_out)
        print(f"Wrote {out_path}")
    else:
        run_terminal(csv_path, doc_types, strategies)


if __name__ == "__main__":
    main()
