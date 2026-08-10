"""Report topical coverage and embedding similarities of Qwen top-1 parents."""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOPICS = {
    "IEEPA": re.compile(r"\bIEEPA\b|International Emergency Economic Powers Act", re.I),
    "National Emergencies Act": re.compile(r"National Emergencies Act", re.I),
}
VARIANTS = {
    "full": ("qwen_full_operative_rank", "qwen_full_operative_score", "Full-operative Qwen"),
    "matched": ("qwen_matched_pairs_rank", "qwen_matched_pairs_score", "Matched-pairs Qwen"),
}
QUANTILES = (0, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 1)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def load_corpus(root: Path) -> dict[str, dict[str, str]]:
    corpus = {}
    for path in (root / "data/4_28_2026_build_dev.csv", root / "data/4_28_2026_build_holdout.csv"):
        for row in read_csv(path):
            corpus[row[""]] = row
    return corpus


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("cannot calculate a percentile for an empty set")
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def quantile_summary(values: list[float]) -> dict[str, float]:
    return {str(int(fraction * 100)): percentile(values, fraction) for fraction in QUANTILES}


def top_rows_by_variant(rows: list[dict[str, str]]) -> dict[str, dict[str, dict[str, str]]]:
    by_child: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_child[row["child_id"]].append(row)
    output = {variant: {} for variant in VARIANTS}
    for child_id, candidates in by_child.items():
        for variant, (rank_field, _, _) in VARIANTS.items():
            output[variant][child_id] = min(candidates, key=lambda row: int(row[rank_field]))
    return output


def similarity_distribution(rows: list[dict[str, str]]) -> dict[str, dict[str, float]]:
    return {
        "document_embedding_similarity": quantile_summary(
            [float(row["document_embedding_score"]) for row in rows]
        ),
        "operative_embedding_similarity": quantile_summary(
            [float(row["operative_embedding_score"]) for row in rows]
        ),
    }


def histogram(values: list[float], bins: int = 20) -> list[dict[str, float | int]]:
    minimum, maximum = min(values), max(values)
    if minimum == maximum:
        return [{"low": minimum, "high": maximum, "count": len(values)}]
    width = (maximum - minimum) / bins
    counts = [0] * bins
    for value in values:
        index = min(int((value - minimum) / width), bins - 1)
        counts[index] += 1
    return [
        {"low": minimum + index * width, "high": minimum + (index + 1) * width, "count": count}
        for index, count in enumerate(counts)
    ]


def build_analysis(root: Path = ROOT, sample_limit: int = 10) -> dict:
    corpus = load_corpus(root)
    documents = {row["document_id"]: row for row in read_jsonl(root / "data/parent_analysis/directive_similarity_documents.jsonl")}
    qwen_path = root / "data/parent_analysis/qwen_pilot_100.csv"
    if not qwen_path.is_file():
        qwen_path = root / "data/parent_analysis/qwen_reranked_candidates.csv"
    qwen_rows = read_csv(qwen_path)
    top_rows = top_rows_by_variant(qwen_rows)
    qwen_children = set(top_rows["full"])
    analyzed = set(documents)
    automatic = {row["child_id"] for row in read_csv(root / "data/parent_analysis/automatic_edges.csv")}

    result = {
        "total_qwen_children": len(qwen_children),
        "total_candidate_pairs": len(qwen_rows),
        "topics": {},
        "types": {},
    }

    for document_type in sorted({row["document_type"] for row in qwen_rows}):
        result["types"][document_type] = {}
        for variant, (_, _, label) in VARIANTS.items():
            selected = [row for row in top_rows[variant].values()
                        if row["document_type"] == document_type]
            result["types"][document_type][variant] = {
                "label": label,
                "count": len(selected),
                "similarity": similarity_distribution(selected),
                "histograms": {
                    "document_embedding_similarity": histogram(
                        [float(row["document_embedding_score"]) for row in selected]
                    ),
                    "operative_embedding_similarity": histogram(
                        [float(row["operative_embedding_score"]) for row in selected]
                    ),
                },
            }
    for topic, matcher in TOPICS.items():
        topic_ids = {document_id for document_id, row in corpus.items() if matcher.search(row["doc_text"])}
        statuses = Counter()
        for document_id in topic_ids:
            if document_id in automatic:
                statuses["automatic_parent"] += 1
            elif document_id in qwen_children:
                statuses["qwen_scored"] += 1
            elif document_id in analyzed:
                statuses["analyzed_without_qwen"] += 1
            else:
                statuses["not_analyzed"] += 1

        topic_result = {
            "total": len(topic_ids),
            "statuses": dict(statuses),
            "variants": {},
        }
        for variant, (_, score_field, label) in VARIANTS.items():
            selected = [top_rows[variant][document_id] for document_id in sorted(topic_ids & qwen_children, key=int)]
            same_topic = [row for row in selected if row["parent_id"] in topic_ids]
            nonmatches = [row for row in selected if row["parent_id"] not in topic_ids]
            topic_result["variants"][variant] = {
                "label": label,
                "qwen_scored": len(selected),
                "same_topic": len(same_topic),
                "nonmatching": len(nonmatches),
                "similarity": similarity_distribution(selected),
                "histograms": {
                    "document_embedding_similarity": histogram([float(row["document_embedding_score"]) for row in selected]),
                    "operative_embedding_similarity": histogram([float(row["operative_embedding_score"]) for row in selected]),
                },
                "nonmatch_examples": [
                    {
                        "child_id": row["child_id"],
                        "child": {key: documents[row["child_id"]].get(key, "") for key in ("title", "date", "url")},
                        "parent_id": row["parent_id"],
                        "parent": {key: documents[row["parent_id"]].get(key, "") for key in ("title", "date", "url")},
                        "qwen_score": float(row[score_field]),
                        "document_embedding_similarity": float(row["document_embedding_score"]),
                        "operative_embedding_similarity": float(row["operative_embedding_score"]),
                    }
                    for row in nonmatches[:sample_limit]
                ],
            }
        result["topics"][topic] = topic_result

    all_rows_by_variant = {}
    for variant, (_, _, label) in VARIANTS.items():
        selected = list(top_rows[variant].values())
        all_rows_by_variant[variant] = {
            "label": label,
            "similarity": similarity_distribution(selected),
            "histograms": {
                "document_embedding_similarity": histogram([float(row["document_embedding_score"]) for row in selected]),
                "operative_embedding_similarity": histogram([float(row["operative_embedding_score"]) for row in selected]),
            },
        }
    result["all_qwen_evaluated"] = all_rows_by_variant
    return result


def fmt(value: float) -> str:
    return f"{value:.3f}"


def quantile_table(distribution: dict[str, dict[str, float]]) -> str:
    labels = [("0", "Min"), ("10", "P10"), ("25", "P25"), ("50", "Median"),
              ("75", "P75"), ("90", "P90"), ("95", "P95"), ("100", "Max")]
    rows = []
    for metric, values in distribution.items():
        rows.append("<tr><th>{}</th>{}</tr>".format(
            html.escape(metric.replace("_", " ").title()),
            "".join(f"<td>{fmt(values[key])}</td>" for key, _ in labels),
        ))
    header = "<tr><th>Metric</th>{}</tr>".format("".join(f"<th>{label}</th>" for _, label in labels))
    return f"<table><thead>{header}</thead><tbody>{''.join(rows)}</tbody></table>"


def render_histogram(histograms: dict[str, list[dict]]) -> str:
    blocks = []
    for metric, bins in histograms.items():
        peak = max(item["count"] for item in bins) or 1
        minimum = bins[0]["low"]
        maximum = bins[-1]["high"]
        x_ticks = [minimum + (maximum - minimum) * fraction / 4 for fraction in range(5)]
        bars = "".join(
            f'<span title="{item["low"]:.3f}–{item["high"]:.3f}: {item["count"]}" '
            f'style="height:{max(1, 100 * item["count"] / peak):.1f}%"></span>'
            for item in bins
        )
        blocks.append(
            f'<div class="hist"><h4>{html.escape(metric.replace("_", " ").title())}</h4>'
            f'<div class="plot"><div class="y-title">Count</div><div class="y-axis">'
            f'<span>{peak:,}</span><span>{peak / 2:g}</span><span>0</span></div>'
            f'<div class="plot-body"><div class="bars">{bars}</div><div class="x-axis">'
            f'{"".join(f"<span>{tick:.3f}</span>" for tick in x_ticks)}</div>'
            f'<div class="x-title">Cosine similarity</div></div></div></div>'
        )
    return "".join(blocks)


def build_html(result: dict) -> str:
    sections = []
    for topic, data in result["topics"].items():
        status = ", ".join(f"{key.replace('_', ' ')}: {value}" for key, value in data["statuses"].items())
        variants = []
        for variant, detail in data["variants"].items():
            examples = []
            for example in detail["nonmatch_examples"]:
                examples.append(
                    f'<li><a href="{html.escape(example["child"]["url"])}">{html.escape(example["child"]["title"])}</a> '
                    f'(ID {example["child_id"]}) → <a href="{html.escape(example["parent"]["url"])}">'
                    f'{html.escape(example["parent"]["title"])}</a> (ID {example["parent_id"]}); '
                    f'Qwen {example["qwen_score"]:.3f}, document {example["document_embedding_similarity"]:.3f}, '
                    f'operative {example["operative_embedding_similarity"]:.3f}</li>'
                )
            variants.append(
                f'<h3>{html.escape(detail["label"])}</h3>'
                f'<p>{detail["same_topic"]}/{detail["qwen_scored"]} same-topic top-1; '
                f'{detail["nonmatching"]} non-matches.</p>'
                f'{quantile_table(detail["similarity"])}{render_histogram(detail["histograms"])}'
                f'<h4>Non-matching examples</h4><ol>{"".join(examples)}</ol>'
            )
        sections.append(f'<section><h2>{html.escape(topic)}</h2><p>{html.escape(status)}</p>{"".join(variants)}</section>')

    def render_variants(variants: dict, include_count: bool = False) -> str:
        rendered = []
        for detail in variants.values():
            count = f'<p>{detail["count"]:,} Qwen-evaluated children.</p>' if include_count else ""
            rendered.append(
                f'<h3>{html.escape(detail["label"])}</h3>{count}'
                f'{quantile_table(detail["similarity"])}{render_histogram(detail["histograms"])}'
            )
        return "".join(rendered)

    all_sections = render_variants(result["all_qwen_evaluated"])
    type_tabs = []
    type_buttons = []
    for index, (document_type, variants) in enumerate(result["types"].items()):
        panel_id = f"type-{index}"
        label = document_type.replace("_", " ").title()
        type_buttons.append(f'<button class="tab" data-panel="{panel_id}">{html.escape(label)}</button>')
        type_tabs.append(
            f'<section class="tab-panel" id="{panel_id}" hidden><h2>{html.escape(label)}</h2>'
            f'{render_variants(variants, include_count=True)}</section>'
        )
    type_counts = ", ".join(
        f'{next(iter(variants.values()))["count"]:,} {document_type.replace("_", " ")} children'
        for document_type, variants in result["types"].items()
    )
    return f'''<!doctype html><html><head><meta charset="utf-8"><title>Qwen topical coverage and similarity</title>
<style>body{{font:15px system-ui;line-height:1.45;color:#172033;background:#f5f7fa;margin:0}}main{{max-width:1400px;margin:auto;padding:28px}}section,.card{{background:#fff;border:1px solid #d8e1eb;border-radius:9px;padding:18px;margin:18px 0}}table{{border-collapse:collapse;width:100%;margin:10px 0 18px}}th,td{{border:1px solid #d8e1eb;padding:7px;text-align:right}}th:first-child,td:first-child{{text-align:left}}th{{background:#eef3f8}}.hist{{display:inline-block;width:48%;min-width:390px;vertical-align:top;margin-right:1%}}.plot{{display:grid;grid-template-columns:18px 44px 1fr;align-items:stretch}}.y-title{{writing-mode:vertical-rl;transform:rotate(180deg);text-align:center;font-size:12px;color:#52606d}}.y-axis{{height:138px;display:flex;flex-direction:column;justify-content:space-between;align-items:flex-end;padding-right:6px;font-size:11px;color:#52606d}}.plot-body{{min-width:0}}.bars{{height:130px;display:flex;align-items:flex-end;gap:2px;border-left:1px solid #52606d;border-bottom:1px solid #52606d;padding:4px;background:linear-gradient(to bottom,transparent 49.5%,#d8e1eb 50%,transparent 50.5%)}}.bars span{{display:block;flex:1;background:#3b82c4;min-width:2px}}.x-axis{{display:flex;justify-content:space-between;font-size:11px;color:#52606d}}.x-axis span{{position:relative;padding-top:5px;transform:translateX(-50%)}}.x-axis span:first-child{{transform:none}}.x-axis span:last-child{{transform:none}}.x-axis span:before{{content:"";position:absolute;top:0;left:50%;height:4px;border-left:1px solid #52606d}}.x-title{{text-align:center;font-size:12px;color:#52606d;margin-top:2px}}li{{margin:6px 0}}a{{color:#075985}}small{{color:#52606d}}.tabs{{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}}.tabs button{{border:1px solid #9fb3c8;background:#fff;border-radius:6px;padding:8px 12px;cursor:pointer}}.tabs button.active{{background:#075985;color:#fff}}</style></head><body><main>
<h1>Qwen topical coverage and similarity</h1><p>Qwen reranks the RRF top-ten candidate set. Similarity values are cosine similarities; higher values indicate greater similarity. Operative similarity is the bidirectional best-segment aggregate.</p>
<div class="card"><strong>{result["total_qwen_children"]:,}</strong> Qwen-evaluated children</div>
<section><h2>Which directives are analyzed?</h2>
<p>This report analyzes the 100-child Qwen pilot: {html.escape(type_counts)}. These are later directives without an automatically resolved parent for which the retrieval pipeline produced at least one eligible candidate. The current pilot contains no proclamation or letter children, so those directive types do not have distributions here.</p>
<p>For each child, candidates are earlier directives of the same directive type. The retrieval system first ranks up to 25 candidates using document and operative-provision similarity, three-word-sequence overlap, and text reuse; Qwen then reranks the fused top ten. The pilot contains {result["total_candidate_pairs"]:,} child–candidate comparisons (one child has only nine eligible earlier candidates).</p>
<p>Each distribution below contains one selected parent per child: Qwen's top-ranked candidate under either the full-operative or matched-pairs representation. The plotted values are the document and operative embedding similarities for those selected pairs, not the Qwen reranker score itself. The IEEPA and National Emergencies Act sections are subsets identified by mentions in the child directive text.</p>
</section>
<nav class="tabs" aria-label="Directive type"><button class="tab active" data-panel="overall">Overall</button>{"".join(type_buttons)}</nav>
<section class="tab-panel" id="overall"><h2>All Qwen-evaluated directives</h2>{all_sections}</section>{"".join(type_tabs)}
<div id="topic-breakdowns">{"".join(sections)}</div>
<script>document.querySelectorAll('.tab').forEach(button=>button.addEventListener('click',()=>{{document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x===button));document.querySelectorAll('.tab-panel').forEach(panel=>panel.hidden=panel.id!==button.dataset.panel)}}));</script>
</main></body></html>'''


def write_report(output: Path, root: Path = ROOT) -> dict:
    result = build_analysis(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_html(result), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "data/parent_analysis/qwen_comparison/qwen_topical_coverage.html")
    args = parser.parse_args()
    result = write_report(args.output)
    print(json.dumps({topic: data for topic, data in result["topics"].items()}, indent=2))
    print(args.output)


if __name__ == "__main__":
    main()
