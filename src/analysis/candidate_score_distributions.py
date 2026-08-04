"""Summarize Candidate 1 and 2 similarity scores across ranked children."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "data" / "parent_analysis" / "ranked_candidates.csv"
DEFAULT_CHILDREN = ROOT / "data" / "parent_analysis" / "unresolved_children.csv"
DEFAULT_CORPUS = ROOT / "data" / "4_28_2026_build_dev.csv"
DEFAULT_AUTOMATIC_EDGES = ROOT / "data" / "parent_analysis" / "automatic_edges.csv"
DEFAULT_CEREMONIAL_EXCLUSIONS = ROOT / "data" / "parent_analysis" / "ceremonial_exclusions.csv"
DEFAULT_DOCUMENTS = ROOT / "data" / "parent_analysis" / "directive_similarity_documents.jsonl"
DEFAULT_OUTPUT = ROOT / "data" / "parent_analysis" / "candidate_score_distributions"
CANDIDATE_RANKS = (1, 2)
SCORE_FIELDS = {
    "operative_embedding": ("operative_embedding_score", "similarity"),
    "trigram_tfidf": ("segment_word_trigram_tfidf_score", "similarity"),
    "text_reuse": ("segment_text_reuse_words", "reused words"),
}
RAW_FIELDS = {
    "operative_embedding": "operative_embedding_similarity",
    "trigram_tfidf": "trigram_tfidf_similarity",
    "text_reuse": "text_reuse_words",
}


def _score(value: str) -> float | None:
    if value == "":
        return None
    score = float(value)
    if not np.isfinite(score):
        raise ValueError(f"non-finite similarity score: {value}")
    return score


def extract_candidate_scores(
    ranked_rows: Iterable[dict[str, str]], ranks: tuple[int, ...] = CANDIDATE_RANKS,
) -> list[dict]:
    """Extract one wide score row for each requested child-candidate rank."""
    extracted = []
    seen: set[tuple[str, int]] = set()
    for row in ranked_rows:
        candidate_rank = int(row["rrf_rank"])
        if candidate_rank not in ranks:
            continue
        key = (row["child_id"], candidate_rank)
        if key in seen:
            raise ValueError(
                f"duplicate Candidate {candidate_rank} for child {row['child_id']}"
            )
        seen.add(key)
        output = {
            "child_id": row["child_id"],
            "parent_id": row["parent_id"],
            "document_type": row["document_type"],
            "candidate_rank": candidate_rank,
        }
        for channel, (source_field, _unit) in SCORE_FIELDS.items():
            output[RAW_FIELDS[channel]] = _score(row[source_field])
        extracted.append(output)
    return sorted(extracted, key=lambda row: (row["candidate_rank"], row["child_id"]))


def summarize_scores(extracted: list[dict], total_children: int) -> list[dict]:
    """Return descriptive statistics for each candidate rank and score channel."""
    summaries = []
    for candidate_rank in CANDIDATE_RANKS:
        candidates = [row for row in extracted if row["candidate_rank"] == candidate_rank]
        for channel, (_source_field, unit) in SCORE_FIELDS.items():
            field = RAW_FIELDS[channel]
            values = np.asarray(
                [row[field] for row in candidates if row[field] is not None], dtype=float
            )
            count = len(values)
            zero_count = int(np.count_nonzero(values == 0))
            summary = {
                "candidate_rank": candidate_rank,
                "score_channel": channel,
                "unit": unit,
                "total_children": total_children,
                "candidate_count": len(candidates),
                "children_without_candidate": total_children - len(candidates),
                "score_count": count,
                "score_missing_count": len(candidates) - count,
                "zero_count": zero_count,
                "zero_share": zero_count / count if count else "",
            }
            if count:
                quantiles = np.quantile(
                    values, [0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]
                )
                summary.update({
                    "mean": float(np.mean(values)),
                    "std_dev": float(np.std(values, ddof=1)) if count > 1 else 0.0,
                    "min": float(np.min(values)),
                    "p01": float(quantiles[0]),
                    "p05": float(quantiles[1]),
                    "p25": float(quantiles[2]),
                    "p50": float(quantiles[3]),
                    "p75": float(quantiles[4]),
                    "p95": float(quantiles[5]),
                    "p99": float(quantiles[6]),
                    "max": float(np.max(values)),
                })
            else:
                summary.update({
                    field: "" for field in (
                        "mean", "std_dev", "min", "p01", "p05", "p25", "p50",
                        "p75", "p95", "p99", "max",
                    )
                })
            summaries.append(summary)
    return summaries


def _histogram_specs(extracted: list[dict], bins: int = 30) -> list[dict]:
    specs = []
    for channel, (_source_field, unit) in SCORE_FIELDS.items():
        field = RAW_FIELDS[channel]
        combined = [row[field] for row in extracted if row[field] is not None]
        low = min(combined, default=0.0)
        high = (
            float(np.quantile(combined, 0.99))
            if channel == "text_reuse" and combined
            else max(combined, default=1.0)
        )
        if low == high:
            low -= 0.5
            high += 0.5
        edges = np.linspace(low, high, bins + 1)
        for candidate_rank in CANDIDATE_RANKS:
            values = np.asarray([
                row[field] for row in extracted
                if row["candidate_rank"] == candidate_rank and row[field] is not None
            ], dtype=float)
            above_display_range = int(np.count_nonzero(values > high))
            counts, _ = np.histogram(values, bins=edges)
            shares = counts / len(values) if len(values) else counts.astype(float)
            specs.append({
                "title": f"Candidate {candidate_rank}: {channel.replace('_', ' ')}",
                "unit": unit,
                "minimum": low,
                "maximum": high,
                "n": len(values),
                "above_display_range": above_display_range,
                "shares": shares.tolist(),
            })
    return specs


def build_threshold_samples(
    extracted: list[dict], documents: dict[str, dict], sample_size: int = 12,
) -> list[dict]:
    """Build reproducible pair samples for operative-embedding score bands."""
    bands = (
        ("above_09", "At least .9", 0.9, float("inf")),
        ("08_to_09", ".8 to under .9", 0.8, 0.9),
        ("07_to_08", ".7 to under .8", 0.7, 0.8),
    )
    output = []
    for band_id, label, low, high in bands:
        eligible = [
            row for row in extracted
            if row["operative_embedding_similarity"] is not None
            and low <= row["operative_embedding_similarity"] < high
        ]
        eligible.sort(key=lambda row: hashlib.sha256(
            f"{band_id}:{row['child_id']}:{row['parent_id']}:{row['candidate_rank']}".encode()
        ).hexdigest())
        pairs = []
        for row in eligible[:sample_size]:
            child = documents[row["child_id"]]
            parent = documents[row["parent_id"]]
            pairs.append({
                "candidate_rank": row["candidate_rank"],
                "score": row["operative_embedding_similarity"],
                "child": {key: child[key] for key in ("document_id", "title", "date", "url")},
                "parent": {key: parent[key] for key in ("document_id", "title", "date", "url")},
                "child_excerpt": child["cleaned_masked_text"][:900],
                "parent_excerpt": parent["cleaned_masked_text"][:900],
            })
        type_counts = Counter(row["document_type"] for row in eligible)
        output.append({
            "id": band_id,
            "label": label,
            "total": len(eligible),
            "type_counts": dict(sorted(type_counts.items())),
            "pairs": pairs,
        })
    return output


def build_plot_html(
    extracted: list[dict], population: dict | None = None, threshold_samples: list[dict] | None = None,
) -> str:
    """Build a dependency-free six-panel histogram report."""
    data = json.dumps(_histogram_specs(extracted), separators=(",", ":")).replace(
        "</", "<\\/"
    )
    sample_data = json.dumps(threshold_samples or [], separators=(",", ":")).replace("</", "<\\/")
    if population:
        population_note = f"""
<section class="population">
<h2>How the source corpus becomes the reported n</h2>
<p>Source document IDs run as high as <strong>{population['maximum_document_id']:,}</strong>,
but IDs are not contiguous. This analysis starts from the
<strong>{population['corpus_documents']:,}-document development corpus</strong>—the main
analysis split used to construct and rank parent candidates. The separately reserved
holdout split is not used in this ranking. The codebook-based ceremonial filter excludes
<strong>{population['ceremonial_exclusions']:,}</strong> directives, leaving
<strong>{population['analyzed_directives']:,}</strong> directives eligible to appear as
children or parents. Automatic reference matching identifies parents for
<strong>{population['automatic_parent_children']:,}</strong> children, leaving
<strong>{population['unresolved_children']:,}</strong> unresolved children for candidate
ranking. Candidate 1 exists for <strong>{population['candidate_1_children']:,}</strong>
children and Candidate 2 for <strong>{population['candidate_2_children']:,}</strong>.
Each chart's <em>n</em> is the number of those candidate rows with a non-missing score in
that channel, so it can be smaller again.</p>
</section>"""
    else:
        population_note = ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Candidate 1–2 similarity score distributions</title>
<style>
body{{margin:24px;font:14px system-ui,sans-serif;color:#172033;background:#f4f7fb}}
h1{{margin-bottom:4px}}p{{color:#667085}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(360px,1fr));gap:16px}}
.panel,.population{{background:#fff;border:1px solid #d8dee9;border-radius:8px;padding:12px}}.population{{margin:16px 0}}h2{{font-size:15px;margin:0 0 6px}}
.tabs{{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}}.tab{{border:1px solid #98a2b3;background:#fff;border-radius:6px;padding:8px 12px;cursor:pointer}}.tab.active{{background:#225ea8;color:#fff;border-color:#225ea8}}
.tab-view[hidden]{{display:none}}.pairs{{display:grid;gap:16px}}.pair{{background:#fff;border:1px solid #d8dee9;border-radius:8px;padding:14px}}.pair-meta{{color:#475467;margin:0 0 10px}}.documents{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}.document{{border-left:3px solid #84b4d8;padding-left:10px}}.document h3{{font-size:14px;margin:0 0 4px}}.document p{{white-space:pre-wrap;line-height:1.45}}a{{color:#225ea8}}
.type-counts{{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 18px}}.type-count{{background:#e8f1f8;border-radius:999px;padding:6px 10px;color:#344054}}
.metric-guide{{background:#fff;border:1px solid #d8dee9;border-radius:8px;padding:12px;margin:16px 0}}.metric-guide li{{margin:6px 0;color:#475467}}
canvas{{display:block;width:100%;height:240px}}@media(max-width:850px){{.grid{{grid-template-columns:1fr}}}}
@media(max-width:700px){{.documents{{grid-template-columns:1fr}}}}
</style></head><body>
<h1>Candidate 1–2 similarity score distributions</h1>
<p>Thirty equal-width bins use shared limits for Candidate 1 and 2 within each channel. Bar heights are shares of non-missing scores.</p>
{population_note}
<section class="metric-guide"><h2>How to read these metrics</h2><ul>
<li><strong>Operative embedding similarity:</strong> semantic similarity between the strongest aligned operative segments.</li>
<li><strong>Word-trigram TF-IDF similarity:</strong> overlap in distinctive case-sensitive three-word sequences.</li>
<li><strong>Text reuse:</strong> average reused-word count among the strongest aligned segment pairs.</li>
<li><strong>Why Candidate 2 can have a smaller n:</strong> the earliest directives of each type may have fewer than two eligible earlier parents, and directives without operative segments have missing channel scores.</li>
</ul></section>
<nav class="tabs" id="tabs"><button class="tab active" data-view="distributions">Distributions</button></nav>
<section class="tab-view" id="distributions"><div class="grid" id="grid"></div></section>
<div id="sample-views"></div>
<script>
const DATA={data},SAMPLES={sample_data},grid=document.getElementById('grid');
const fmt=x=>Math.abs(x)>=100?x.toFixed(0):x.toFixed(3);
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
DATA.forEach((d,i)=>{{
 const panel=document.createElement('section');panel.className='panel';
 panel.innerHTML='<h2>'+d.title+'</h2><canvas width="600" height="240"></canvas><p>n = '+d.n.toLocaleString()+' · '+d.unit+(d.above_display_range?' · '+d.above_display_range.toLocaleString()+' above display range':'')+'</p>';grid.appendChild(panel);
 const c=panel.querySelector('canvas'),x=c.getContext('2d'),left=48,right=12,top=12,bottom=35,w=c.width-left-right,h=c.height-top-bottom;
 x.strokeStyle='#98a2b3';x.beginPath();x.moveTo(left,top);x.lineTo(left,top+h);x.lineTo(left+w,top+h);x.stroke();
 const peak=Math.max(...d.shares,0.01),bw=w/d.shares.length;x.fillStyle='#225ea8';
 d.shares.forEach((v,j)=>{{const bh=h*v/peak;x.fillRect(left+j*bw,top+h-bh,Math.max(1,bw-1),bh)}});
 x.fillStyle='#475467';x.font='12px system-ui';x.textAlign='left';x.fillText(fmt(d.minimum),left,top+h+18);
 x.textAlign='right';x.fillText(fmt(d.maximum),left+w,top+h+18);x.fillText((peak*100).toFixed(1)+'%',left-5,top+5);
}});
const tabs=document.getElementById('tabs'),views=document.getElementById('sample-views');
SAMPLES.forEach(b=>{{
 const button=document.createElement('button');button.className='tab';button.dataset.view=b.id;button.textContent=b.label;tabs.appendChild(button);
 const section=document.createElement('section');section.className='tab-view';section.id=b.id;section.hidden=true;
 const counts=Object.entries(b.type_counts).map(x=>'<span class="type-count">'+esc(x[0].split('_').join(' '))+': <strong>'+x[1].toLocaleString()+'</strong></span>').join('');
 section.innerHTML='<h2>Operative embedding: '+esc(b.label)+'</h2><p><strong>'+b.total.toLocaleString()+'</strong> Candidate 1–2 pairs are in this band, broken down by directive type:</p><div class="type-counts">'+counts+'</div><p>Showing a deterministic sample of '+b.pairs.length+' pairs.</p><div class="pairs">'+b.pairs.map((p,i)=>'<article class="pair"><p class="pair-meta"><strong>Pair '+(i+1)+'</strong> · Candidate '+p.candidate_rank+' · score <strong>'+p.score.toFixed(3)+'</strong></p><div class="documents">'+[['Child',p.child,p.child_excerpt],['Parent',p.parent,p.parent_excerpt]].map(x=>'<section class="document"><h3>'+x[0]+': <a href="'+esc(x[1].url)+'" target="_blank" rel="noopener">'+esc(x[1].title)+'</a></h3><small>'+esc(x[1].date)+' · ID '+esc(x[1].document_id)+'</small><p>'+esc(x[2])+(x[2].length===900?'…':'')+'</p></section>').join('')+'</div></article>').join('')+'</div>';
 views.appendChild(section);
}});
tabs.addEventListener('click',event=>{{const button=event.target.closest('button');if(!button)return;document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x===button));document.querySelectorAll('.tab-view').forEach(x=>x.hidden=x.id!==button.dataset.view);}});
</script></body></html>"""


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_analysis(
    ranked_path: Path,
    children_path: Path,
    output_dir: Path,
    corpus_path: Path | None = None,
    automatic_edges_path: Path | None = None,
    documents_path: Path | None = None,
    ceremonial_exclusions_path: Path | None = None,
) -> dict[str, Path]:
    with ranked_path.open(newline="", encoding="utf-8") as handle:
        extracted = extract_candidate_scores(csv.DictReader(handle))
    with children_path.open(newline="", encoding="utf-8") as handle:
        child_ids = {row["document_id"] for row in csv.DictReader(handle)}
    population = None
    if corpus_path is not None and automatic_edges_path is not None:
        with corpus_path.open(newline="", encoding="utf-8") as handle:
            corpus_rows = list(csv.DictReader(handle))
        with automatic_edges_path.open(newline="", encoding="utf-8") as handle:
            automatic_children = {row["child_id"] for row in csv.DictReader(handle)}
        ceremonial_count = 0
        if ceremonial_exclusions_path is not None:
            with ceremonial_exclusions_path.open(newline="", encoding="utf-8") as handle:
                ceremonial_count = sum(1 for _row in csv.DictReader(handle))
        candidate_counts = {
            rank: len({row["child_id"] for row in extracted if row["candidate_rank"] == rank})
            for rank in CANDIDATE_RANKS
        }
        population = {
            "corpus_documents": len(corpus_rows),
            "maximum_document_id": max(int(row[""]) for row in corpus_rows),
            "ceremonial_exclusions": ceremonial_count,
            "analyzed_directives": len(corpus_rows) - ceremonial_count,
            "automatic_parent_children": len(automatic_children),
            "unresolved_children": len(child_ids),
            "candidate_1_children": candidate_counts[1],
            "candidate_2_children": candidate_counts[2],
        }
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "candidate_1_2_scores.csv"
    summary_path = output_dir / "candidate_1_2_score_summary.csv"
    plot_path = output_dir / "candidate_1_2_score_distributions.html"
    _write_csv(raw_path, extracted)
    _write_csv(summary_path, summarize_scores(extracted, len(child_ids)))
    threshold_samples = None
    if documents_path is not None:
        with documents_path.open(encoding="utf-8") as handle:
            documents = {row["document_id"]: row for row in map(json.loads, handle)}
        threshold_samples = build_threshold_samples(extracted, documents)
    plot_path.write_text(build_plot_html(extracted, population, threshold_samples), encoding="utf-8")
    return {"scores": raw_path, "summary": summary_path, "plots": plot_path}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ranked-candidates", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--children", type=Path, default=DEFAULT_CHILDREN)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--automatic-edges", type=Path, default=DEFAULT_AUTOMATIC_EDGES)
    parser.add_argument("--documents", type=Path, default=DEFAULT_DOCUMENTS)
    parser.add_argument(
        "--ceremonial-exclusions", type=Path, default=DEFAULT_CEREMONIAL_EXCLUSIONS
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    outputs = write_analysis(
        args.ranked_candidates,
        args.children,
        args.output_dir,
        args.corpus,
        args.automatic_edges,
        args.documents,
        args.ceremonial_exclusions,
    )
    for label, path in outputs.items():
        print(f"{label}: {path}")


if __name__ == "__main__":
    main()
