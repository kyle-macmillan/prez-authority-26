#!/usr/bin/env python3
"""Build, validate, score, and summarize the in-text citation analysis."""

from __future__ import annotations

import argparse
import csv
import html
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

from citation_core import (  # noqa: E402
    DEV, EXPECTED_DEVELOPMENT_HASH, build_segments, entity_set, id_hash,
    regex_citations, validate_citations, validate_development_rows,
)


SEED = 260907
DOC_TYPES = ("executive_order", "memorandum", "letter", "proclamation")
VESTING_HINT = re.compile(
    r"authority\s+vested\s+in\s+me|\bI,\s+.{0,120}?President\s+of\s+the\s+United\s+States",
    re.I | re.S,
)
CITATION_HINT = re.compile(
    r"\b(?:\d+\s+U\.?S\.?C\.?|Public\s+Law|\d+\s+Stat\.?|"
    r"Executive\s+Orders?\s+(?:No\.?\s*)?\d+|Proclamation\s+(?:No\.?\s*)?\d+|"
    r"\d+\s+C\.?F\.?R\.?|Constitution|[A-Z][A-Za-z0-9'’&.-]+(?:\s+"
    r"[A-Z][A-Za-z0-9'’&.-]+){1,10}\s+Act)\b",
    re.I,
)


def read_csv(path: Path = DEV) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    validate_development_rows(rows)
    return rows


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def decade(row: dict[str, str]) -> str:
    match = re.search(r"\d{4}", row.get("date", ""))
    return f"{int(match.group()) // 10 * 10}s" if match else "unknown"


def _interleave_decades(rows: list[dict], rng: random.Random) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[decade(row)].append(row)
    for values in groups.values():
        rng.shuffle(values)
    result = []
    keys = sorted(groups)
    while keys:
        next_keys = []
        for key in keys:
            if groups[key]:
                result.append(groups[key].pop())
            if groups[key]:
                next_keys.append(key)
        keys = next_keys
    return result


def _select_type(rows: list[dict], count: int, used: set[str], rng: random.Random) -> list[dict]:
    available = [row for row in rows if row[""] not in used]
    strata: dict[tuple[bool, bool], list[dict]] = defaultdict(list)
    for row in available:
        strata[(bool(VESTING_HINT.search(row["doc_text"])), bool(CITATION_HINT.search(row["doc_text"])))] .append(row)
    quotas = [count // 4 + (1 if index < count % 4 else 0) for index in range(4)]
    chosen = []
    for quota, key in zip(quotas, ((True, True), (True, False), (False, True), (False, False))):
        chosen.extend(_interleave_decades(strata[key], rng)[:quota])
    if len(chosen) < count:
        selected_ids = {row[""] for row in chosen}
        remainder = [row for row in available if row[""] not in selected_ids]
        chosen.extend(_interleave_decades(remainder, rng)[:count - len(chosen)])
    if len(chosen) != count:
        raise ValueError("insufficient documents for benchmark stratum")
    used.update(row[""] for row in chosen)
    return chosen


def _document_record(row: dict[str, str], split: str, order: int) -> dict:
    segments, excluded = build_segments(row["doc_text"], row["doc_type"])
    return {
        "document_id": row[""], "split": split, "display_order": order,
        "url": row["url"], "date": row["date"], "decade": decade(row),
        "president": row["president"], "doc_type": row["doc_type"],
        "preliminary_vesting": bool(VESTING_HINT.search(row["doc_text"])),
        "preliminary_citation": bool(CITATION_HINT.search(row["doc_text"])),
        "segments": [segment.__dict__ for segment in segments],
        "excluded_metadata": excluded,
    }


def build_benchmark(output: Path) -> None:
    rows = read_csv()
    by_type = {kind: [row for row in rows if row["doc_type"] == kind] for kind in DOC_TYPES}
    rng = random.Random(SEED)
    used: set[str] = set()
    selected = []
    for split in ("calibration", "evaluation"):
        for kind in DOC_TYPES:
            selected.extend((split, row) for row in _select_type(by_type[kind], 25, used, rng))
    rng.shuffle(selected)
    documents = [_document_record(row, split, index) for index, (split, row) in enumerate(selected, 1)]
    predictions = [
        {"document_id": doc["document_id"], "citations": regex_citations(
            doc["document_id"], [type("Segment", (), segment) for segment in doc["segments"]]
        ), "unresolved_identity_links": []}
        for doc in documents
    ]
    output.mkdir(parents=True, exist_ok=True)
    write_jsonl(output / "documents.jsonl", documents)
    write_jsonl(output / "regex_predictions.jsonl", predictions)
    manifest = {
        "schema_version": 1, "seed": SEED, "documents": len(documents),
        "split_counts": dict(Counter(doc["split"] for doc in documents)),
        "type_counts": dict(Counter(doc["doc_type"] for doc in documents)),
        "preliminary_strata": {
            f"vesting_{str(vesting).lower()}__citation_{str(citation).lower()}": count
            for (vesting, citation), count in sorted(Counter(
                (doc["preliminary_vesting"], doc["preliminary_citation"]) for doc in documents
            ).items())
        },
        "development_count": len(rows), "development_id_sha256": id_hash(row[""] for row in rows),
        "expected_development_id_sha256": EXPECTED_DEVELOPMENT_HASH,
        "holdout_documents": 0,
    }
    (output / "sample_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (output / "review.html").write_text(review_html(documents, predictions), encoding="utf-8")


def build_corpus(output: Path) -> None:
    """Materialize production inputs; this makes no model calls."""
    rows = read_csv()
    output.mkdir(parents=True, exist_ok=True)
    documents_path = output / "documents.jsonl"
    predictions_path = output / "regex_predictions.jsonl"
    with documents_path.open("w", encoding="utf-8") as documents_handle, predictions_path.open("w", encoding="utf-8") as predictions_handle:
        for index, row in enumerate(rows, 1):
            document = _document_record(row, "production", index)
            documents_handle.write(json.dumps(document, ensure_ascii=False, sort_keys=True) + "\n")
            segments = [type("Segment", (), segment) for segment in document["segments"]]
            prediction = {"document_id": row[""], "citations": regex_citations(row[""], segments), "unresolved_identity_links": []}
            predictions_handle.write(json.dumps(prediction, ensure_ascii=False, sort_keys=True) + "\n")
    manifest = {
        "schema_version": 1, "documents": len(rows), "development_id_sha256": id_hash(row[""] for row in rows),
        "expected_development_id_sha256": EXPECTED_DEVELOPMENT_HASH, "holdout_documents": 0,
        "status": "inputs_only; production method remains gated by locked benchmark",
    }
    (output / "corpus_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def review_html(documents: list[dict], predictions: list[dict]) -> str:
    data = json.dumps({"documents": documents, "predictions": predictions}, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html><meta charset=utf-8><title>In-text citation gold review</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;font:14px/1.45 system-ui;color:#182230;background:#eef2f6}}
header{{position:sticky;top:0;background:#14213d;color:white;padding:12px 20px;z-index:3}}button,select{{font:inherit;padding:6px 10px}}
.layout{{display:grid;grid-template-columns:250px 1fr;max-width:1500px;margin:auto;min-height:100vh}}aside{{background:white;padding:12px;overflow:auto;height:calc(100vh - 58px);position:sticky;top:58px}}
.item{{display:block;width:100%;text-align:left;border:0;background:white;padding:7px;cursor:pointer}}.item.active{{background:#dbeafe}}main{{padding:18px}}
.card{{background:white;border:1px solid #ccd5df;border-radius:8px;padding:14px;margin-bottom:12px}}.segment{{white-space:pre-wrap;padding:9px;border-left:4px solid #94a3b8;margin:8px 0;background:#f8fafc}}.vesting{{border-color:#7c3aed;background:#f5f3ff}}
textarea{{width:100%;min-height:280px;font:12px/1.45 ui-monospace,monospace}}.meta{{color:#526170}}.ok{{color:#166534;font-weight:700}}
</style><header><b>In-text citation benchmark</b> · edit the JSON list, inspect all substantive text, certify, then export
 <select id=filter><option value=all>all</option><option>calibration</option><option>evaluation</option></select>
 <button id=export>Export certified gold JSONL</button> <span id=progress></span></header>
<div class=layout><aside id=list></aside><main><section class=card><h2 id=title></h2><div id=meta class=meta></div></section><section class=card id=text></section>
<section class=card><h3>Unique authority records</h3><p>Correct, add, or delete records. Evidence must be verbatim and identity links must be text-grounded.</p><textarea id=citations></textarea>
<label><input type=checkbox id=certified> I inspected the complete substantive text and this list includes every eligible citation.</label> <button id=save>Save</button> <span id=status></span></section></main></div>
<script>const DATA={data}; const KEY='in-text-citation-gold-v1';let saved=JSON.parse(localStorage.getItem(KEY)||'{{}}'),shown=[],idx=0;
const $=id=>document.getElementById(id), esc=s=>String(s).replace(/[&<>]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c]));
function refreshList(){{let f=$('filter').value;shown=DATA.documents.filter(d=>f==='all'||d.split===f);$('list').innerHTML=shown.map((d,i)=>`<button class="item ${{i===idx?'active':''}}" data-i="${{i}}">${{d.display_order}} · ${{d.doc_type}} · ${{d.document_id}} ${{saved[d.document_id]?.certified?'✓':''}}</button>`).join('');document.querySelectorAll('.item').forEach(b=>b.onclick=()=>{{save();idx=+b.dataset.i;show()}});}}
function show(){{let d=shown[idx];if(!d)return;$('title').textContent=`${{d.display_order}} · ${{d.document_id}}`;$('meta').textContent=`${{d.split}} · ${{d.doc_type}} · ${{d.date}} · ${{d.president}}`;$('text').innerHTML=d.segments.map(s=>`<div class="segment ${{s.region}}"><b>${{esc(s.segment_id)}} · ${{esc(s.region)}} · ${{esc(s.source_type)}}</b><br>${{esc(s.text)}}</div>`).join('');let initial=DATA.predictions.find(x=>x.document_id===d.document_id).citations;$('citations').value=JSON.stringify(saved[d.document_id]?.citations||initial,null,2);$('certified').checked=!!saved[d.document_id]?.certified;$('status').textContent='';refreshList();progress();}}
function save(){{let d=shown[idx];if(!d)return;try{{let citations=JSON.parse($('citations').value);if(!Array.isArray(citations))throw Error('must be a JSON list');saved[d.document_id]={{document_id:d.document_id,citations,unresolved_identity_links:[],certified:$('certified').checked,split:d.split}};localStorage.setItem(KEY,JSON.stringify(saved));$('status').textContent='saved';$('status').className='ok';}}catch(e){{$('status').textContent=e.message;$('status').className='';}}progress();}}
function progress(){{$('progress').textContent=`${{Object.values(saved).filter(x=>x.certified).length}} / 200 certified`;}}
$('filter').onchange=()=>{{save();idx=0;refreshList();show()}};$('save').onclick=()=>{{save();refreshList()}};$('export').onclick=()=>{{save();let rows=DATA.documents.map(d=>saved[d.document_id]).filter(x=>x?.certified);let blob=new Blob([rows.map(x=>JSON.stringify(x)).join('\\n')+'\\n'],{{type:'application/jsonl'}}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='gold.jsonl';a.click();URL.revokeObjectURL(a.href)}};refreshList();show();</script>"""


def build_requests(documents_path: Path, method: str, output: Path, benchmark_score: Path | None = None) -> None:
    if method not in {"terra", "sol"}:
        raise ValueError("method must be terra or sol")
    model = {"terra": "gpt-5.6-terra", "sol": "gpt-5.6-sol"}[method]
    documents = read_jsonl(documents_path)
    if any(document.get("split") == "production" for document in documents):
        if not benchmark_score:
            raise ValueError("production request generation requires --benchmark-score")
        selected = json.loads(benchmark_score.read_text(encoding="utf-8")).get("selected_method")
        if method != selected and not (selected == "hybrid" and method == "terra"):
            raise ValueError(f"{method} is not the benchmark-selected production method")
    rows = []
    for document in documents:
        rows.append({
            "request_id": f"in-text-citations-v1:{method}:{document['document_id']}",
            "document_id": document["document_id"], "model": model,
            "scope": document["split"],
            "reasoning_effort": "medium", "prompt_version": "in-text-citations-v1",
            "segments": [{k: segment[k] for k in ("segment_id", "region", "text")} for segment in document["segments"]],
        })
    write_jsonl(output, rows)


def build_hybrid_requests(documents_path: Path, regex_path: Path, terra_path: Path, output: Path) -> None:
    documents = {row["document_id"]: row for row in read_jsonl(documents_path)}
    regex_rows = {row["document_id"]: row for row in read_jsonl(regex_path)}
    terra_rows = {row["document_id"]: row for row in read_jsonl(terra_path)}
    requests = []
    for document_id, document in documents.items():
        regex_row, terra_row = regex_rows[document_id], terra_rows[document_id]
        if all(entity_set(regex_row["citations"], level) == entity_set(terra_row["citations"], level) for level in ("instrument", "provision")):
            continue
        requests.append({
            "request_id": f"in-text-citations-v1:hybrid:{document_id}",
            "document_id": document_id, "model": "gpt-5.6-sol", "reasoning_effort": "high",
            "prompt_version": "in-text-citations-hybrid-v1",
            "adjudication_instruction": (
                "Compare the supplied regex and Terra candidates, resolve every disagreement, "
                "and independently inspect all segments for citations both systems missed. "
                "Return one complete final citation list."
            ),
            "segments": [{k: segment[k] for k in ("segment_id", "region", "text")} for segment in document["segments"]],
            "candidate_citations": {
                "regex": regex_row["citations"], "terra": terra_row["citations"],
            },
        })
    write_jsonl(output, requests)


def validate_responses(requests_path: Path, responses_path: Path, output: Path, method: str) -> None:
    requests = {row["document_id"]: row for row in read_jsonl(requests_path)}
    validated = []
    seen = set()
    for response in read_jsonl(responses_path):
        document_id = str(response.get("document_id"))
        if document_id in seen or document_id not in requests:
            raise ValueError(f"duplicate or unknown response document: {document_id}")
        validate_citations(response, requests[document_id])
        for citation in response["citations"]:
            citation["document_id"] = document_id
            citation["method"] = method
        validated.append(response)
        seen.add(document_id)
    write_jsonl(output, validated)


def combine_hybrid(regex_path: Path, terra_path: Path, adjudicated_path: Path, output: Path) -> None:
    regex_rows = {row["document_id"]: row for row in read_jsonl(regex_path)}
    terra_rows = {row["document_id"]: row for row in read_jsonl(terra_path)}
    adjudicated = {row["document_id"]: row for row in read_jsonl(adjudicated_path)}
    combined = []
    for document_id, regex_row in regex_rows.items():
        terra_row = terra_rows[document_id]
        disagrees = any(entity_set(regex_row["citations"], level) != entity_set(terra_row["citations"], level) for level in ("instrument", "provision"))
        if disagrees and document_id not in adjudicated:
            raise ValueError(f"missing hybrid adjudication for {document_id}")
        selected = adjudicated.get(document_id, regex_row)
        selected["method"] = "hybrid"
        combined.append(selected)
    write_jsonl(output, combined)


def validate_gold(documents_path: Path, gold_path: Path, output: Path) -> None:
    documents = {row["document_id"]: row for row in read_jsonl(documents_path)}
    gold_rows = read_jsonl(gold_path)
    if len(documents) != 200 or len(gold_rows) != 200:
        raise ValueError("gold validation requires exactly 200 documents and labels")
    if len({row.get("document_id") for row in gold_rows}) != 200:
        raise ValueError("gold labels contain duplicate document IDs")
    validated = []
    for row in gold_rows:
        document_id = str(row.get("document_id"))
        if document_id not in documents or not row.get("certified"):
            raise ValueError(f"uncertified or unknown gold document: {document_id}")
        if row.get("split") != documents[document_id]["split"]:
            raise ValueError(f"gold split mismatch for {document_id}")
        validate_citations(row, documents[document_id])
        validated.append(row)
    if Counter(row["split"] for row in validated) != {"calibration": 100, "evaluation": 100}:
        raise ValueError("gold labels must preserve the 100/100 split")
    write_jsonl(output, validated)


def _metrics(gold: set, predicted: set) -> dict:
    tp, fp, fn = len(gold & predicted), len(predicted - gold), len(gold - predicted)
    precision = tp / (tp + fp) if tp + fp else (1.0 if not gold else 0.0)
    recall = tp / (tp + fn) if tp + fn else 1.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0}


def _scored_entities(citations: list[dict], level: str, region: str | None = None, source_type: str | None = None) -> set[tuple]:
    field = "instrument_keys" if level == "instrument" else "provision_keys"
    return {
        (citation["region"], citation["source_type"], value)
        for citation in citations
        if not citation.get("excluded")
        and (region is None or citation["region"] == region)
        and (source_type is None or citation["source_type"] == source_type)
        for value in citation.get(field, [])
    }


def score(gold_path: Path, predictions: list[str], output: Path) -> None:
    gold_rows = [row for row in read_jsonl(gold_path) if row.get("certified") and row.get("split") == "evaluation"]
    if len(gold_rows) != 100:
        raise ValueError("locked evaluation requires exactly 100 certified gold documents")
    gold = {row["document_id"]: row for row in gold_rows}
    report = {"gold_documents": len(gold), "methods": {}}
    for specification in predictions:
        name, raw_path = specification.split("=", 1)
        rows = {row["document_id"]: row for row in read_jsonl(Path(raw_path))}
        method_report = {}
        for level in ("instrument", "provision"):
            expected, actual = set(), set()
            for document_id, gold_row in gold.items():
                expected |= {(document_id,) + value for value in _scored_entities(gold_row["citations"], level)}
                if document_id not in rows:
                    raise ValueError(f"{name} lacks evaluation document {document_id}")
                actual |= {(document_id,) + value for value in _scored_entities(rows[document_id]["citations"], level)}
            level_report = {"overall": _metrics(expected, actual), "regions": {}, "source_types": {}}
            for region in ("vesting", "body"):
                level_report["regions"][region] = _metrics(
                    {value for value in expected if value[1] == region},
                    {value for value in actual if value[1] == region},
                )
            source_types = sorted({value[2] for value in expected | actual})
            for source_type in source_types:
                level_report["source_types"][source_type] = _metrics(
                    {value for value in expected if value[2] == source_type},
                    {value for value in actual if value[2] == source_type},
                )
            method_report[level] = level_report
        method_report["eligible"] = all(
            method_report[level]["overall"][metric] >= .90
            for level in ("instrument", "provision") for metric in ("precision", "recall")
        )
        report["methods"][name] = method_report
    eligible = [(name, values) for name, values in report["methods"].items() if values["eligible"]]
    if eligible:
        eligible.sort(key=lambda item: (
            min(item[1]["instrument"]["overall"]["recall"], item[1]["provision"]["overall"]["recall"]),
            min(item[1]["instrument"]["overall"]["precision"], item[1]["provision"]["overall"]["precision"]),
            -({"regex": 0, "terra": 1, "sol": 2, "hybrid": 3}.get(item[0], 4)),
        ), reverse=True)
        report["selected_method"] = eligible[0][0]
    else:
        report["selected_method"] = None
        report["production_blocked"] = True
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def summarize(predictions_path: Path, documents_path: Path, output: Path) -> None:
    rows = read_csv()
    metadata = {row[""]: row for row in rows}
    predictions = {row["document_id"]: row for row in read_jsonl(predictions_path)}
    if set(predictions) != set(metadata):
        raise ValueError("production predictions must cover exactly the development corpus")
    output.mkdir(parents=True, exist_ok=True)
    document_rows = []
    aggregate: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for document_id, result in predictions.items():
        meta = metadata[document_id]
        record = {"document_id": document_id, "doc_type": meta["doc_type"], "date": meta["date"],
                  "decade": decade(meta), "president": meta["president"], "url": meta["url"]}
        for level in ("instrument", "provision"):
            entities = entity_set(result["citations"], level)
            vest = {key for region, key in entities if region == "vesting"}
            body = {key for region, key in entities if region == "body"}
            record.update({
                f"{level}_vesting_count": len(vest), f"{level}_body_count": len(body),
                f"{level}_repeated_count": len(vest & body),
                f"{level}_body_only_count": len(body - vest),
                f"{level}_has_repeated": bool(vest & body),
                f"{level}_has_body_only": bool(body - vest),
            })
            for group in ("overall", meta["doc_type"], decade(meta)):
                counter = aggregate[(level, group)]
                counter["documents"] += 1
                counter["documents_with_vesting"] += bool(vest)
                counter["documents_with_body"] += bool(body)
                counter["vesting_documents_with_repeat"] += bool(vest and vest & body)
                counter["vesting_documents_with_body_only"] += bool(vest and body - vest)
                counter["body_documents_with_body_only"] += bool(body and body - vest)
                counter["vesting_source_pairs"] += len(vest)
                counter["repeated_vesting_source_pairs"] += len(vest & body)
                counter["body_source_pairs"] += len(body)
                counter["body_only_source_pairs"] += len(body - vest)
        document_rows.append(record)
    fieldnames = list(document_rows[0])
    with (output / "documents.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader(); writer.writerows(document_rows)
    tables = []
    for (level, group), counts in sorted(aggregate.items()):
        row = {"level": level, "group": group, **counts}
        for numerator, denominator in (
            ("vesting_documents_with_repeat", "documents_with_vesting"),
            ("vesting_documents_with_body_only", "documents_with_vesting"),
            ("body_documents_with_body_only", "documents_with_body"),
            ("repeated_vesting_source_pairs", "vesting_source_pairs"),
            ("body_only_source_pairs", "body_source_pairs"),
        ):
            row[f"{numerator}_pct"] = 100 * counts[numerator] / counts[denominator] if counts[denominator] else 0
        tables.append(row)
    with (output / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(tables[0]))
        writer.writeheader(); writer.writerows(tables)
    overall = [row for row in tables if row["group"] == "overall"]
    lines = ["# Vesting-clause and in-text authority overlap", "", f"Development corpus: {len(rows):,} directives.", ""]
    for row in overall:
        lines.extend([
            f"## {row['level'].title()} level", "",
            f"- Vesting-bearing documents with a repeated body source: {row['vesting_documents_with_repeat']:,} / {row['documents_with_vesting']:,} ({row['vesting_documents_with_repeat_pct']:.2f}%).",
            f"- Vesting-bearing documents with a body-only source: {row['vesting_documents_with_body_only']:,} / {row['documents_with_vesting']:,} ({row['vesting_documents_with_body_only_pct']:.2f}%).",
            f"- Vesting source-document pairs repeated in the body: {row['repeated_vesting_source_pairs']:,} / {row['vesting_source_pairs']:,} ({row['repeated_vesting_source_pairs_pct']:.2f}%).",
            f"- Body source-document pairs absent from the vesting clause: {row['body_only_source_pairs']:,} / {row['body_source_pairs']:,} ({row['body_only_source_pairs_pct']:.2f}%).", "",
        ])
    (output / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    benchmark = sub.add_parser("build-benchmark")
    benchmark.add_argument("--output", type=Path, default=HERE / "outputs" / "benchmark")
    corpus = sub.add_parser("build-corpus")
    corpus.add_argument("--output", type=Path, default=HERE / "outputs" / "corpus")
    requests = sub.add_parser("build-requests")
    requests.add_argument("--documents", type=Path, required=True)
    requests.add_argument("--method", choices=("terra", "sol"), required=True)
    requests.add_argument("--output", type=Path, required=True)
    requests.add_argument("--benchmark-score", type=Path)
    hybrid = sub.add_parser("build-hybrid-requests")
    hybrid.add_argument("--documents", type=Path, required=True); hybrid.add_argument("--regex", type=Path, required=True)
    hybrid.add_argument("--terra", type=Path, required=True); hybrid.add_argument("--output", type=Path, required=True)
    validate = sub.add_parser("validate-responses")
    validate.add_argument("--requests", type=Path, required=True); validate.add_argument("--responses", type=Path, required=True)
    validate.add_argument("--output", type=Path, required=True); validate.add_argument("--method", required=True)
    gold = sub.add_parser("validate-gold")
    gold.add_argument("--documents", type=Path, required=True); gold.add_argument("--gold", type=Path, required=True)
    gold.add_argument("--output", type=Path, required=True)
    combine = sub.add_parser("combine-hybrid")
    combine.add_argument("--regex", type=Path, required=True); combine.add_argument("--terra", type=Path, required=True)
    combine.add_argument("--adjudicated", type=Path, required=True); combine.add_argument("--output", type=Path, required=True)
    scoring = sub.add_parser("score")
    scoring.add_argument("--gold", type=Path, required=True); scoring.add_argument("--prediction", action="append", required=True)
    scoring.add_argument("--output", type=Path, required=True)
    summary = sub.add_parser("summarize")
    summary.add_argument("--predictions", type=Path, required=True); summary.add_argument("--documents", type=Path, required=True)
    summary.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "build-benchmark": build_benchmark(args.output)
    elif args.command == "build-corpus": build_corpus(args.output)
    elif args.command == "build-requests": build_requests(args.documents, args.method, args.output, args.benchmark_score)
    elif args.command == "build-hybrid-requests": build_hybrid_requests(args.documents, args.regex, args.terra, args.output)
    elif args.command == "validate-responses": validate_responses(args.requests, args.responses, args.output, args.method)
    elif args.command == "validate-gold": validate_gold(args.documents, args.gold, args.output)
    elif args.command == "combine-hybrid": combine_hybrid(args.regex, args.terra, args.adjudicated, args.output)
    elif args.command == "score": score(args.gold, args.prediction, args.output)
    elif args.command == "summarize": summarize(args.predictions, args.documents, args.output)


if __name__ == "__main__":
    main()
