#!/usr/bin/env python3
"""Build a stratified review sample from validated parent-acceptance decisions."""

from __future__ import annotations

import argparse
import csv
import html
import json
import random
from collections import Counter
from pathlib import Path


def jsonl(paths: list[Path]) -> list[dict]:
    return [json.loads(line) for path in paths for line in path.open(encoding="utf-8") if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decisions", type=Path, action="append", required=True)
    parser.add_argument("--documents", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--parents-per-type", type=int, default=3)
    parser.add_argument("--nonparents-per-type", type=int, default=2)
    parser.add_argument("--seed", type=int, default=20260816)
    args = parser.parse_args()

    decisions = jsonl(args.decisions)
    wanted = {str(row["child_id"]) for row in decisions} | {
        str(row["best_candidate_id"]) for row in decisions
    }
    documents = {}
    for row in jsonl([args.documents]):
        document_id = str(row["document_id"])
        if document_id in wanted: documents[document_id] = row

    rng = random.Random(args.seed)
    selected = []
    directive_types = sorted({documents[str(row["child_id"])]["document_type"] for row in decisions})
    for directive_type in directive_types:
        for decision, count in (("candidate", args.parents_per_type), ("none", args.nonparents_per_type)):
            eligible = [row for row in decisions if row["decision"] == decision and
                        documents[str(row["child_id"])]["document_type"] == directive_type]
            eligible.sort(key=lambda row: int(row["child_id"]))
            rng.shuffle(eligible)
            if len(eligible) < count:
                raise ValueError(f"only {len(eligible)} {directive_type}/{decision} decisions")
            selected.extend(eligible[:count])

    output = []
    for row in selected:
        child = documents[str(row["child_id"])]
        parent = documents[str(row["best_candidate_id"])]
        output.append({
            "child_id": str(row["child_id"]), "child_type": child["document_type"],
            "child_title": child.get("title", ""), "child_date": child.get("date", ""),
            "child_url": child.get("url", ""), "child_text": child.get("cleaned_masked_text", ""),
            "decision": row["decision"],
            "best_candidate_id": str(row["best_candidate_id"]),
            "parent_type": parent.get("document_type", ""), "parent_title": parent.get("title", ""),
            "parent_date": parent.get("date", ""), "parent_url": parent.get("url", ""),
            "parent_text": parent.get("cleaned_masked_text", ""),
            "ranking_score": row["ranking_score"], "acceptance_score": row["acceptance_score"],
            "reason": row["reason"],
            "matched_child_function_ids": json.dumps(row["matches"]["child"]),
            "matched_parent_function_ids": json.dumps(row["matches"]["parent"]),
            "snapshot_hash": row["snapshot_hash"],
        })

    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / "decision_sample.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output[0])); writer.writeheader(); writer.writerows(output)
    cards = []
    for row in output:
        accepted = row["decision"] == "candidate"
        cards.append(f'''<article class="card {row["decision"]}">
<div class="status">{"PARENT IDENTIFIED" if accepted else "NO PLAUSIBLE PARENT"}</div>
<div class="comparison">
<section class="document child"><div class="label">CHILD</div><h2>{html.escape(row["child_title"])}</h2>
<div class="meta">{html.escape(row["child_type"].replace("_", " ").title())} · {html.escape(row["child_date"])}</div>
<p><a href="{html.escape(row["child_url"])}">Open child directive ↗</a></p><div class="text">{html.escape(row["child_text"])}</div></section>
<section class="document parent"><div class="label">BEST-RANKED EARLIER CANDIDATE</div><h2>{html.escape(row["parent_title"])}</h2>
<div class="meta">{html.escape(row["parent_type"].replace("_", " ").title())} · {html.escape(row["parent_date"])}</div>
<p><a href="{html.escape(row["parent_url"])}">Open candidate directive ↗</a></p><div class="text">{html.escape(row["parent_text"])}</div></section>
</div>
<div class="scores"><span>Ranking <b>{float(row["ranking_score"]):.2f}</b></span><span>Acceptance <b>{float(row["acceptance_score"]):.2f}</b></span></div>
<p class="reason">{html.escape(str(row["reason"]))}</p>
<details><summary>IDs and matched functions</summary><pre>Child {html.escape(row["child_id"])}: {html.escape(row["matched_child_function_ids"])}\nCandidate {html.escape(row["best_candidate_id"])}: {html.escape(row["matched_parent_function_ids"])}</pre></details>
</article>''')
    html_path = args.output_dir / "decision_sample.html"
    html_path.write_text(f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gemini Function-Parent Review Sample</title><style>
body{{font:16px/1.5 system-ui,sans-serif;background:#f4f5f7;color:#17202a;margin:0}}main{{max-width:1500px;margin:auto;padding:32px}}h1{{margin-bottom:4px}}.lede{{color:#52606d;margin-top:0}}.grid{{display:grid;gap:20px}}.card{{background:white;border-radius:12px;padding:22px;border-left:7px solid #26734d;box-shadow:0 2px 10px #0001}}.card.none{{border-left-color:#a33}}.status{{font-size:12px;font-weight:800;letter-spacing:.08em;color:#26734d;margin-bottom:12px}}.none .status{{color:#a33}}.comparison{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}.document{{padding:16px;border:1px solid #d9e0e7;border-radius:9px;background:#fbfcfd;min-width:0}}.document.parent{{background:#f6f8fb}}.label{{font-size:11px;font-weight:800;letter-spacing:.08em;color:#657482}}h2{{font-size:19px;line-height:1.3;margin:.45rem 0}}.meta{{color:#667}}.text{{height:560px;overflow:auto;white-space:pre-wrap;font:14px/1.55 Georgia,serif;background:white;border:1px solid #e1e5e9;border-radius:6px;padding:16px}}.scores{{display:flex;gap:24px;background:#f5f7f9;padding:10px 14px;border-radius:7px;margin:16px 0}}.reason{{white-space:pre-wrap}}a{{color:#075da8}}pre{{white-space:pre-wrap}}details{{color:#52606d}}@media(max-width:760px){{.comparison{{grid-template-columns:1fr}}main{{padding:16px}}.text{{height:400px}}}}
</style></head><body><main><h1>Gemini Function-Parent Review Sample</h1><p class="lede">20 reproducibly sampled cases: three accepted parents and two non-parents for each directive type.</p><div class="grid">{''.join(cards)}</div></main></body></html>''', encoding="utf-8")
    manifest = {
        "schema_version": 1, "seed": args.seed, "rows": len(output),
        "parents_per_type": args.parents_per_type, "nonparents_per_type": args.nonparents_per_type,
        "directive_types": directive_types,
        "strata": {f"{kind}:{decision}": count for (kind, decision), count in sorted(
            Counter((row["child_type"], row["decision"]) for row in output).items())},
        "source_decisions": [str(path) for path in args.decisions],
        "output": str(csv_path), "html": str(html_path),
    }
    (args.output_dir / "sample_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__": main()
