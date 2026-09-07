#!/usr/bin/env python3
"""Render the blind pilot CSV as a local, searchable browser review page."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=OUTPUTS / "pilot_human_gold.csv")
    parser.add_argument("--output", type=Path, default=OUTPUTS / "pilot_review.html")
    args = parser.parse_args()
    with args.input.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    payload = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    pilot_hash = hashlib.sha256(args.input.read_bytes()).hexdigest()[:12]
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Presidential statutory delegation — blind pilot</title>
<style>
*{{box-sizing:border-box}} body{{margin:0;font:15px/1.45 system-ui,sans-serif;color:#18212b;background:#f6f8fa}}
header{{position:sticky;top:0;z-index:2;background:#fff;border-bottom:1px solid #d0d7de;padding:14px 22px}}
h1{{font-size:20px;margin:0 0 5px}} p{{margin:5px 0;color:#57606a}} input{{width:360px;max-width:100%;padding:8px;border:1px solid #8c959f;border-radius:6px}}
main{{max-width:1180px;margin:20px auto;padding:0 20px}} article{{background:#fff;border:1px solid #d0d7de;border-radius:8px;margin:14px 0;padding:18px}}
h2{{font-size:17px;margin:0 0 10px}} .meta{{display:flex;flex-wrap:wrap;gap:7px;margin:0 0 12px}} .tag{{background:#ddf4ff;color:#0969da;border-radius:999px;padding:2px 8px;font-size:12px}} .broad{{background:#fff8c5;color:#7d4e00}}
dt{{font-weight:650;margin-top:15px}} dd{{margin:4px 0;white-space:pre-wrap;overflow-wrap:anywhere}} .box{{background:#f6f8fa;border:1px solid #d8dee4;border-radius:6px;padding:10px;max-height:260px;overflow:auto}}
details{{margin-top:12px}} summary{{cursor:pointer;font-weight:600}} code{{font-size:13px}} .empty{{padding:40px;text-align:center;color:#57606a}}
.toolbar{{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:10px}} button{{padding:8px 11px;border:1px solid #0969da;border-radius:6px;background:#0969da;color:#fff;cursor:pointer;font-weight:600}} button.secondary{{color:#0969da;background:#fff}} .status{{font-size:13px;color:#57606a}}
.coding{{margin-top:18px;padding:14px;background:#f6f8fa;border:1px solid #d8dee4;border-radius:6px}} label{{display:block;font-weight:650;margin:10px 0 4px}} textarea,select,input[type=date]{{width:100%;min-height:36px;padding:8px;border:1px solid #8c959f;border-radius:6px;font:13px/1.35 ui-monospace,monospace}} textarea{{min-height:76px}} textarea.notes{{font-family:inherit;font-size:14px}} .grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}} .checks{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;margin:12px 0}} .checks label{{margin:0;font-weight:500}} .checks input{{width:auto;min-height:0;margin-right:5px}} .hint{{color:#57606a;font-size:13px}}
</style></head><body>
<header><h1>Presidential statutory delegation — blind 30-authority pilot</h1>
<p>Code independently before any GPT output is run. The structured form matches the GPT response schema; entries save in this browser and can be downloaded as the pilot CSV.</p>
<div class="toolbar"><input id="search" autofocus placeholder="Search pilot authorities…"><button id="download">Download coded CSV</button><button id="clear" class="secondary">Clear browser entries</button><span class="status" id="status"></span></div></header><main id="items"></main>
<script>
const rows={payload};
const esc=s=>String(s||'').replace(/[&<>\"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]));
const storageKey='presidential-statutory-delegation-pilot-{pilot_hash}';
const saved=JSON.parse(localStorage.getItem(storageKey)||'{{}}');
rows.forEach(r=>Object.assign(r,saved[r.pilot_id]||{{}}));
const status=()=>{{
 const coded=rows.filter(r=>r.human_classifications_json||r.human_notes).length;
 document.querySelector('#status').textContent=`${{coded}} / ${{rows.length}} entries saved locally`;
}};
const persist=(id,field,value)=>{{
 const row=rows.find(r=>r.pilot_id===id); row[field]=value;
 saved[id]={{...(saved[id]||{{}}),[field]:value}};
 localStorage.setItem(storageKey,JSON.stringify(saved)); status();
}};
const defaults=r=>{{
 let dates=[]; try{{dates=JSON.parse(r.observed_dates)}}catch(_e){{}}
 return {{version_start:dates[0]||'',version_end:null,presidential_authorization:false,
   presidential_required_duty:false,presidential_condition_precedent:false,
   standalone_presidential_constraint:false,classification:'',confidence:'medium',
   operative_excerpt:'',rationale:'',official_sources:[]}};
}};
const oneVersion=r=>{{
 try{{const values=JSON.parse(r.human_classifications_json||'[]');if(Array.isArray(values)&&values.length===1)return {{...defaults(r),...values}};}}catch(_e){{}}
 return defaults(r);
}};
const isSelected=(value,option)=>value===option?'selected':'';
const checked=value=>value?'checked':'';
const sourceText=values=>Array.isArray(values)?values.join(String.fromCharCode(10)):'';
const structuredUpdate=id=>{{
 const row=rows.find(r=>r.pilot_id===id), value=defaults(row);
 document.querySelectorAll(`.structured[data-id="${{id}}"]`).forEach(el=>{{
   value[el.dataset.field]=el.type==='checkbox'?el.checked:el.value;
 }});
 value.version_end=value.version_end||null;
 value.official_sources=String(value.official_sources||'').split(String.fromCharCode(10)).map(x=>x.trim()).filter(Boolean);
 persist(id,'human_classifications_json',JSON.stringify([value],null,2));
}};
const render=()=>{{
 const q=document.querySelector('#search').value.toLowerCase();
 const selected=rows.filter(r=>Object.values(r).join(' ').toLowerCase().includes(q));
 document.querySelector('#items').innerHTML=selected.length?selected.map(r=>{{const c=oneVersion(r); return `<article>
 <h2>${{esc(r.pilot_id)}} · <code>${{esc(r.canonical_authority_id)}}</code></h2>
 <div class="meta"><span class="tag">${{esc(r.citation_kind)}}</span><span class="tag ${{r.is_broad==='true'?'broad':''}}">${{r.is_broad==='true'?'broad citation':'pinpoint citation'}}</span><span class="tag">${{esc(r.occurrence_count)}} occurrences</span></div>
 <dt>Citation form(s) for this authority</dt><dd>${{esc(r.citation_aliases)}}</dd>
 <dt>Observed directive dates</dt><dd>${{esc(r.observed_dates)}}</dd>
 <details open><summary>Sample vesting-clause context</summary><dd class="box">${{esc(r.sample_vesting_clauses)}}</dd></details>
 <details><summary>Supplied current source text${{r.supplied_current_heading?' — '+esc(r.supplied_current_heading):''}}</summary><dd class="box">${{esc(r.supplied_current_text||'No current OLRC text was supplied.')}}</dd></details>
 <details><summary>Amendment notes and source</summary><dd><a href="${{esc(r.supplied_official_url)}}" target="_blank" rel="noreferrer">${{esc(r.supplied_official_url||'No supplied official URL')}}</a></dd><dd class="box">${{esc(r.supplied_amendment_notes||'No supplied amendment notes.')}}</dd></details>
 <section class="coding"><strong>Your pilot coding</strong><div class="hint">A delegated classification requires presidential authorization or a presidential condition precedent. Required duties and constraints alone are nondelegations.</div>
 <div class="grid"><div><label>Version start</label><input class="structured" data-id="${{esc(r.pilot_id)}}" data-field="version_start" type="date" value="${{esc(c.version_start)}}"></div><div><label>Version end (blank = ongoing)</label><input class="structured" data-id="${{esc(r.pilot_id)}}" data-field="version_end" type="date" value="${{esc(c.version_end||'')}}"></div></div>
 <div class="checks"><label><input class="structured" data-id="${{esc(r.pilot_id)}}" data-field="presidential_authorization" type="checkbox" ${{checked(c.presidential_authorization)}}> Presidential authorization</label><label><input class="structured" data-id="${{esc(r.pilot_id)}}" data-field="presidential_required_duty" type="checkbox" ${{checked(c.presidential_required_duty)}}> Required presidential duty</label><label><input class="structured" data-id="${{esc(r.pilot_id)}}" data-field="presidential_condition_precedent" type="checkbox" ${{checked(c.presidential_condition_precedent)}}> Presidential condition precedent</label><label><input class="structured" data-id="${{esc(r.pilot_id)}}" data-field="standalone_presidential_constraint" type="checkbox" ${{checked(c.standalone_presidential_constraint)}}> Standalone presidential constraint</label></div>
 <div class="grid"><div><label>Classification</label><select class="structured" data-id="${{esc(r.pilot_id)}}" data-field="classification"><option value="">Choose…</option><option value="delegation" ${{isSelected(c.classification,'delegation')}}>delegation</option><option value="nondelegation" ${{isSelected(c.classification,'nondelegation')}}>nondelegation</option><option value="too_broad" ${{isSelected(c.classification,'too_broad')}}>too_broad</option><option value="cannot_verify" ${{isSelected(c.classification,'cannot_verify')}}>cannot_verify</option></select></div><div><label>Confidence</label><select class="structured" data-id="${{esc(r.pilot_id)}}" data-field="confidence"><option value="high" ${{isSelected(c.confidence,'high')}}>high</option><option value="medium" ${{isSelected(c.confidence,'medium')}}>medium</option><option value="low" ${{isSelected(c.confidence,'low')}}>low</option></select></div></div>
 <label>Operative statutory excerpt</label><textarea class="structured" data-id="${{esc(r.pilot_id)}}" data-field="operative_excerpt" placeholder="Short statutory text; may be empty for too_broad or cannot_verify">${{esc(c.operative_excerpt)}}</textarea>
 <label>Rationale</label><textarea class="structured" data-id="${{esc(r.pilot_id)}}" data-field="rationale" placeholder="Why the cited provision is or is not a delegation">${{esc(c.rationale)}}</textarea>
 <label>Official source URL(s), one per line</label><textarea class="structured" data-id="${{esc(r.pilot_id)}}" data-field="official_sources" placeholder="https://…">${{esc(sourceText(c.official_sources))}}</textarea>
 <label>Notes / thoughts</label><textarea class="notes" data-id="${{esc(r.pilot_id)}}" data-field="human_notes" placeholder="Your reasoning, questions, sources, or coding notes…">${{esc(r.human_notes)}}</textarea>
 <details><summary>Advanced: edit multiple-version classification JSON directly</summary><div class="hint">Use this only if the provision changed across observed dates. Editing a structured field afterward replaces this with one version.</div><textarea data-id="${{esc(r.pilot_id)}}" data-field="human_classifications_json" placeholder='[{{"version_start":"1900-01-01","version_end":null,...}}]'>${{esc(r.human_classifications_json)}}</textarea></details>
 </section>
 </article>`}}).join(''):'<div class="empty">No pilot authorities match that search.</div>';
 document.querySelectorAll('.structured[data-id]').forEach(el=>el.addEventListener('input',()=>structuredUpdate(el.dataset.id)));
 document.querySelectorAll('textarea[data-id]:not(.structured)').forEach(el=>el.addEventListener('input',()=>persist(el.dataset.id,el.dataset.field,el.value)));
}}; document.querySelector('#search').addEventListener('input',render); render();
const csvEscape=value=>`"${{String(value??'').replaceAll('"','""')}}"`;
document.querySelector('#download').addEventListener('click',()=>{{
 const fields=Object.keys(rows[0]);
 const newline=String.fromCharCode(13,10);
 const content=[fields.map(csvEscape).join(','),...rows.map(r=>fields.map(f=>csvEscape(r[f])).join(','))].join(newline)+newline;
 const link=document.createElement('a'); link.href=URL.createObjectURL(new Blob([content],{{type:'text/csv;charset=utf-8'}}));
 link.download='pilot_human_gold_coded.csv'; link.click(); URL.revokeObjectURL(link.href);
}});
document.querySelector('#clear').addEventListener('click',()=>{{
 if(confirm('Clear all locally saved coding entries from this browser?')){{localStorage.removeItem(storageKey); location.reload();}}
}}); status();
</script></body></html>"""
    args.output.write_text(page, encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
