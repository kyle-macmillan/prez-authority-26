"""Summarize Candidate 1 and 2 similarity scores across ranked children."""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Iterable
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "data" / "parent_analysis" / "ranked_candidates.csv"
DEFAULT_CHILDREN = ROOT / "data" / "parent_analysis" / "unresolved_children.csv"
DEFAULT_OUTPUT = ROOT / "data" / "parent_analysis" / "candidate_score_distributions"
CANDIDATE_RANKS = (1, 2)
TEXT_REUSE_DISPLAY_QUANTILE = 0.99
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
        high = max(combined, default=1.0)
        if channel == "text_reuse" and combined:
            high = float(np.quantile(combined, TEXT_REUSE_DISPLAY_QUANTILE))
        if low == high:
            low -= 0.5
            high += 0.5
        edges = np.linspace(low, high, bins + 1)
        for candidate_rank in CANDIDATE_RANKS:
            values = np.asarray([
                row[field] for row in extracted
                if row["candidate_rank"] == candidate_rank and row[field] is not None
            ], dtype=float)
            counts, _ = np.histogram(values, bins=edges)
            shares = counts / len(values) if len(values) else counts.astype(float)
            specs.append({
                "title": f"Candidate {candidate_rank}: {channel.replace('_', ' ')}",
                "unit": unit,
                "minimum": low,
                "maximum": high,
                "n": len(values),
                "above_display_range": int(np.count_nonzero(values > high)),
                "shares": shares.tolist(),
            })
    return specs


def build_plot_html(extracted: list[dict]) -> str:
    """Build a dependency-free six-panel histogram report."""
    data = json.dumps(_histogram_specs(extracted), separators=(",", ":")).replace(
        "</", "<\\/"
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Candidate 1–2 similarity score distributions</title>
<style>
body{{margin:24px;font:14px system-ui,sans-serif;color:#172033;background:#f4f7fb}}
h1{{margin-bottom:4px}}p{{color:#667085}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(360px,1fr));gap:16px}}
.panel{{background:#fff;border:1px solid #d8dee9;border-radius:8px;padding:12px}}h2{{font-size:15px;margin:0 0 6px}}
.note{{margin-top:16px;background:#fff;border:1px solid #d8dee9;border-radius:8px;padding:12px}}
.note h2{{margin:0 0 6px}}.note h3{{font-size:14px;margin:12px 0 4px}}.note p{{margin:0;line-height:1.5}}
canvas{{display:block;width:100%;height:240px}}@media(max-width:850px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body>
<h1>Candidate 1–2 similarity score distributions</h1>
<p>Thirty equal-width bins use shared limits for Candidate 1 and 2 within each channel. Bar heights are shares of non-missing scores. Text reuse stops at the combined 99th percentile; the upper 1% remains in the CSVs and summary statistics.</p>
<div class="grid" id="grid"></div>
<section class="note">
<h2>How to read these metrics</h2>
<p><strong>Candidate 1</strong> and <strong>Candidate 2</strong> are the first- and second-ranked earlier documents of the same directive type. Their final order comes from unweighted reciprocal rank fusion (<code>k = 20</code>) of the three metrics below. Full-document embeddings select the initial pool of up to 25 candidates but do not enter the final fusion directly.</p>
<h3>Operative embedding similarity</h3><p>Semantic similarity between the child and candidate parent’s operative segments. The score is the mean of the three highest pairwise dot products between normalized segment embeddings, so it behaves like cosine similarity. Higher values mean the documents’ directed actions are more similar in meaning.</p>
<h3>Word-trigram TF-IDF similarity</h3><p>Wording similarity between operative segments based on case-sensitive sequences of three consecutive words. Each segment is represented by a TF-IDF vector, pairwise similarity is the vector dot product (cosine similarity after the vectors’ default normalization), and the score is the mean of the three strongest segment pairs. Higher values mean more similar local phrasing.</p>
<h3>Text reuse</h3><p>Exact verbal overlap between operative segments. A reused passage must contain at least 10 consecutive, case-sensitive word tokens; overlapping matches are merged and counted as reused words. The document-pair score is the mean reused-word count across the three strongest segment pairs. Higher values mean more verbatim reuse.</p>
<h2>Why this report starts with 16,397 rather than 20,232 directives</h2><p>The 20,232 figure is the current full corpus: 18,211 development documents plus 2,021 documents reserved as a holdout during rule development. This candidate report was generated from an earlier 16,397-document development snapshot. Thus, 20,232 minus the 2,021-document holdout gives 18,211, and the remaining difference of 1,814 reflects documents added to the development corpus after this parent-analysis snapshot was built. Those 1,814 documents were not removed by a parent-analysis rule; they are a corpus-version difference. By type, the later development corpus added 411 executive orders, 304 memoranda, 738 proclamations, and 361 letters.</p>
<h2>Why Candidate 2 has n = 11,716</h2><p>This report uses the 16,397-directive corpus build. Removing 2,102 children with an automatic same-type parent left 14,295 unresolved children. Eight of those children—the two earliest in each of the four directive types—had no eligible earlier same-type Candidate 2, leaving 14,287 Candidate 2 pairs. Another 2,571 pairs lacked a segment-level score because the child or candidate parent had no operative segment, leaving 11,716 non-missing scores in each Candidate 2 histogram.</p>
</section>
<script>
const DATA={data},grid=document.getElementById('grid');
const fmt=x=>Math.abs(x)>=100?x.toFixed(0):x.toFixed(3);
DATA.forEach((d,i)=>{{
 const panel=document.createElement('section');panel.className='panel';
 const omitted=d.above_display_range?' · '+d.above_display_range.toLocaleString()+' above display range':'';
 panel.innerHTML='<h2>'+d.title+'</h2><canvas width="600" height="240"></canvas><p>n = '+d.n.toLocaleString()+' · '+d.unit+omitted+'</p>';grid.appendChild(panel);
 const c=panel.querySelector('canvas'),x=c.getContext('2d'),left=48,right=12,top=12,bottom=35,w=c.width-left-right,h=c.height-top-bottom;
 x.strokeStyle='#98a2b3';x.beginPath();x.moveTo(left,top);x.lineTo(left,top+h);x.lineTo(left+w,top+h);x.stroke();
 const peak=Math.max(...d.shares,0.01),bw=w/d.shares.length;x.fillStyle='#225ea8';
 d.shares.forEach((v,j)=>{{const bh=h*v/peak;x.fillRect(left+j*bw,top+h-bh,Math.max(1,bw-1),bh)}});
 x.fillStyle='#475467';x.font='12px system-ui';x.textAlign='left';x.fillText(fmt(d.minimum),left,top+h+18);
 x.textAlign='right';x.fillText(fmt(d.maximum),left+w,top+h+18);x.fillText((peak*100).toFixed(1)+'%',left-5,top+5);
}});
</script></body></html>"""


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_analysis(ranked_path: Path, children_path: Path, output_dir: Path) -> dict[str, Path]:
    with ranked_path.open(newline="", encoding="utf-8") as handle:
        extracted = extract_candidate_scores(csv.DictReader(handle))
    with children_path.open(newline="", encoding="utf-8") as handle:
        child_ids = {row["document_id"] for row in csv.DictReader(handle)}
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "candidate_1_2_scores.csv"
    summary_path = output_dir / "candidate_1_2_score_summary.csv"
    plot_path = output_dir / "candidate_1_2_score_distributions.html"
    _write_csv(raw_path, extracted)
    _write_csv(summary_path, summarize_scores(extracted, len(child_ids)))
    plot_path.write_text(build_plot_html(extracted), encoding="utf-8")
    return {"scores": raw_path, "summary": summary_path, "plots": plot_path}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ranked-candidates", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--children", type=Path, default=DEFAULT_CHILDREN)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    outputs = write_analysis(args.ranked_candidates, args.children, args.output_dir)
    for label, path in outputs.items():
        print(f"{label}: {path}")


if __name__ == "__main__":
    main()
