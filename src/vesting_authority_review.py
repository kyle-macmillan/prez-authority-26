"""Build and summarize a comparative review sample of vesting-authority documents.

Generate the fixed-seed sample and review page:
  python3 src/vesting_authority_review.py

Summarize a CSV exported after manual coding:
  python3 src/vesting_authority_review.py --summarize path/to/coded.csv
"""

import argparse
import csv
import html
import json
import math
import random
import re
from collections import Counter
from pathlib import Path

from segmenter import segment_ordering
from vesting_authority_stats import DEFAULT_AUDIT, DEFAULT_DEV, DEFAULT_HOLDOUT, load_corpus


ROOT = Path(__file__).parent.parent
DEFAULT_SAMPLE = ROOT / "data" / "vesting_authority_review_sample.csv"
DEFAULT_HTML = ROOT / "data" / "vesting_authority_review.html"
DEFAULT_SEED = 20260622
GROUPS = ("generic_only", "generic_plus_specific")
TYPE_ALLOCATION = {
    "executive_order": 40,
    "memorandum": 25,
    "letter": 1,
    "proclamation": 34,
}
ACTION_MODES = (
    "direct_legal_effect",
    "agency_direction",
    "mixed",
    "ceremonial_symbolic",
    "unclear_other",
)
RELIANCE_MODES = (
    "explicit_applicable_law",
    "explicit_agency_statutory_authority",
    "both",
    "neither",
    "unclear",
)
CONFIDENCE_LEVELS = ("high", "medium", "low")

OUTPUT_FIELDS = (
    "sample_id", "display_order", "authority_footing", "doc_type",
    "stratum_population", "stratum_sample_n", "sample_weight", "document_id",
    "date", "year", "president", "url", "source_file", "vesting_clauses",
    "generic_authority_matches", "specific_authority_matches", "operative_excerpt",
    "full_text", "primary_action_mode", "agency_authority_reliance",
    "reviewer_confidence", "reviewer_notes",
)


def load_audit(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def select_sample(audit_rows: list[dict], seed: int = DEFAULT_SEED) -> list[dict]:
    """Return a deterministic matched-stratum sample with sampling metadata."""
    selected = []
    for group in GROUPS:
        qualifies = group == "generic_only"
        for doc_type, sample_n in TYPE_ALLOCATION.items():
            pool = sorted(
                (
                    row for row in audit_rows
                    if (row["qualifies"] == "true") == qualifies
                    and row["doc_type"] == doc_type
                ),
                key=lambda row: int(row["document_id"]),
            )
            if len(pool) < sample_n:
                raise ValueError(
                    f"{group}/{doc_type} needs {sample_n} documents but only {len(pool)} exist"
                )
            rng = random.Random(f"{seed}:{group}:{doc_type}")
            for row in rng.sample(pool, sample_n):
                item = dict(row)
                item["authority_footing"] = group
                item["stratum_population"] = len(pool)
                item["stratum_sample_n"] = sample_n
                item["sample_weight"] = len(pool) / sample_n
                selected.append(item)

    random.Random(seed).shuffle(selected)
    for index, row in enumerate(selected, 1):
        row["sample_id"] = f"VA{index:03d}"
        row["display_order"] = index
    return selected


def operative_excerpt(doc_text: str, doc_type: str, limit: int = 6000) -> str:
    actions = [
        item.text
        for item in segment_ordering(doc_text, doc_type)
        if item.seg_type == "order_action"
    ]
    text = "\n\n".join(actions) if actions else doc_text
    text = "\n\n".join(part.strip() for part in re.split(r"  +", text) if part.strip())
    return text[:limit]


def materialize_sample(selected: list[dict], corpus_rows: list[dict]) -> list[dict]:
    source = {row[""]: row for row in corpus_rows}
    records = []
    for sampled in selected:
        document_id = sampled["document_id"]
        if document_id not in source:
            raise ValueError(f"sampled document {document_id} is missing from the corpus")
        document = source[document_id]
        year_match = re.search(r"(\d{4})$", document["date"])
        records.append(
            {
                "sample_id": sampled["sample_id"],
                "display_order": sampled["display_order"],
                "authority_footing": sampled["authority_footing"],
                "doc_type": sampled["doc_type"],
                "stratum_population": sampled["stratum_population"],
                "stratum_sample_n": sampled["stratum_sample_n"],
                "sample_weight": f"{sampled['sample_weight']:.8f}",
                "document_id": document_id,
                "date": document["date"],
                "year": year_match.group(1) if year_match else "",
                "president": document["president"],
                "url": document["url"],
                "source_file": sampled["source_file"],
                "vesting_clauses": sampled["vesting_clauses"],
                "generic_authority_matches": sampled["generic_authority_matches"],
                "specific_authority_matches": sampled["specific_authority_matches"],
                "operative_excerpt": operative_excerpt(document["doc_text"], document["doc_type"]),
                "full_text": "\n\n".join(
                    part.strip() for part in re.split(r"  +", document["doc_text"]) if part.strip()
                ),
                "primary_action_mode": "",
                "agency_authority_reliance": "",
                "reviewer_confidence": "",
                "reviewer_notes": "",
            }
        )
    return records


def write_sample(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(records)


def _options(values: tuple[str, ...]) -> str:
    return '<option value="">Not coded</option>' + "".join(
        f'<option value="{html.escape(value)}">{html.escape(value.replace("_", " ").title())}</option>'
        for value in values
    )


def build_html(records: list[dict]) -> str:
    data = json.dumps(records, ensure_ascii=False).replace("</", "<\\/")
    template = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vesting Authority Review</title>
<style>
:root{font-family:system-ui,sans-serif;color:#172033;background:#f5f7fa}*{box-sizing:border-box}
body{margin:0}.top{position:sticky;top:0;z-index:2;background:#172033;color:white;padding:12px 20px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
button,select,textarea{font:inherit}button{padding:7px 12px;border:1px solid #aeb8c7;border-radius:6px;background:white;cursor:pointer}.top button{border-color:#65738a}
.progress{margin-left:auto}.wrap{max-width:1200px;margin:20px auto;padding:0 18px}.card{background:white;border:1px solid #d9e0e9;border-radius:9px;padding:18px;margin-bottom:15px}
.meta{display:flex;gap:12px;flex-wrap:wrap;color:#536176}.badge{background:#e8eef8;padding:3px 8px;border-radius:12px}.footing{background:#fff3cd}
h2{margin:0 0 8px}.text{white-space:pre-wrap;line-height:1.5;max-height:420px;overflow:auto;border-left:4px solid #657fc1;padding:10px 14px;background:#f8faff}
.evidence{white-space:pre-wrap;font-family:ui-monospace,monospace;font-size:13px}.grid{display:grid;grid-template-columns:repeat(3,minmax(180px,1fr));gap:15px}.field label{display:block;font-weight:650;margin-bottom:5px}.field select,.field textarea{width:100%;padding:8px;border:1px solid #b8c2d0;border-radius:6px}.field.notes{grid-column:1/-1}.field textarea{min-height:90px}
.codebook li{margin:6px 0}.hidden{display:none}@media(max-width:750px){.grid{grid-template-columns:1fr}.progress{margin-left:0}}
</style></head><body>
<div class="top"><button id="prev">← Previous</button><button id="next">Next →</button><button id="export">Export coded CSV</button><button id="toggle-full">Show/hide full text</button><span class="progress" id="progress"></span></div>
<main class="wrap">
<section class="card"><h2 id="title"></h2><div class="meta" id="meta"></div></section>
<section class="card"><h3>Vesting clause and authority evidence</h3><div id="vesting" class="text"></div><div id="evidence" class="evidence"></div></section>
<section class="card"><h3>Operative excerpt</h3><div id="excerpt" class="text"></div></section>
<section class="card hidden" id="full-card"><h3>Full document</h3><div id="full" class="text"></div></section>
<section class="card"><h3>Manual coding</h3><div class="grid">
<div class="field"><label for="action">Primary action mode</label><select id="action">__ACTION_OPTIONS__</select></div>
<div class="field"><label for="reliance">Agency-authority reliance</label><select id="reliance">__RELIANCE_OPTIONS__</select></div>
<div class="field"><label for="confidence">Confidence</label><select id="confidence">__CONFIDENCE_OPTIONS__</select></div>
<div class="field notes"><label for="notes">Notes</label><textarea id="notes"></textarea></div>
</div></section>
<section class="card codebook"><h3>Codebook</h3><ul>
<li><b>Direct legal effect:</b> directly revokes, amends, designates, establishes, terminates, or changes legal status.</li>
<li><b>Agency direction:</b> principally instructs agencies or officers to act.</li>
<li><b>Mixed:</b> substantial direct effects and agency directions, with neither clearly primary.</li>
<li><b>Ceremonial/symbolic:</b> commemorative, proclamatory, or flag/status action without material agency implementation.</li>
<li><b>Agency-authority reliance:</b> code explicit “applicable law” language and explicit reliance on an agency’s statutory authority separately.</li>
</ul></section>
</main>
<script>
const rows=__DATA__; const storageKey='vesting-authority-review-v1'; let index=0;
const saved=JSON.parse(localStorage.getItem(storageKey)||'{}');
for(const row of rows){if(saved[row.sample_id]) Object.assign(row,saved[row.sample_id]);}
const $=id=>document.getElementById(id);
function show(){const r=rows[index];$('title').textContent=`${r.sample_id}: ${r.doc_type.replaceAll('_',' ')} — ${r.date}`;
$('meta').innerHTML=''; for(const value of [r.authority_footing,r.president,`Document ${r.document_id}`,`weight ${r.sample_weight}`]){const s=document.createElement('span');s.className='badge'+(value===r.authority_footing?' footing':'');s.textContent=value;$('meta').appendChild(s);}
$('vesting').textContent=JSON.parse(r.vesting_clauses).join('\n\n');
const specific=JSON.parse(r.specific_authority_matches);$('evidence').textContent=specific.length?'Specific matches: '+specific.map(x=>`${x.rule}: ${x.text}`).join(' | '):'Specific matches: none';
$('excerpt').textContent=r.operative_excerpt;$('full').textContent=r.full_text;$('action').value=r.primary_action_mode;$('reliance').value=r.agency_authority_reliance;$('confidence').value=r.reviewer_confidence;$('notes').value=r.reviewer_notes;
const done=rows.filter(x=>x.primary_action_mode&&x.agency_authority_reliance).length;$('progress').textContent=`${index+1} / ${rows.length} · ${done} fully coded`;}
function save(){const r=rows[index];r.primary_action_mode=$('action').value;r.agency_authority_reliance=$('reliance').value;r.reviewer_confidence=$('confidence').value;r.reviewer_notes=$('notes').value;saved[r.sample_id]={primary_action_mode:r.primary_action_mode,agency_authority_reliance:r.agency_authority_reliance,reviewer_confidence:r.reviewer_confidence,reviewer_notes:r.reviewer_notes};localStorage.setItem(storageKey,JSON.stringify(saved));}
for(const id of ['action','reliance','confidence','notes']) $(id).addEventListener('input',()=>{save();show();});
$('prev').onclick=()=>{save();index=(index+rows.length-1)%rows.length;show();};$('next').onclick=()=>{save();index=(index+1)%rows.length;show();};$('toggle-full').onclick=()=>$('full-card').classList.toggle('hidden');
function csvCell(v){const s=String(v??'');return /[",\n]/.test(s)?'"'+s.replaceAll('"','""')+'"':s;}
$('export').onclick=()=>{save();const keys=Object.keys(rows[0]);const csv=[keys.join(','),...rows.map(r=>keys.map(k=>csvCell(r[k])).join(','))].join('\n');const blob=new Blob([csv],{type:'text/csv;charset=utf-8'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='vesting_authority_review_coded.csv';a.click();URL.revokeObjectURL(a.href);};show();
</script></body></html>'''
    return (
        template.replace("__ACTION_OPTIONS__", _options(ACTION_MODES))
        .replace("__RELIANCE_OPTIONS__", _options(RELIANCE_MODES))
        .replace("__CONFIDENCE_OPTIONS__", _options(CONFIDENCE_LEVELS))
        .replace("__DATA__", data)
    )


def write_html(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_html(records), encoding="utf-8")


def validate_coded_rows(rows: list[dict]) -> None:
    allowed = {
        "primary_action_mode": set(ACTION_MODES) | {""},
        "agency_authority_reliance": set(RELIANCE_MODES) | {""},
        "reviewer_confidence": set(CONFIDENCE_LEVELS) | {""},
    }
    for row in rows:
        for field, values in allowed.items():
            if row.get(field, "") not in values:
                raise ValueError(f"{row.get('sample_id', '?')}: invalid {field}={row.get(field)!r}")


def _weighted_stats(rows: list[dict], predicate) -> tuple[float, float, float, int]:
    weights = [float(row["sample_weight"]) for row in rows]
    if not weights:
        return 0.0, 0.0, 0.0, 0
    proportion = sum(w for row, w in zip(rows, weights) if predicate(row)) / sum(weights)
    effective_n = sum(weights) ** 2 / sum(weight * weight for weight in weights)
    se = math.sqrt(proportion * (1 - proportion) / effective_n) if effective_n else 0
    return proportion, max(0.0, proportion - 1.96 * se), min(1.0, proportion + 1.96 * se), len(rows)


def summarize_rows(rows: list[dict]) -> dict:
    validate_coded_rows(rows)
    summary = {}
    for group in GROUPS:
        group_rows = [row for row in rows if row["authority_footing"] == group]
        action_rows = [row for row in group_rows if row["primary_action_mode"]]
        reliance_rows = [row for row in group_rows if row["agency_authority_reliance"]]
        summary[group] = {
            "action_unweighted": Counter(row["primary_action_mode"] for row in action_rows),
            "action_weighted": {
                value: sum(float(row["sample_weight"]) for row in action_rows if row["primary_action_mode"] == value)
                for value in ACTION_MODES
            },
            "reliance_unweighted": Counter(row["agency_authority_reliance"] for row in reliance_rows),
            "reliance_weighted": {
                value: sum(float(row["sample_weight"]) for row in reliance_rows if row["agency_authority_reliance"] == value)
                for value in RELIANCE_MODES
            },
            "direct_effect": _weighted_stats(
                action_rows, lambda row: row["primary_action_mode"] == "direct_legal_effect"
            ),
            "agency_direction": _weighted_stats(
                action_rows, lambda row: row["primary_action_mode"] == "agency_direction"
            ),
            "explicit_agency_reliance": _weighted_stats(
                reliance_rows,
                lambda row: row["agency_authority_reliance"]
                in {"explicit_agency_statutory_authority", "both"},
            ),
        }
    return summary


def print_coded_summary(rows: list[dict]) -> None:
    summary = summarize_rows(rows)
    for group in GROUPS:
        print(f"\n{group}")
        print("  action counts:", dict(summary[group]["action_unweighted"]))
        print("  weighted action totals:", {
            key: round(value, 2) for key, value in summary[group]["action_weighted"].items()
        })
        print("  reliance counts:", dict(summary[group]["reliance_unweighted"]))
        print("  weighted reliance totals:", {
            key: round(value, 2) for key, value in summary[group]["reliance_weighted"].items()
        })
        for measure in ("direct_effect", "agency_direction", "explicit_agency_reliance"):
            estimate, lower, upper, n = summary[group][measure]
            if n:
                print(
                    f"  {measure}: {estimate:.1%} "
                    f"(approx. 95% CI {lower:.1%}–{upper:.1%}; coded n={n})"
                )
            else:
                print(f"  {measure}: no coded observations")

    comparisons = (
        ("direct_effect", "generic_plus_specific", "generic_only"),
        ("agency_direction", "generic_only", "generic_plus_specific"),
        ("explicit_agency_reliance", "generic_only", "generic_plus_specific"),
    )
    print("\nHypothesis-facing weighted differences")
    for measure, positive_group, negative_group in comparisons:
        positive = summary[positive_group][measure]
        negative = summary[negative_group][measure]
        if positive[3] and negative[3]:
            difference = positive[0] - negative[0]
            print(f"  {measure} ({positive_group} minus {negative_group}): {difference:+.1%}")
        else:
            print(f"  {measure}: unavailable until both groups have coded observations")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--dev", type=Path, default=DEFAULT_DEV)
    parser.add_argument("--holdout", type=Path, default=DEFAULT_HOLDOUT)
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument("--html", type=Path, default=DEFAULT_HTML)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--summarize", type=Path)
    args = parser.parse_args()

    if args.summarize:
        with open(args.summarize, newline="", encoding="utf-8-sig") as handle:
            print_coded_summary(list(csv.DictReader(handle)))
        return

    selected = select_sample(load_audit(args.audit), args.seed)
    records = materialize_sample(selected, load_corpus([args.dev, args.holdout]))
    write_sample(args.sample, records)
    write_html(args.html, records)
    print(f"Sample CSV: {args.sample} ({len(records)} documents)")
    print(f"Review HTML: {args.html}")


if __name__ == "__main__":
    main()
