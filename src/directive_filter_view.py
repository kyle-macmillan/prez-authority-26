"""Interactive filter view for the 100-directive sample.

Produces data/directive_filter_review.html — a self-contained HTML document
with faceted filtering on five dimensions:
  - Vesting clause type (specific / generic / none, rule-based)
  - Binding legal effect (union across annotators)
  - Scope: foreign / domestic (union, may overlap for split directives)
  - National security (union)
  - Emergency (union)

Within each filter group: OR.  Across filter groups: AND.
Labels resolved by union: a directive matches a label if ANY coder assigned it.

Run from project root:
  python3 src/directive_filter_view.py
"""

import json
import re
from collections import Counter
from html import escape
from pathlib import Path

from vesting_authority_stats import (
    classify_vesting_clauses,
    extract_vesting_clauses,
    load_corpus,
    DEFAULT_DEV,
    DEFAULT_HOLDOUT,
)

ROOT = Path(__file__).parent.parent
DOC_ID_MAP = ROOT / "data" / "Annotations" / "Sandbox 1" / "doc_id_map_viewer.json"
RESULT_DIR = ROOT / "data" / "Annotations" / "Sandbox 1" / "results"
HTML_OUT = ROOT / "data" / "directive_filter_review.html"

_PREFIX_ORDER = {"EO": 0, "L": 1, "M": 2, "P": 3}

_BADGE_COLORS = {
    "generic":           ("#0550ae", "#fff"),
    "specific":          ("#8250df", "#fff"),
    "no_vesting_clause": ("#57606a", "#fff"),
    "binding":           ("#1a7f37", "#fff"),
    "not_binding":       ("#57606a", "#fff"),
    "foreign":           ("#bf3989", "#fff"),
    "domestic":          ("#2da44e", "#fff"),
    "natsec_yes":        ("#953800", "#fff"),
    "natsec_no":         ("#57606a", "#fff"),
    "emergency_yes":     ("#e16812", "#fff"),
    "emergency_no":      ("#57606a", "#fff"),
    "executive_order":   ("#0550ae", "#fff"),
    "memorandum":        ("#bf3989", "#fff"),
    "proclamation":      ("#2da44e", "#fff"),
    "letter":            ("#6e40c9", "#fff"),
}

_DT_ABBR = {
    "executive_order": "EO",
    "memorandum": "Memo",
    "proclamation": "Proc.",
    "letter": "Ltr.",
}


def _badge(text: str, key: str = "") -> str:
    bg, fg = _BADGE_COLORS.get(key or text, ("#888", "#fff"))
    return (f'<span class="badge" style="background:{bg};color:{fg}">'
            f'{escape(text.replace("_", " "))}</span>')


def _prefix(label: str) -> str:
    return "".join(ch for ch in label if not ch.isdigit())


def _vesting(doc_text: str, doc_type: str):
    """Return (category, gen_matches, spec_matches, clauses)."""
    clauses = extract_vesting_clauses(doc_text, doc_type)
    if not clauses:
        return "no_vesting_clause", [], [], []
    qualifies, generic, specific = classify_vesting_clauses(clauses)
    cat = "generic" if qualifies else "specific"
    return cat, generic, specific, clauses


def _load_annotators() -> list[tuple[str, dict]]:
    result = []
    for f in sorted(RESULT_DIR.glob("*.json")):
        d = json.loads(f.read_text())
        result.append((d.get("annotator", f.stem), d))
    return result


# ---------------------------------------------------------------------------
# Build records
# ---------------------------------------------------------------------------

def build_records() -> list[dict]:
    id_map: dict[str, int] = json.loads(DOC_ID_MAP.read_text())
    corpus: dict[int, dict] = {int(r[""]): r for r in load_corpus([DEFAULT_DEV])}
    annotators = _load_annotators()

    sorted_labels = sorted(
        id_map,
        key=lambda k: (_PREFIX_ORDER.get(_prefix(k), 99), int(k[len(_prefix(k)):])),
    )

    records = []
    for label in sorted_labels:
        doc_id = id_map[label]
        row = corpus[doc_id]
        text, dtype = row["doc_text"], row["doc_type"]

        vc, gen_m, spec_m, clauses = _vesting(text, dtype)

        # Union labels across annotators
        binding = foreign = domestic = natsec = emergency = False
        ann_rows = []
        for name, adata in annotators:
            clf = (adata.get(label) or {}).get("classification") or {}
            if not clf:
                continue
            cat = clf.get("category")
            le = clf.get("legal_effect")
            scope = clf.get("scope")
            ns = clf.get("national_security")
            emer = clf.get("emergency")

            if cat == "policy" and le == "legal":
                binding = True
            if scope == "foreign":
                foreign = True
            if scope == "domestic":
                domestic = True
            if scope == "foreign" and ns == "yes":
                natsec = True
            if emer == "yes":
                emergency = True

            ann_rows.append({
                "name": name,
                "category": cat or "—",
                "legal_effect": le or "—",
                "scope": scope or "—",
                "national_security": ns or "—",
                "emergency": emer or "—",
            })

        scope_str = " ".join(filter(None, [
            "foreign" if foreign else "",
            "domestic" if domestic else "",
        ])) or "unlabeled"

        slug = re.sub(r"-\d{4,}$", "", row["url"].rstrip("/").split("/")[-1])
        title = slug.replace("-", " ").title()

        records.append({
            "viewer_id": label,
            "document_id": doc_id,
            "doc_type": dtype,
            "date": row["date"],
            "president": row["president"],
            "url": row["url"],
            "title": title,
            "vesting": vc,
            "gen_m": [{"rule": m.rule, "text": m.text} for m in gen_m],
            "spec_m": [{"rule": m.rule, "text": m.text} for m in spec_m],
            "clauses": clauses,
            "binding": binding,
            "foreign": foreign,
            "domestic": domestic,
            "natsec": natsec,
            "emergency": emergency,
            "scope_str": scope_str,
            "annotators": ann_rows,
            "doc_text": text,
        })
    return records


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

def _highlight(clause_text: str, gen_m: list, spec_m: list) -> str:
    """Return HTML with generic (blue) and specific (purple) match highlights."""
    if not clause_text:
        return "<em>(none extracted)</em>"
    h = escape(clause_text)
    for m in gen_m:
        t = escape(m["text"])
        if t:
            h = h.replace(t, f'<mark class="gm">{t}</mark>', 1)
    for m in spec_m:
        t = escape(m["text"])
        if t:
            h = h.replace(t, f'<mark class="sm">{t}</mark>', 1)
    return h


def _ann_table(ann_rows: list) -> str:
    if not ann_rows:
        return '<p class="no-ann">No annotations loaded.</p>'
    rows_html = "".join(
        f"<tr><td>{escape(a['name'])}</td><td>{escape(a['category'])}</td>"
        f"<td>{escape(a['legal_effect'])}</td><td>{escape(a['scope'])}</td>"
        f"<td>{escape(a['national_security'])}</td><td>{escape(a['emergency'])}</td></tr>"
        for a in ann_rows
    )
    return (
        '<table class="ann-table"><thead><tr>'
        "<th>Annotator</th><th>Category</th><th>Legal effect</th>"
        "<th>Scope</th><th>Nat-sec</th><th>Emergency</th>"
        f"</tr></thead><tbody>{rows_html}</tbody></table>"
    )


def _fbtn(label: str, dim: str, val: str, color: str) -> str:
    return (
        f'<button class="fbtn" data-dim="{dim}" data-val="{val}"'
        f' style="--ac:{color}" onclick="toggle(this,\'{dim}\',\'{val}\')">'
        f'{escape(label)}</button>'
    )


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

_JS = r"""
const fs = {};  // filterState: {dim: Set(vals)}

function toggle(btn, dim, val) {
  if (!fs[dim]) fs[dim] = new Set();
  const s = fs[dim];
  s.has(val) ? s.delete(val) : s.add(val);
  if (s.size === 0) delete fs[dim];
  btn.classList.toggle('active', !!(fs[dim] && fs[dim].has(val)));
  apply();
}

function apply() {
  let shown = 0;
  document.querySelectorAll('.card').forEach(card => {
    const pass = Object.entries(fs).every(([dim, vals]) => {
      const cv = new Set((card.dataset[dim] || '').split(' ').filter(Boolean));
      return [...vals].some(v => cv.has(v));
    });
    card.style.display = pass ? '' : 'none';
    if (pass) shown++;
  });
  document.getElementById('cnt').textContent = `Showing ${shown} of 100`;
}

function clearAll() {
  for (const k in fs) delete fs[k];
  document.querySelectorAll('.fbtn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.card').forEach(c => c.style.display = '');
  document.getElementById('cnt').textContent = 'Showing 100 of 100';
}

function exportCSV() {
  const cols = [
    ['ID','vid'],['Type','doctype'],['Date','date'],['President','president'],
    ['Vesting','vesting'],['Binding','binding'],['Scope','scope'],
    ['Nat-sec','natsec'],['Emergency','emergency'],['Title','title'],['URL','url']
  ];
  const header = cols.map(([h]) => h).join(',');
  const rows = [...document.querySelectorAll('.card')]
    .filter(c => c.style.display !== 'none')
    .map(c => cols.map(([,k]) => '"' + (c.dataset[k] || '').replace(/"/g,'""') + '"').join(','));
  const a = document.createElement('a');
  a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent([header,...rows].join('\n'));
  a.download = 'directive_filter_export.csv';
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
}
"""

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; font-size: 14px; color: #222; background: #f6f8fa; }

/* ---- sticky header ---- */
.sticky-top { position: sticky; top: 0; z-index: 30; }
.page-head { background: #24292f; color: white; padding: 10px 20px; display: flex; align-items: center; gap: 12px; }
.page-head h1 { font-size: 15px; font-weight: 600; flex: 1; }
#cnt { font-size: 12px; color: #ccc; white-space: nowrap; }
.clear-btn { background: transparent; color: #ff8888; border: 1px solid #ff8888; padding: 4px 12px; border-radius: 5px; cursor: pointer; font-size: 12px; }
.clear-btn:hover { background: rgba(255,100,100,.15); }
.export-btn { background: #1a7f37; color: white; border: none; padding: 5px 13px; border-radius: 5px; cursor: pointer; font-size: 12px; }
.export-btn:hover { background: #166130; }

/* ---- filter panel ---- */
.filter-panel { background: white; border-bottom: 2px solid #d0d7de; padding: 10px 20px; }
.filter-intro { font-size: 11px; color: #888; margin-bottom: 8px; }
.frow { display: flex; align-items: center; gap: 10px; margin-bottom: 5px; }
.frow:last-child { margin-bottom: 0; }
.flabel { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .07em; color: #888; width: 86px; flex-shrink: 0; }
.fbtns { display: flex; flex-wrap: wrap; gap: 4px; }
.fbtn { border: 1px solid #d0d7de; background: white; padding: 2px 10px; border-radius: 14px; cursor: pointer; font-size: 12px; color: #444; }
.fbtn.active { background: var(--ac, #0550ae); color: white; border-color: transparent; font-weight: 600; }
.fbtn:hover:not(.active) { background: #f0f0f0; }

/* ---- summary strip ---- */
.sum-strip { background: #fff8e1; border-bottom: 1px solid #ffe082; padding: 7px 20px; font-size: 12px; color: #555; display: flex; flex-wrap: wrap; gap: 18px; }
.sum-item b { color: #222; }
.sum-lbl { font-weight: 700; color: #333; margin-right: 4px; }
.sum-note { font-size: 11px; color: #aaa; }

/* ---- cards ---- */
.cards-container { padding: 14px 20px; display: grid; gap: 12px; }
.card { background: white; border: 1px solid #d0d7de; border-radius: 8px; overflow: hidden; }
.card-head { background: #f6f8fa; border-bottom: 1px solid #d0d7de; padding: 9px 14px 7px; }
.card-top { display: flex; align-items: center; gap: 5px; flex-wrap: wrap; margin-bottom: 3px; }
.vid { font-size: 14px; font-weight: 700; }
.meta { font-size: 11px; color: #888; margin-left: auto; }
.card-link { font-size: 12px; color: #0550ae; text-decoration: none; }
.card-link:hover { text-decoration: underline; }
.card-body { padding: 9px 14px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; }
.dim-row { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }
.sec-label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .07em; color: #888; }
.clause-section { margin-bottom: 8px; }
.clause-text { font-size: 12px; background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 4px; padding: 7px; line-height: 1.5; margin-top: 3px; }
mark.gm { background: #cae8ff; color: #0550ae; border-radius: 2px; padding: 0 1px; }
mark.sm { background: #e8d5ff; color: #8250df; border-radius: 2px; padding: 0 1px; }
.legend { font-size: 11px; color: #888; margin-top: 3px; }
.legend mark { padding: 1px 4px; border-radius: 2px; }
details { margin-top: 7px; }
details summary { font-size: 12px; color: #0550ae; cursor: pointer; padding: 2px 0; user-select: none; }
.ann-table { border-collapse: collapse; font-size: 11px; margin-top: 5px; width: 100%; }
.ann-table th { background: #f6f8fa; text-align: left; padding: 3px 8px; border: 1px solid #d0d7de; font-weight: 600; }
.ann-table td { padding: 3px 8px; border: 1px solid #eee; }
.no-ann { font-size: 12px; color: #aaa; margin-top: 4px; }
.ft { font-size: 11px; font-family: "SF Mono", Consolas, monospace; background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 4px; padding: 8px; max-height: 380px; overflow-y: auto; white-space: pre-wrap; word-wrap: break-word; margin-top: 5px; line-height: 1.5; }
"""


def build_html(records: list[dict]) -> str:
    n = len(records)

    # Summary counts
    vc_ct = Counter(r["vesting"] for r in records)
    binding_ct = Counter("binding" if r["binding"] else "not_binding" for r in records)
    dt_ct = Counter(r["doc_type"] for r in records)
    n_foreign = sum(r["foreign"] for r in records)
    n_domestic = sum(r["domestic"] for r in records)
    n_natsec = sum(r["natsec"] for r in records)
    n_emergency = sum(r["emergency"] for r in records)

    # How many distinct annotators appeared across all records
    all_annotators = set()
    for r in records:
        for a in r["annotators"]:
            all_annotators.add(a["name"])
    n_coders = len(all_annotators)

    # Build filter panel
    filter_panel = f"""<div class="filter-panel">
  <div class="filter-intro">
    Within each row: <b>OR</b> &nbsp;·&nbsp; Across rows: <b>AND</b>
    &nbsp;·&nbsp; Human labels resolved by <b>union</b> across {n_coders} coders
  </div>
  <div class="frow">
    <span class="flabel">Vesting</span>
    <div class="fbtns">
      {_fbtn("Specific", "vesting", "specific", "#8250df")}
      {_fbtn("Generic", "vesting", "generic", "#0550ae")}
      {_fbtn("None", "vesting", "no_vesting_clause", "#57606a")}
    </div>
  </div>
  <div class="frow">
    <span class="flabel">Legal effect</span>
    <div class="fbtns">
      {_fbtn("Binding", "binding", "true", "#1a7f37")}
      {_fbtn("Not binding", "binding", "false", "#57606a")}
    </div>
  </div>
  <div class="frow">
    <span class="flabel">Scope</span>
    <div class="fbtns">
      {_fbtn("Foreign", "scope", "foreign", "#bf3989")}
      {_fbtn("Domestic", "scope", "domestic", "#2da44e")}
    </div>
  </div>
  <div class="frow">
    <span class="flabel">Nat-sec</span>
    <div class="fbtns">
      {_fbtn("Nat-sec", "natsec", "true", "#953800")}
      {_fbtn("Not nat-sec", "natsec", "false", "#57606a")}
    </div>
  </div>
  <div class="frow">
    <span class="flabel">Emergency</span>
    <div class="fbtns">
      {_fbtn("Emergency", "emergency", "true", "#e16812")}
      {_fbtn("Not emergency", "emergency", "false", "#57606a")}
    </div>
  </div>
  <div class="frow">
    <span class="flabel">Doc type</span>
    <div class="fbtns">
      {_fbtn("EO", "doctype", "executive_order", "#0550ae")}
      {_fbtn("Memo", "doctype", "memorandum", "#bf3989")}
      {_fbtn("Proc.", "doctype", "proclamation", "#2da44e")}
      {_fbtn("Letter", "doctype", "letter", "#6e40c9")}
    </div>
  </div>
</div>"""

    summary_strip = f"""<div class="sum-strip">
  <span><span class="sum-lbl">Vesting:</span>
    specific <b>{vc_ct['specific']}</b> &nbsp; generic <b>{vc_ct['generic']}</b> &nbsp; none <b>{vc_ct['no_vesting_clause']}</b></span>
  <span><span class="sum-lbl">Legal effect:</span>
    binding <b>{binding_ct['binding']}</b> &nbsp; not binding <b>{binding_ct['not_binding']}</b>
    <span class="sum-note">(any coder)</span></span>
  <span><span class="sum-lbl">Scope:</span>
    foreign <b>{n_foreign}</b> &nbsp; domestic <b>{n_domestic}</b>
    <span class="sum-note">(union, may overlap)</span></span>
  <span><span class="sum-lbl">Nat-sec:</span>
    yes <b>{n_natsec}</b> &nbsp; no <b>{n - n_natsec}</b></span>
  <span><span class="sum-lbl">Emergency:</span>
    yes <b>{n_emergency}</b> &nbsp; no <b>{n - n_emergency}</b></span>
  <span><span class="sum-lbl">Doc type:</span>
    EO <b>{dt_ct['executive_order']}</b> &nbsp;
    Memo <b>{dt_ct['memorandum']}</b> &nbsp;
    Proc. <b>{dt_ct['proclamation']}</b> &nbsp;
    Letter <b>{dt_ct['letter']}</b></span>
</div>"""

    # Build cards
    cards = []
    for r in records:
        label = r["viewer_id"]
        dt = r["doc_type"]
        vc = r["vesting"]
        clause_text = " | ".join(r["clauses"]) if r["clauses"] else ""

        # Scope display in card body
        scope_badges = ""
        if r["foreign"]:
            scope_badges += _badge("foreign", "foreign") + " "
        if r["domestic"]:
            scope_badges += _badge("domestic", "domestic") + " "
        if not scope_badges:
            scope_badges = '<span class="badge" style="background:#888;color:#fff">unlabeled</span>'

        natsec_text = "nat-sec" if r["natsec"] else "not nat-sec"
        natsec_key = "natsec_yes" if r["natsec"] else "natsec_no"
        emer_text = "emergency" if r["emergency"] else "not emergency"
        emer_key = "emergency_yes" if r["emergency"] else "emergency_no"
        binding_text = "binding" if r["binding"] else "not binding"
        binding_key = "binding" if r["binding"] else "not_binding"

        legend = ""
        if r["gen_m"] or r["spec_m"]:
            legend = '<div class="legend"><mark class="gm">generic</mark> <mark class="sm">specific</mark></div>'

        card = f"""<div class="card"
  data-vesting="{vc}"
  data-binding="{str(r['binding']).lower()}"
  data-scope="{escape(r['scope_str'])}"
  data-natsec="{str(r['natsec']).lower()}"
  data-emergency="{str(r['emergency']).lower()}"
  data-doctype="{dt}"
  data-vid="{escape(label)}"
  data-url="{escape(r['url'])}"
  data-title="{escape(r['title'])}"
  data-date="{escape(r['date'])}"
  data-president="{escape(r['president'])}">
  <div class="card-head">
    <div class="card-top">
      <strong class="vid">{escape(label)}</strong>
      {_badge(_DT_ABBR.get(dt, dt), dt)}
      {_badge(vc, vc)}
      <span class="meta">{escape(r['president'].split()[-1])} · {escape(r['date'][-4:])}</span>
    </div>
    <a href="{escape(r['url'])}" target="_blank" class="card-link">{escape(r['title'])}</a>
  </div>
  <div class="card-body">
    <div class="dim-row">
      {_badge(binding_text, binding_key)}
      {scope_badges}
      {_badge(natsec_text, natsec_key)}
      {_badge(emer_text, emer_key)}
    </div>
    <div class="clause-section">
      <span class="sec-label">Vesting clause</span>
      <div class="clause-text">{_highlight(clause_text, r['gen_m'], r['spec_m'])}</div>
      {legend}
    </div>
    <details>
      <summary>Annotator labels ({len(r['annotators'])} coder{"s" if len(r['annotators']) != 1 else ""})</summary>
      {_ann_table(r['annotators'])}
    </details>
    <details>
      <summary>Full text</summary>
      <pre class="ft">{escape(r['doc_text'][:10000])}{"…" if len(r['doc_text']) > 10000 else ""}</pre>
    </details>
  </div>
</div>"""
        cards.append(card)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Directive Filter — Sample 100</title>
<style>{_CSS}</style>
</head>
<body>
<div class="sticky-top">
  <div class="page-head">
    <h1>Presidential Directive Filter — Sample of 100</h1>
    <span id="cnt">Showing 100 of 100</span>
    <button class="clear-btn" onclick="clearAll()">✕ Clear filters</button>
    <button class="export-btn" onclick="exportCSV()">⬇ Export CSV</button>
  </div>
  {filter_panel}
</div>
{summary_strip}
<div class="cards-container">
{"".join(cards)}
</div>
<script>{_JS}</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("Loading corpus and annotations…")
    records = build_records()
    assert len(records) == 100, f"Expected 100 records, got {len(records)}"
    print(f"Built {len(records)} records")
    vc_ct = Counter(r["vesting"] for r in records)
    for k, v in sorted(vc_ct.items()):
        print(f"  vesting {k}: {v}")

    print("Building HTML…")
    html = build_html(records)
    HTML_OUT.write_text(html, encoding="utf-8")
    print(f"Wrote {HTML_OUT}")
    print(f"Open: open {HTML_OUT}")


if __name__ == "__main__":
    main()
