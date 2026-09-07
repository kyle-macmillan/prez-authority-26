#!/usr/bin/env python3
"""Build exact scoped 5-word-reuse distributions and publication-style figures.

The three displayed groups are deliberately not mutually exclusive: the all-scoped
panel contains every scoped nonceremonial directive; the HC-union panel is its
high-confidence subset; and the non-HC/no-explicit-link panel is the clean inference
comparison population used for the 36.3% descriptive result.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np

from build import (
    AUTOMATIC_EDGES,
    DEFAULT_OUTPUT,
    assign_families,
    build_lexical_scores,
    explicit_parent_child_ids,
    load_documents,
    load_profiles,
    read_csv,
    write_csv,
)


HERE = Path(__file__).resolve().parent
THRESHOLD = 0.2206716686487198
EXISTING_NONHC_SCORES = DEFAULT_OUTPUT / "full_nonhc_word5_reuse.csv"
DISTRIBUTION_CSV = DEFAULT_OUTPUT / "scoped_word5_reuse_distribution.csv"
SUMMARY_CSV = DEFAULT_OUTPUT / "scoped_word5_reuse_distribution_summary.csv"
FIGURE_DIR = DEFAULT_OUTPUT / "figures"

RC_PARAMS = {
    "font.size": 10,
    "legend.fontsize": 7,
    "legend.fancybox": True,
    "font.family": "serif",
    "font.sans-serif": "Times",
    "xtick.major.width": 0.25,
    "xtick.minor.width": 0.25,
    "ytick.major.width": 0.25,
    "ytick.minor.width": 0.25,
    "text.usetex": False,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
}


def configure_matplotlib():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(RC_PARAMS)
    return plt


def best_earlier_score(
    child: dict, scores: np.ndarray, dates: np.ndarray, ids: np.ndarray,
    scoped_parent_mask: np.ndarray,
) -> tuple[str, float] | None:
    eligible = (dates < child["parsed_date"].timestamp()) & scoped_parent_mask
    positions = np.flatnonzero(eligible)
    if not len(positions):
        return None
    values = scores[eligible]
    order = np.lexsort((ids[positions].astype(int), -values))
    winner = int(positions[int(order[0])])
    return str(ids[winner]), float(scores[winner])


def load_existing_nonhc_scores(expected_ids: set[str]) -> dict[str, dict]:
    rows = read_csv(EXISTING_NONHC_SCORES)
    output: dict[str, dict] = {}
    for row in rows:
        child_id = row["child_id"]
        if child_id not in expected_ids:
            raise ValueError(f"existing non-HC score has unexpected child ID: {child_id}")
        if row["status"] != "scored" or not row["word5_reuse_score"]:
            raise ValueError(f"existing non-HC score is not usable: {child_id}")
        output[child_id] = {
            "parent_id": row["parent_id"],
            "word5_reuse_score": float(row["word5_reuse_score"]),
            "status": row["status"],
        }
    if set(output) != expected_ids:
        raise ValueError(
            f"existing non-HC scores cover {len(output)} IDs; expected {len(expected_ids)}"
        )
    return output


def score_missing_children(
    documents: list[dict], child_ids: list[str], scoped_ids: set[str], batch_size: int,
) -> dict[str, dict]:
    """Score only HC and explicit-link children not already in the exact non-HC file."""
    by_id = {row["document_id"]: row for row in documents}
    dates = np.asarray([row["parsed_date"].timestamp() for row in documents])
    ids = np.asarray([row["document_id"] for row in documents])
    scoped_parent_mask = np.asarray([row["document_id"] in scoped_ids for row in documents])
    output: dict[str, dict] = {}
    for start in range(0, len(child_ids), batch_size):
        batch = child_ids[start : start + batch_size]
        score_map = build_lexical_scores(documents, batch, "primary_text", size=5)
        for child_id in batch:
            result = best_earlier_score(
                by_id[child_id], score_map[child_id], dates, ids, scoped_parent_mask
            )
            if result is None:
                output[child_id] = {
                    "parent_id": "", "word5_reuse_score": "",
                    "status": "no_strictly_earlier_scoped_parent",
                }
            else:
                parent_id, score = result
                output[child_id] = {
                    "parent_id": parent_id, "word5_reuse_score": score, "status": "scored",
                }
        print(json.dumps({
            "newly_scored": min(start + len(batch), len(child_ids)),
            "new_score_total": len(child_ids),
        }, sort_keys=True), flush=True)
    return output


def group_label(child_id: str, hc_ids: set[str], comparison_ids: set[str]) -> str:
    if child_id in hc_ids:
        return "high_confidence_union"
    if child_id in comparison_ids:
        return "non_hc_no_explicit_link"
    return "other_scoped_explicit_link"


def quantile(values: list[float], point: float) -> float:
    return float(np.quantile(np.asarray(values), point))


def summarize(values: list[float], label: str, total: int) -> dict:
    return {
        "group": label,
        "total_directives": total,
        "scored_directives": len(values),
        "unscored_directives": total - len(values),
        "median": quantile(values, 0.50),
        "p25": quantile(values, 0.25),
        "p75": quantile(values, 0.75),
        "p90": quantile(values, 0.90),
        "p95": quantile(values, 0.95),
        "above_hc_pilot_median": sum(value > THRESHOLD for value in values),
        "share_above_hc_pilot_median": sum(value > THRESHOLD for value in values) / len(values),
    }


def render_histograms(
    plt, groups: list[tuple[str, list[float], tuple]], output: Path, reference_score: float,
) -> list[Path]:
    figure, axes = plt.subplots(1, 3, figsize=(9.375, 3.86), sharex=True)
    bins = np.linspace(0, 1, 41)
    for axis, (label, values, color) in zip(axes, groups, strict=True):
        axis.hist(values, bins=bins, density=True, color=color, alpha=0.78, edgecolor="white", linewidth=0.25)
        axis.axvline(reference_score, color="0.15", linestyle="--", linewidth=0.9)
        axis.set_title(f"{label}\n(n = {len(values):,}; median = {np.median(values):.3f})", fontsize=9)
        axis.set_xlim(0, 1)
        axis.set_xlabel("Best-earlier weighted 5-word reuse")
        axis.grid(axis="y", linewidth=0.35, alpha=0.35)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
    axes[0].set_ylabel("Density")
    figure.text(
        0.5, 0.01,
        f"Dashed line: full HC-union median ({reference_score:.3f}). HC is a subset of all directives; the non-HC panel excludes explicit links.",
        ha="center", va="bottom", fontsize=6,
    )
    figure.subplots_adjust(left=0.07, right=0.99, top=0.84, bottom=0.22, wspace=0.23)
    paths = [output / "word5_reuse_distribution_panels.png", output / "word5_reuse_distribution_panels.pdf"]
    figure.savefig(paths[0], dpi=300)
    figure.savefig(paths[1])
    plt.close(figure)
    return paths


def render_ecdf(
    plt, groups: list[tuple[str, list[float], tuple]], output: Path, reference_score: float,
) -> list[Path]:
    figure, axis = plt.subplots(figsize=(6.25, 3.86))
    shares_above = []
    for label, values, color in groups:
        ordered = np.sort(np.asarray(values))
        y_values = np.arange(1, len(ordered) + 1) / len(ordered)
        axis.step(ordered, y_values, where="post", color=color, linewidth=1.25, label=label)
        share_at_or_below = np.searchsorted(ordered, reference_score, side="right") / len(ordered)
        axis.scatter([reference_score], [share_at_or_below], color=color, s=14, zorder=3)
        shares_above.append((label, 1 - share_at_or_below))
    axis.axvline(
        reference_score, color="0.15", linestyle="--", linewidth=0.9,
        label=f"Full HC-union median: {reference_score:.3f}",
    )
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1.01)
    axis.set_xlabel("Best-earlier weighted 5-word reuse")
    axis.set_ylabel("Share of directives with score at or below x")
    axis.set_yticks((0, 0.25, 0.50, 0.75, 1.00), ("0%", "25%", "50%", "75%", "100%"))
    axis.set_title("Cumulative distribution of text-reuse scores")
    axis.grid(linewidth=0.35, alpha=0.35)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.legend(loc="lower right", frameon=True, framealpha=0.9)
    axis.text(
        0.02, 0.94,
        "Share above HC-union median:\n" + "\n".join(
            f"{label}: {share:.1%}" for label, share in shares_above
        ),
        transform=axis.transAxes, ha="left", va="top", fontsize=7,
        bbox={"facecolor": "white", "edgecolor": "0.75", "alpha": 0.92, "pad": 3},
    )
    figure.text(
        0.99, 0.01,
        "Scores compare each directive with all strictly earlier eligible directives; same-day candidates are excluded.",
        ha="right", va="bottom", fontsize=6,
    )
    figure.subplots_adjust(left=0.13, right=0.98, top=0.88, bottom=0.20)
    paths = [output / "word5_reuse_distribution_ecdf.png", output / "word5_reuse_distribution_ecdf.pdf"]
    figure.savefig(paths[0], dpi=300)
    figure.savefig(paths[1])
    plt.close(figure)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=400)
    parser.add_argument("--render-only", action="store_true", help="Reuse the saved distribution CSV.")
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")

    documents, _ = load_documents()
    assign_families(documents, load_profiles())
    scoped_ids = {row["document_id"] for row in documents if not row["analysis_scope_reason"]}
    hc_ids = {row["document_id"] for row in documents if row["document_id"] in scoped_ids and row["families"]}
    explicit_ids = explicit_parent_child_ids(read_csv(AUTOMATIC_EDGES)) & scoped_ids
    comparison_ids = scoped_ids - hc_ids - explicit_ids
    if (len(scoped_ids), len(hc_ids), len(comparison_ids)) != (13086, 1577, 9583):
        raise ValueError("unexpected scoped/HC/comparison population counts")

    if args.render_only:
        rows = read_csv(DISTRIBUTION_CSV)
        if {row["child_id"] for row in rows} != scoped_ids:
            raise ValueError("saved distribution CSV does not cover the scoped population")
        missing_ids = []
    else:
        scores = load_existing_nonhc_scores(comparison_ids)
        missing_ids = sorted(scoped_ids - set(scores), key=int)
        scores.update(score_missing_children(documents, missing_ids, scoped_ids, args.batch_size))
        if set(scores) != scoped_ids:
            raise ValueError("score file does not cover the full scoped population")
        rows = []
        for child_id in sorted(scoped_ids, key=int):
            row = scores[child_id]
            rows.append({
                "child_id": child_id,
                "group": group_label(child_id, hc_ids, comparison_ids),
                "is_high_confidence": child_id in hc_ids,
                "has_explicit_parent_link": child_id in explicit_ids,
                **row,
            })
        write_csv(DISTRIBUTION_CSV, rows)

    values = {
        "All nonceremonial": [float(row["word5_reuse_score"]) for row in rows if row["status"] == "scored"],
        "High-confidence union": [
            float(row["word5_reuse_score"]) for row in rows
            if row["status"] == "scored" and str(row["is_high_confidence"]).casefold() == "true"
        ],
        "Non-HC, no explicit link": [float(row["word5_reuse_score"]) for row in rows if row["status"] == "scored" and row["group"] == "non_hc_no_explicit_link"],
    }
    expected = {
        "All nonceremonial": len(scoped_ids),
        "High-confidence union": len(hc_ids),
        "Non-HC, no explicit link": len(comparison_ids),
    }
    summary = [summarize(values[label], label, expected[label]) for label in values]
    write_csv(SUMMARY_CSV, summary)

    plt = configure_matplotlib()
    colors = plt.get_cmap("tab10").colors
    groups = [
        ("All nonceremonial", values["All nonceremonial"], (0.35, 0.35, 0.35)),
        ("High-confidence union", values["High-confidence union"], colors[3]),
        ("Non-HC, no explicit link", values["Non-HC, no explicit link"], colors[0]),
    ]
    reference_score = float(np.median(values["High-confidence union"]))
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    figure_paths = (
        render_histograms(plt, groups, FIGURE_DIR, reference_score)
        + render_ecdf(plt, groups, FIGURE_DIR, reference_score)
    )
    manifest = {
        "score": "best-earlier IDF-weighted unique 5-word reuse",
        "hc_pilot_threshold": THRESHOLD,
        "figure_reference_score": reference_score,
        "figure_reference_label": "full high-confidence-union median",
        "population": "scoped nonceremonial directives",
        "scoped_total": len(scoped_ids),
        "high_confidence_total": len(hc_ids),
        "non_hc_no_explicit_link_total": len(comparison_ids),
        "explicit_link_children_in_scoped_population": len(explicit_ids),
        "reused_exact_non_hc_scores": len(comparison_ids),
        "newly_scored_directives": len(scoped_ids) - len(comparison_ids),
        "figures": [str(path.relative_to(DEFAULT_OUTPUT)) for path in figure_paths],
    }
    (FIGURE_DIR / "word5_reuse_distribution_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"summary": summary, "figures": manifest["figures"]}, sort_keys=True))


if __name__ == "__main__":
    main()
