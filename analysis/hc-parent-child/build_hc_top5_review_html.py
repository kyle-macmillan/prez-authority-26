#!/usr/bin/env python3
"""Create a standalone browser form for the HC top-five parent review."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "outputs" / "hc_top5_parent_review"


def main() -> None:
    with (OUTPUT / "top5_review_queue.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    data = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    token = hashlib.sha256(data.encode()).hexdigest()[:12]
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>HC Top-Five Drafting-Template Review</title><style>
:root{{color-scheme:light;--ink:#172033;--muted:#536171;--line:#d6dee8;--blue:#075985;--bg:#f4f7fb}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.45 system-ui,sans-serif}}main{{max-width:1500px;margin:auto;padding:24px}}h1{{margin:0 0 4px}}h2{{font-size:16px;margin:0}}.muted{{color:var(--muted)}}.toolbar,.review,details{{background:#fff;border:1px solid var(--line);border-radius:10px;padding:14px;margin:16px 0}}.toolbar{{display:flex;gap:12px;flex-wrap:wrap;align-items:center}}button,select,textarea{{font:inherit}}button{{background:var(--blue);border:0;border-radius:6px;color:#fff;padding:8px 12px;cursor:pointer}}button.secondary{{background:#e5edf5;color:var(--ink)}}select{{padding:7px;min-width:250px}}textarea{{width:100%;min-height:80px;padding:8px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.45 ui-monospace,monospace;background:#f8fafc;padding:12px;border-radius:6px}}summary{{cursor:pointer;font-weight:600}}.status{{margin-left:auto;font-weight:600}}a{{color:var(--blue)}}label{{display:block;margin-top:10px}}</style></head><body><main>
<h1>HC Top-Five Drafting-Template Review</h1><p class="muted">For each later directive, decide whether one earlier directive is its best plausible drafting template. Candidate order, method, scores, and HC category are hidden. Vesting clauses are excluded.</p>
<p class="muted">Choose A–E only if that earlier directive plausibly supplied the distinctive drafting template. Choose “None” if no candidate plausibly did; “Not an HC case” if the later directive itself falls outside the HC categories; or “Uncertain” when you cannot decide.</p>
<div class="toolbar"><button id="prev" class="secondary">← Previous</button><button id="next" class="secondary">Next →</button><select id="jump"></select><button id="download">Download decisions CSV</button><span id="status" class="status"></span></div>
<section class="review"><h2 id="title"></h2><div id="meta" class="muted"></div><label>Decision <select id="decision"><option value="">Choose…</option><option value="candidate_a">Candidate A</option><option value="candidate_b">Candidate B</option><option value="candidate_c">Candidate C</option><option value="candidate_d">Candidate D</option><option value="candidate_e">Candidate E</option><option value="none">None is a plausible drafting template</option><option value="not_high_confidence_family">Not an HC case</option><option value="uncertain">Uncertain</option></select></label><label>Notes<textarea id="notes"></textarea></label></section>
<details open><summary>Later directive</summary><a id="childlink" target="_blank" rel="noopener">Open source</a><pre id="childtext"></pre></details><div id="candidates"></div>
</main><script>
const ROWS={data};const STORE='hc-top5:'+{json.dumps(token)};let state={{...JSON.parse(localStorage.getItem(STORE)||'{{}}')}};let i=0;const $=x=>document.getElementById(x);function key(){{return ROWS[i].review_id}}function save(){{state[key()]={{decision:$('decision').value,review_notes:$('notes').value}};localStorage.setItem(STORE,JSON.stringify(state));status()}}function status(){{$('status').textContent=`${{ROWS.filter(r=>state[r.review_id]?.decision).length}} / ${{ROWS.length}} decided`}}function render(){{let r=ROWS[i],s=state[key()]||{{}};$('title').textContent=`${{i+1}}. ${{r.child_title}}`;$('meta').textContent=`${{r.child_type.replaceAll('_',' ')}} · ${{r.child_date}}`;$('decision').value=s.decision||'';$('notes').value=s.review_notes||'';$('childlink').href=r.child_url;$('childtext').textContent=r.child_non_vesting_text;let h='';for(let x of 'abcde'){{h+=`<details><summary>Candidate ${{x.toUpperCase()}} — ${{r['candidate_'+x+'_title']}} (${{r['candidate_'+x+'_date']}})</summary><a target="_blank" rel="noopener" href="${{r['candidate_'+x+'_url']}}">Open source</a><pre>${{r['candidate_'+x+'_non_vesting_text'].replaceAll('&','&amp;').replaceAll('<','&lt;')}}</pre></details>`}}$('candidates').innerHTML=h;$('prev').disabled=i===0;$('next').disabled=i===ROWS.length-1;$('jump').value=i;status()}}function download(){{save();let out=['review_id,decision,review_notes'];for(let r of ROWS){{let s=state[r.review_id]||{{}};let cell=x=>{{let v=String(x??'');return /[",\\n]/.test(v)?'"'+v.replaceAll('"','""')+'"':v}};out.push([r.review_id,s.decision||'',s.review_notes||''].map(cell).join(','))}}let a=document.createElement('a');a.href=URL.createObjectURL(new Blob([out.join('\\n')+'\\n'],{{type:'text/csv'}}));a.download='hc_top5_parent_decisions.csv';a.click()}}for(let [n,r] of ROWS.entries()){{let o=document.createElement('option');o.value=n;o.textContent=`${{n+1}}. ${{r.child_title}}`;$('jump').append(o)}}$('prev').onclick=()=>{{save();if(i){{--i;render()}}}};$('next').onclick=()=>{{save();if(i<ROWS.length-1){{++i;render()}}}};$('jump').onchange=()=>{{save();i=+$('jump').value;render()}};$('decision').onchange=save;$('notes').oninput=save;$('download').onclick=download;render();
</script></body></html>'''
    (OUTPUT / "top5_review.html").write_text(page, encoding="utf-8")
    print(f"wrote {OUTPUT / 'top5_review.html'}")


if __name__ == "__main__":
    main()
