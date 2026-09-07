#!/usr/bin/env python3
"""Create standalone browser review pages for the HC parent-child pilot."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
DEFAULT_OUTPUT = HERE / "outputs"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_page(
    path: Path, title: str, intro: str, rows: list[dict], *, kind: str,
    download_filename: str | None = None,
) -> None:
    data = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    # A rebuilt queue may reuse P001, P002, … for different pairs.  Scope browser
    # storage to this exact rendered data so old selections cannot attach to new rows.
    review_token = hashlib.sha256(data.encode("utf-8")).hexdigest()[:12]
    fields = {
        "family": {
            "id": "review_id", "decision": "family_member",
            "options": [("member", "Member of HC union"), ("not_member", "Not a member of HC union"), ("uncertain", "Uncertain")],
            "left": ("Directive", "non_vesting_text"), "right": None,
            "meta": lambda r: f"{r['document_type'].replace('_', ' ')} · {r['date']} · {r['president']}",
            "file": "family_review_decisions.csv",
            "csv": ["review_id", "family_id", "document_id", "decision", "review_notes"],
        },
        "parent": {
            "id": "pair_id", "decision": "parent_relationship",
            "options": [
                ("parent", "Parent"), ("not_parent", "Not a parent"),
                ("not_high_confidence_family", "Not an HC-family case"),
                ("out_of_scope", "Out of scope (legacy)"), ("uncertain", "Uncertain"),
            ],
            "left": ("Later directive (child)", "child_non_vesting_text"),
            "right": ("Earlier directive (candidate parent)", "parent_non_vesting_text"),
            "meta": lambda r: f"Child: {r['child_type'].replace('_', ' ')} · {r['child_date']}  |  Parent: {r['parent_type'].replace('_', ' ')} · {r['parent_date']}",
            "file": "parent_pair_decisions.csv",
            "csv": ["pair_id", "decision", "review_notes"],
        },
    }[kind]
    if download_filename:
        fields = dict(fields)
        fields["file"] = download_filename
    options = "".join(
        f'<option value="{html.escape(value)}">{html.escape(label)}</option>'
        for value, label in fields["options"]
    )
    initial = {
        row[fields["id"]]: {
            "decision": row.get("decision", ""),
            "review_notes": row.get("review_notes", ""),
        }
        for row in rows
        if row.get("decision") or row.get("review_notes")
    }
    initial_json = json.dumps(initial, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    row_meta = [
        {
            "id": row[fields["id"]],
            "title": (
                row.get("title") or row.get("child_title") or row.get("document_id") or row.get("child_id")
            ),
            "meta": fields["meta"](row),
        }
        for row in rows
    ]
    row_meta_json = json.dumps(row_meta, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    left_label, left_text = fields["left"]
    right = fields["right"]
    panels = f'''<section class="document"><h2 id="left-label">{html.escape(left_label)}</h2><a id="left-link" target="_blank" rel="noopener">Open source</a><pre id="left-text"></pre></section>'''
    if right:
        right_label, right_text = right
        panels += f'''<section class="document"><h2 id="right-label">{html.escape(right_label)}</h2><a id="right-link" target="_blank" rel="noopener">Open source</a><pre id="right-text"></pre></section>'''
    columns = "two" if right else "one"
    path.write_text(f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root{{color-scheme:light;--ink:#172033;--muted:#536171;--line:#d6dee8;--blue:#075985;--bg:#f4f7fb}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.45 system-ui,sans-serif}}
main{{max-width:1500px;margin:auto;padding:24px}} h1{{margin:0 0 4px}} h2{{font-size:16px;margin:0 0 6px}} .muted{{color:var(--muted)}}
.toolbar,.review{{background:#fff;border:1px solid var(--line);border-radius:10px;padding:14px;margin:16px 0}} .toolbar{{display:flex;gap:12px;flex-wrap:wrap;align-items:center}}
button,select,input,textarea{{font:inherit}} button{{background:var(--blue);border:0;border-radius:6px;color:white;padding:8px 12px;cursor:pointer}} button.secondary{{background:#e5edf5;color:var(--ink)}}
select{{min-width:180px;padding:7px}} textarea{{width:100%;min-height:86px;padding:8px}} .status{{margin-left:auto;font-weight:600}}
.review{{display:grid;grid-template-columns:1fr;gap:12px}} .documents.two{{display:grid;grid-template-columns:1fr 1fr;gap:14px}} .documents.one{{display:grid;grid-template-columns:minmax(0,1fr)}}
.document{{border:1px solid var(--line);border-radius:8px;padding:12px;min-width:0}} pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;max-height:none;overflow:visible;background:#f8fafc;padding:12px;border-radius:6px}}
.choice{{display:flex;gap:10px;align-items:center;flex-wrap:wrap}} a{{color:var(--blue)}} #case-title{{margin:0}} @media(max-width:850px){{.documents.two{{grid-template-columns:1fr}}}}
</style></head><body><main>
<h1>{html.escape(title)}</h1><p class="muted">{html.escape(intro)}</p>
<p class="muted">Selections are stored in this browser until you download them. Operative vesting clauses are excluded.</p>
<div class="toolbar"><button id="previous" class="secondary">← Previous</button><button id="next" class="secondary">Next →</button><select id="jump"></select><button id="download">Download decisions CSV</button><button id="clear" class="secondary">Clear this case</button><span id="status" class="status"></span></div>
<article class="review"><div><h2 id="case-title"></h2><div id="case-meta" class="muted"></div></div><div class="choice"><label for="decision">Decision</label><select id="decision"><option value="">Choose…</option>{options}</select></div><label for="notes">Notes</label><textarea id="notes" placeholder="Optional explanation"></textarea></article>
<div class="documents {columns}">{panels}</div>
</main><script>
const ROWS={data}; const META={row_meta_json}; const INITIAL={initial_json};
const KIND={json.dumps(kind)}; const ID_FIELD={json.dumps(fields['id'])}; const LEFT_TEXT={json.dumps(left_text)}; const RIGHT_TEXT={json.dumps(right[1] if right else '')}; const FILE_NAME={json.dumps(fields['file'])}; const CSV_FIELDS={json.dumps(fields['csv'])};
const STORE='hc-parent-child:'+KIND+':{review_token}'; let state={{...INITIAL,...JSON.parse(localStorage.getItem(STORE)||'{{}}')}}; let index=0;
const $=id=>document.getElementById(id); const esc=v=>String(v??'');
function current(){{return ROWS[index]}} function key(){{return current()[ID_FIELD]}}
function save(){{state[key()]={{decision:$('decision').value,review_notes:$('notes').value}};localStorage.setItem(STORE,JSON.stringify(state));renderStatus()}}
function renderStatus(){{let done=ROWS.filter(r=>state[r[ID_FIELD]]?.decision).length;$('status').textContent=`${{done}} / ${{ROWS.length}} decided`;}}
function render(){{let r=current(),m=META[index],saved=state[key()]||{{}};$('case-title').textContent=`${{index+1}}. ${{m.title}}`;$('case-meta').textContent=m.meta;$('decision').value=saved.decision||'';$('notes').value=saved.review_notes||'';$('left-text').textContent=r[LEFT_TEXT]||'';$('left-link').href=r.url||r.child_url||'#';
if(RIGHT_TEXT){{$('right-text').textContent=r[RIGHT_TEXT]||'';$('right-link').href=r.parent_url||'#';}} $('jump').value=String(index);$('previous').disabled=index===0;$('next').disabled=index===ROWS.length-1;renderStatus();}}
function csvCell(v){{let s=String(v??'');return /[",\\n]/.test(s)?'"'+s.replaceAll('"','""')+'"':s}}
function download(){{save();let lines=[CSV_FIELDS.join(',')];for(let r of ROWS){{let s=state[r[ID_FIELD]]||{{}};let data={{...r,...s}};lines.push(CSV_FIELDS.map(f=>csvCell(data[f])).join(','));}}let blob=new Blob([lines.join('\\n')+'\\n'],{{type:'text/csv'}});let a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=FILE_NAME;a.click();URL.revokeObjectURL(a.href);}}
$('previous').onclick=()=>{{save();if(index){{index--;render()}}}};$('next').onclick=()=>{{save();if(index<ROWS.length-1){{index++;render()}}}};$('decision').onchange=save;$('notes').oninput=save;$('download').onclick=download;$('clear').onclick=()=>{{delete state[key()];localStorage.setItem(STORE,JSON.stringify(state));render()}};
for(let [i,m] of META.entries()){{let o=document.createElement('option');o.value=String(i);o.textContent=`${{i+1}}. ${{m.title}}`; $('jump').append(o)}};$('jump').onchange=()=>{{save();index=Number($('jump').value);render()}};render();
</script></body></html>''', encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--family-download-name", default="family_review_decisions.csv")
    parser.add_argument("--parent-download-name", default="parent_pair_decisions.csv")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--family-only", action="store_true")
    mode.add_argument("--parent-only", action="store_true")
    args = parser.parse_args()
    written = []
    if not args.parent_only:
        family = read_csv(args.output / "family_review_queue.csv")
        page = args.output / "family_review.html"
        write_page(
            page, "HC Family Review",
            "Decide whether this directive belongs to any high-confidence category. The category used to sample the case and rule-match status are hidden.",
            family, kind="family", download_filename=args.family_download_name,
        )
        written.append(page)
    if not args.family_only:
        parent = read_csv(args.output / "parent_pair_review.csv")
        page = args.output / "parent_pair_review.html"
        write_page(
            page, "HC Parent-Pair Review",
            "Decide whether the earlier directive is a plausible drafting parent for the later directive. Scores, family labels, and methods are hidden.",
            parent, kind="parent", download_filename=args.parent_download_name,
        )
        written.append(page)
    print("wrote " + " and ".join(str(path) for path in written))


if __name__ == "__main__":
    main()
