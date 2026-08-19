"""Report topical coverage and embedding similarities of Qwen top-1 parents."""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

try:
    from .vesting_topic import extract_vesting_clauses
except ImportError:  # Direct script execution.
    from vesting_topic import extract_vesting_clauses

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
    for path in (root / "data/4_28_2026_build_dev.csv",):
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


def similarity_distribution(
    rows: list[dict[str, str]], qwen_score_field: str | None = None
) -> dict[str, dict[str, float]]:
    result = {
        "document_embedding_similarity": quantile_summary(
            [float(row["document_embedding_score"]) for row in rows]
        ),
        "operative_embedding_similarity": quantile_summary(
            [float(row["operative_embedding_score"]) for row in rows]
        ),
    }
    if qwen_score_field:
        result[qwen_score_field] = quantile_summary(
            [float(row[qwen_score_field]) for row in rows]
        )
    return result


def variant_detail(rows: list[dict[str, str]], label: str, qwen_score_field: str) -> dict:
    return {
        "label": label,
        "children": len(rows),
        "similarity": similarity_distribution(rows, qwen_score_field),
        "histograms": {
            "document_embedding_similarity": histogram([float(row["document_embedding_score"]) for row in rows]),
            "operative_embedding_similarity": histogram([float(row["operative_embedding_score"]) for row in rows]),
            qwen_score_field: histogram([float(row[qwen_score_field]) for row in rows]),
        },
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
    qwen_rows = read_csv(root / "data/parent_analysis/qwen_reranked_candidates.csv")
    top_rows = top_rows_by_variant(qwen_rows)
    qwen_children = set(top_rows["full"])
    analyzed = set(documents)
    automatic = {row["child_id"] for row in read_csv(root / "data/parent_analysis/automatic_edges.csv")}
    vesting_text = {
        document_id: " ".join(extract_vesting_clauses(row["doc_text"], row["doc_type"]))
        for document_id, row in corpus.items()
    }

    result = {
        "total_qwen_children": len(qwen_children),
        "total_candidate_pairs": len(qwen_rows),
        "topics": {},
    }
    for topic, matcher in TOPICS.items():
        topic_ids = {
            document_id for document_id, row in corpus.items()
            if matcher.search(vesting_text[document_id])
        }
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
                "similarity": similarity_distribution(selected, score_field),
                "histograms": {
                    "document_embedding_similarity": histogram([float(row["document_embedding_score"]) for row in selected]),
                    "operative_embedding_similarity": histogram([float(row["operative_embedding_score"]) for row in selected]),
                    score_field: histogram([float(row[score_field]) for row in selected]),
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
        all_rows_by_variant[variant] = variant_detail(selected, label, VARIANTS[variant][1])
    result["all_qwen_evaluated"] = all_rows_by_variant

    type_rows: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    for variant, rows_by_child in top_rows.items():
        for row in rows_by_child.values():
            type_rows[row["document_type"]][variant].append(row)
    result["directive_types"] = {
        document_type: {
            variant: variant_detail(rows, VARIANTS[variant][2], VARIANTS[variant][1])
            for variant, rows in variants.items()
        }
        for document_type, variants in sorted(type_rows.items())
    }
    result["matched_examples"] = [
        {
            "child_id": row["child_id"],
            "parent_id": row["parent_id"],
            "document_type": row["document_type"],
            "child": {key: documents[row["child_id"]].get(key, "") for key in ("title", "date", "url")},
            "parent": {key: documents[row["parent_id"]].get(key, "") for key in ("title", "date", "url")},
            "qwen_score": float(row["qwen_matched_pairs_score"]),
            "document_embedding_score": float(row["document_embedding_score"]),
            "operative_embedding_score": float(row["operative_embedding_score"]),
        }
        for row in [top_rows["matched"][child_id] for child_id in sorted(top_rows["matched"], key=int)[:20]]
    ]
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


def render_distribution_sections(details: dict[str, dict]) -> str:
    return "".join(
        f'<h3>{html.escape(detail["label"])}</h3>'
        f'<p>{detail.get("children", "")} top-ranked child directives.</p>'
        f'{quantile_table(detail["similarity"])}{render_histogram(detail["histograms"])}'
        for detail in details.values()
    )


def render_histogram(histograms: dict[str, list[dict]]) -> str:
    blocks = []
    for metric, bins in histograms.items():
        peak = max(item["count"] for item in bins) or 1
        bars = "".join(
            f'<span title="{item["low"]:.3f}–{item["high"]:.3f}: {item["count"]}" '
            f'style="height:{max(1, 100 * item["count"] / peak):.1f}%"></span>'
            for item in bins
        )
        low = bins[0]["low"]
        high = bins[-1]["high"]
        midpoint = (low + high) / 2
        ticks = "".join(
            f'<span><i></i>{value:.3f}</span>'
            for value in (low, midpoint, high)
        )
        blocks.append(
            f'<div class="hist"><h4>{html.escape(metric.replace("_", " ").title())}</h4>'
            f'<div class="plot"><div class="bars">{bars}</div>'
            f'<div class="axis">{ticks}</div></div></div>'
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
                f'<p class="explain">This section shows the top-ranked parent selected by this Qwen representation. '
                f'{detail["same_topic"]}/{detail["qwen_scored"]} same-topic top-1; '
                f'{detail["nonmatching"]} non-matches.</p>'
                f'{quantile_table(detail["similarity"])}{render_histogram(detail["histograms"])}'
                f'<h4>Non-matching examples</h4><ol>{"".join(examples)}</ol>'
            )
        sections.append(f'<section><h2>{html.escape(topic)}</h2><p>{html.escape(status)}</p>{"".join(variants)}</section>')

    all_sections = render_distribution_sections(result["all_qwen_evaluated"])
    type_tabs = ['<button class="tab active" data-tab="tab-overall">Overall</button>']
    type_panels = [f'<div class="tab-panel active" id="tab-overall"><h2>All Qwen-evaluated directives</h2>{all_sections}</div>']
    for document_type, details in result["directive_types"].items():
        tab_id = "tab-" + re.sub(r"[^a-z0-9]+", "-", document_type.lower()).strip("-")
        label = document_type.replace("_", " ").title()
        type_tabs.append(f'<button class="tab" data-tab="{tab_id}">{html.escape(label)}</button>')
        type_panels.append(
            f'<div class="tab-panel" id="{tab_id}"><h2>{html.escape(label)} directives</h2>'
            f'{render_distribution_sections(details)}</div>'
        )
    example_rows = "".join(
        f'<tr><td>{index}</td><td><a href="{html.escape(example["child"]["url"])}">'
        f'{html.escape(example["child"]["title"])}</a><br><small>ID {example["child_id"]} · '
        f'{html.escape(example["child"]["date"])} · {html.escape(example["document_type"])}</small></td>'
        f'<td><a href="{html.escape(example["parent"]["url"])}">{html.escape(example["parent"]["title"])}</a>'
        f'<br><small>ID {example["parent_id"]} · {html.escape(example["parent"]["date"])}</small></td>'
        f'<td>{example["qwen_score"]:.3f}</td><td>{example["document_embedding_score"]:.3f}</td>'
        f'<td>{example["operative_embedding_score"]:.3f}</td></tr>'
        for index, example in enumerate(result["matched_examples"], 1)
    )
    type_tabs.append('<button class="tab" data-tab="tab-examples">20 matched examples</button>')
    type_panels.append(
        '<div class="tab-panel" id="tab-examples"><h2>20 matched-pairs Qwen examples</h2>'
        '<p>These are the first 20 child directives by ID, with the parent ranked first by matched-pairs Qwen. '
        'They are illustrative examples, not a random sample.</p>'
        '<table><thead><tr><th>#</th><th>Later child directive</th><th>Earlier matched parent</th>'
        '<th>Matched-pairs Qwen</th><th>Document embedding</th><th>Operative embedding</th></tr></thead>'
        f'<tbody>{example_rows}</tbody></table></div>'
    )
    return f'''<!doctype html><html><head><meta charset="utf-8"><title>Qwen topical coverage and similarity</title>
<style>body{{font:15px system-ui;line-height:1.45;color:#172033;background:#f5f7fa;margin:0}}main{{max-width:1400px;margin:auto;padding:28px}}section,.card{{background:#fff;border:1px solid #d8e1eb;border-radius:9px;padding:18px;margin:18px 0}}table{{border-collapse:collapse;width:100%;margin:10px 0 18px}}th,td{{border:1px solid #d8e1eb;padding:7px;text-align:right}}th:first-child,td:first-child{{text-align:left}}th{{background:#eef3f8}}.tabs{{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0 0}}.tab{{border:1px solid #b9c8d6;border-bottom:0;border-radius:8px 8px 0 0;background:#e8eef4;padding:10px 14px;cursor:pointer;font:inherit}}.tab.active{{background:#fff;font-weight:700}}.tab-panel{{display:none;background:#fff;border:1px solid #d8e1eb;border-radius:0 9px 9px 9px;padding:18px;margin:0 0 18px}}.tab-panel.active{{display:block}}.hist{{display:inline-block;width:48%;min-width:330px;vertical-align:top;margin-right:1%}}.plot{{padding:0 6px 22px}}.bars{{height:130px;display:flex;align-items:flex-end;gap:2px;border-bottom:1px solid #9aa8b8;padding:4px}}.bars span{{display:block;flex:1;background:#3b82c4;min-width:2px}}.axis{{display:flex;justify-content:space-between;color:#52606d;font-size:11px}}.axis span{{display:flex;flex-direction:column;align-items:center;min-width:42px}}.axis i{{display:block;height:5px;border-left:1px solid #52606d}}li{{margin:6px 0}}a{{color:#075985}}small{{color:#52606d}}</style></head><body><main>
<h1>Qwen topical coverage and similarity</h1><p>Qwen reranks the RRF top-ten candidate set. Similarity values are cosine similarities; higher values indicate greater similarity. Operative similarity is the bidirectional best-segment aggregate.</p>
<section class="card"><h2>How to read this report</h2>
<p><strong>Document embedding similarity</strong> compares each directive as a whole, using its overall semantic representation. It captures broad subject-matter and meaning overlap.</p>
<p><strong>Operative embedding similarity</strong> compares the directive’s operative provisions—the passages that contain commands, duties, authorities, or actions—rather than treating the full document as one undifferentiated text.</p>
<p><strong>Full-operative Qwen</strong> scores every operative provision in the later (child) directive against every operative provision in the earlier (parent) candidate. The displayed score aggregates the strongest matches in both directions, so it asks whether the two directives have similar operative coverage overall.</p>
<p>More specifically, “strongest matches” means: (1) for each child provision, keep only its highest-scoring parent provision; (2) average those best child-to-parent scores; (3) for each parent provision, keep only its highest-scoring child provision; (4) average those best parent-to-child scores; and (5) average the two directional results.</p>
<p><strong>Matched-pairs Qwen</strong> uses only the provision pairs identified by the embedding-based alignment step. This focuses Qwen on the passages that the retrieval stage considered most corresponding, instead of scoring every possible provision pair.</p>
<p><strong>Qwen score distributions</strong> show the model’s yes-probability for the selected child–parent matches. Higher values indicate stronger model support for the match; lower values indicate weaker support.</p>
<p>A <strong>non-matching example</strong> is a topic directive whose top-ranked Qwen parent belongs outside that topic. For example, an IEEPA child may receive a parent that does not mention IEEPA. These are review examples—not necessarily errors—and help reveal whether the model is matching broader function or operative language rather than the topic label itself.</p>
<p>The distribution tables and histograms summarize the embedding scores for the selected top-1 rows in each cohort and Qwen representation; they are not distributions of every candidate pair.</p>
</section>
<section class="card"><h2>Dataset composition</h2>
<ul>
<li><strong>Directive universe:</strong> the report uses the presidential-directive corpus represented in the document and operative-segment files.</li>
<li><strong>Candidate inputs:</strong> each later directive contributes its RRF-selected top-ten earlier candidates. The report contains {result["total_candidate_pairs"]:,} candidate rows across {result["total_qwen_children"]:,} later directives.</li>
<li><strong>Overall cohort:</strong> the overall tables summarize one top-ranked parent per later directive, separately for full-operative and matched-pairs Qwen.</li>
<li><strong>IEEPA cohort:</strong> directives whose extracted vesting clause mentions “IEEPA” or “International Emergency Economic Powers Act.”</li>
<li><strong>National Emergencies Act cohort:</strong> directives whose extracted vesting clause mentions “National Emergencies Act.”</li>
<li><strong>Topic status:</strong> within each topic, the report distinguishes directives with an automatic parent, directives scored by Qwen, and directives analyzed without Qwen.</li>
</ul>
</section>
<div class="card"><strong>{result["total_qwen_children"]:,}</strong> Qwen-evaluated children</div>
<div class="tabs" role="tablist">{"".join(type_tabs)}</div>{"".join(type_panels)}{"".join(sections)}
<script>document.querySelectorAll('.tab').forEach(button=>button.addEventListener('click',()=>{{document.querySelectorAll('.tab,.tab-panel').forEach(item=>item.classList.remove('active'));button.classList.add('active');document.getElementById(button.dataset.tab).classList.add('active')}}));</script>
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
