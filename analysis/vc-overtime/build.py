"""Build non-ceremonial vesting-clause count figures over administrations.

Run from the repository root:
  python3 analysis/vc-overtime/build.py
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


ANALYSIS_DIR = Path(__file__).resolve().parent
ROOT = ANALYSIS_DIR.parents[1]
SRC_DIR = ROOT / "src"
VESTING_DIR = ROOT / "Authority Vagueness Analysis"
for module_dir in (SRC_DIR, VESTING_DIR):
    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))

from ceremonial import ceremonial_reason  # noqa: E402
from vesting_authority_breakdown import (  # noqa: E402
    CATEGORIES,
    CATEGORY_LABELS,
    VIEWS,
    administration_order,
    analyze,
)
from vesting_authority_stats import DEFAULT_DEV, DEFAULT_HOLDOUT, load_corpus  # noqa: E402


DEFAULT_OUTPUT_DIR = ANALYSIS_DIR / "outputs"
VIEW_ORDER = tuple(VIEWS)
PARTIAL_ADMINISTRATION = "Donald J. Trump (Second)"

PRESIDENT_LABELS = {
    "Harry S Truman": "Truman",
    "Dwight D. Eisenhower": "Eisenhower",
    "John F. Kennedy": "Kennedy",
    "Lyndon B. Johnson": "L. Johnson",
    "Richard Nixon": "Nixon",
    "Gerald R. Ford": "Ford",
    "Jimmy Carter": "Carter",
    "Ronald Reagan": "Reagan",
    "George Bush": "G.H.W. Bush",
    "William J. Clinton": "Clinton",
    "George W. Bush": "G.W. Bush",
    "Barack Obama": "Obama",
    "Donald J. Trump": "Trump",
    "Joseph R. Biden, Jr.": "Biden",
}
FIGURE_STEM = {
    "all": "all_directives",
    "executive_order": "executive_orders",
    "memorandum": "memoranda",
    "letter": "letters",
    "proclamation": "proclamations",
}

EXCLUDED_FIGURE_CATEGORIES = {
    "no_vesting_clause",
    "other_vesting_authority",
}
PLOTTED_CATEGORIES = tuple(
    category for category in CATEGORIES if category not in EXCLUDED_FIGURE_CATEGORIES
)
CORE_AUTHORITY_CATEGORIES = (
    "specific_statute_only",
    "generic_constitution_and_generic_statute",
    "generic_constitution_and_specific_statute",
)
OTHER_AUTHORITY_CATEGORIES = tuple(
    category
    for category in CATEGORIES
    if category not in CORE_AUTHORITY_CATEGORIES and category != "no_vesting_clause"
)

PLOT_LABELS = {
    category: CATEGORY_LABELS[category].split(") ", 1)[-1]
    for category in CATEGORIES
}

RC_PARAMS = {
    "font.size": 10,
    "figure.figsize": [2 * 3.125, 2 * 1.93],
    "legend.fontsize": 6,
    "legend.fancybox": True,
    "font.family": "serif",
    "font.sans-serif": "Times",
    "xtick.major.width": 0.25,
    "xtick.minor.width": 0.25,
    "ytick.major.width": 0.25,
    "ytick.minor.width": 0.25,
    "text.usetex": False,
}


def parse_administration(administration: str) -> tuple[str, str]:
    """Split the report's ``President (Term)`` administration label."""
    president, separator, term = administration.rpartition(" (")
    if not separator or not term.endswith(")"):
        raise ValueError(f"unexpected administration label: {administration!r}")
    return president, term[:-1]


def compact_administration_label(administration: str) -> str:
    president, _ = parse_administration(administration)
    try:
        # Terms remain distinct in the underlying data and sequential x positions, but
        # the display labels intentionally omit Roman-numeral term markers.
        label = PRESIDENT_LABELS[president]
    except KeyError as exc:
        raise ValueError(f"missing compact label for {administration!r}") from exc
    return f"{label}*" if administration == PARTIAL_ADMINISTRATION else label


def retain_categories(
    counts: Counter,
    administration_count: int,
    threshold: float = 50.0,
) -> tuple[dict[str, float], tuple[str, ...]]:
    """Return global all-directive means and categories meeting the cutoff."""
    if administration_count <= 0:
        raise ValueError("administration_count must be positive")
    means = {
        category: counts[("total", "all", category)] / administration_count
        for category in CATEGORIES
    }
    retained = tuple(
        category
        for category in PLOTTED_CATEGORIES
        if means[category] >= threshold
    )
    return means, retained


def filter_ceremonial(rows: list[dict]) -> tuple[list[dict], Counter]:
    retained = []
    reasons = Counter()
    for row in rows:
        reason = ceremonial_reason(row)
        if reason:
            reasons[reason] += 1
        else:
            retained.append(row)
    return retained, reasons


def corpus_latest_date(rows: list[dict]) -> datetime:
    if not rows:
        raise ValueError("cannot find latest date in an empty corpus")
    return max(datetime.strptime(row["date"], "%B %d, %Y") for row in rows)


def source_display_path(path: Path) -> str:
    """Prefer a repository-relative provenance path while supporting CLI overrides."""
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def validate_analysis(
    counts: Counter,
    totals: Counter,
    administrations: list[str],
    retained_document_count: int,
) -> None:
    if totals[("total", "all")] != retained_document_count:
        raise ValueError("all-directive total does not match the retained corpus")
    for administration in (*administrations, "total"):
        for view in VIEW_ORDER:
            category_sum = sum(
                counts[(administration, view, category)] for category in CATEGORIES
            )
            if category_sum != totals[(administration, view)]:
                raise ValueError(
                    f"category total mismatch for {administration}, {view}: "
                    f"{category_sum} != {totals[(administration, view)]}"
                )


def write_counts_csv(
    path: Path,
    counts: Counter,
    administrations: list[str],
    global_means: dict[str, float],
    retained_categories: tuple[str, ...],
) -> None:
    retained_set = set(retained_categories)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = (
        "administration_order",
        "administration",
        "plot_label",
        "president",
        "term",
        "partial_administration",
        "directive_type",
        "category",
        "category_label",
        "count",
        "global_mean_per_administration",
        "retained_at_50",
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for order, administration in enumerate(administrations, start=1):
            president, term = parse_administration(administration)
            for view in VIEW_ORDER:
                for category in CATEGORIES:
                    writer.writerow(
                        {
                            "administration_order": order,
                            "administration": administration,
                            "plot_label": compact_administration_label(administration),
                            "president": president,
                            "term": term,
                            "partial_administration": str(
                                administration == PARTIAL_ADMINISTRATION
                            ).lower(),
                            "directive_type": view,
                            "category": category,
                            "category_label": PLOT_LABELS[category],
                            "count": counts[(administration, view, category)],
                            "global_mean_per_administration": f"{global_means[category]:.6f}",
                            "retained_at_50": str(category in retained_set).lower(),
                        }
                    )


def configure_matplotlib():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(RC_PARAMS)
    plt.rcParams["pdf.fonttype"] = 42
    plt.rcParams["ps.fonttype"] = 42
    return plt


def render_figure(
    plt,
    counts: Counter,
    administrations: list[str],
    view: str,
    categories: tuple[str, ...],
    variant: str,
    figure_dir: Path,
    partial_through: datetime,
) -> list[Path]:
    x_values = list(range(len(administrations)))
    labels = [compact_administration_label(item) for item in administrations]
    colors = plt.get_cmap("tab10").colors
    markers = ("o", "s", "^", "D", "v", "P", "X", "<", ">", "*")
    linestyles = ("-", "--", "-.", ":")

    figure, axis = plt.subplots()
    max_count = 0
    for category in categories:
        category_index = CATEGORIES.index(category)
        values = [counts[(administration, view, category)] for administration in administrations]
        max_count = max(max_count, *values)
        axis.plot(
            x_values,
            values,
            color=colors[category_index % len(colors)],
            linestyle=linestyles[(category_index // len(colors)) % len(linestyles)],
            marker=markers[category_index % len(markers)],
            markersize=2.4,
            linewidth=0.9,
            markeredgewidth=0.25,
            label=PLOT_LABELS[category],
        )

    axis.set_ylabel("Number of directives")
    title_suffix = {
        "all_categories": "All plotted categories",
        "min50": "Global mean ≥ 50 per administration",
        "core_authority": "Core authority categories",
    }[variant]
    axis.set_title(f"Vesting-clause authority: {VIEWS[view]}\n{title_suffix}")
    axis.set_xticks(x_values, labels, rotation=60, ha="right", rotation_mode="anchor")
    axis.set_xlim(-0.35, len(administrations) - 0.65)
    # Reserve headroom for an in-axes legend. Keeping the legend above the data avoids
    # collisions with the 22 rotated administration labels at the fixed figure size.
    axis.set_ylim(0, max(1, math.ceil(max_count * 1.30)))
    axis.grid(axis="y", linewidth=0.35, alpha=0.35)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.legend(
        loc="upper center",
        ncol=2 if len(categories) <= 4 else 3,
        frameon=True,
        framealpha=0.9,
    )
    figure.text(
        0.99,
        0.01,
        f"* Partial through {partial_through.strftime('%b. %-d, %Y')}",
        ha="right",
        va="bottom",
        fontsize=6,
    )
    figure.subplots_adjust(left=0.11, right=0.98, top=0.86, bottom=0.29)

    stem = f"vc_counts_{FIGURE_STEM[view]}_{variant}"
    figure_dir.mkdir(parents=True, exist_ok=True)
    outputs = [figure_dir / f"{stem}.png", figure_dir / f"{stem}.pdf"]
    figure.savefig(outputs[0], dpi=300)
    figure.savefig(outputs[1])
    plt.close(figure)
    return outputs


def render_type_share_trend(
    plt,
    counts: Counter,
    totals: Counter,
    administrations: list[str],
    view: str,
    figure_dir: Path,
    partial_through: datetime,
) -> list[Path]:
    """Plot authority shares and absolute output for one directive type."""
    if view not in {"all", "executive_order", "memorandum", "letter", "proclamation"}:
        raise ValueError(f"unsupported share-trend view: {view}")
    x_values = list(range(len(administrations)))
    labels = [compact_administration_label(item) for item in administrations]
    colors = plt.get_cmap("tab10").colors
    category_styles = {
        "specific_statute_only": (colors[3], "D"),
        "generic_constitution_and_generic_statute": (colors[4], "v"),
        "generic_constitution_and_specific_statute": (colors[5], "P"),
    }
    figure, axis = plt.subplots()
    denominators = [totals[(administration, view)] for administration in administrations]

    count_axis = axis.twinx()
    count_axis.bar(
        x_values, denominators, width=0.72, color="0.75", alpha=0.28,
        edgecolor="none", label=f"Number of {VIEWS[view].lower()}", zorder=0,
    )
    count_axis.set_ylabel(f"Number of {VIEWS[view].lower()}", color="0.35")
    count_axis.tick_params(axis="y", colors="0.35")
    count_axis.spines["top"].set_visible(False)
    count_axis.spines["right"].set_color("0.55")
    count_axis.set_ylim(0, max(1, math.ceil(max(denominators) * 1.18)))
    axis.set_zorder(count_axis.get_zorder() + 1)
    axis.patch.set_visible(False)

    for category in CORE_AUTHORITY_CATEGORIES:
        color, marker = category_styles[category]
        values = [
            100 * counts[(administration, view, category)] / denominator
            if denominator else 0
            for administration, denominator in zip(administrations, denominators)
        ]
        axis.plot(
            x_values, values, color=color, marker=marker, markersize=2.8,
            linewidth=1.15, markeredgewidth=0.25, label=PLOT_LABELS[category],
        )

    if view == "memorandum":
        values = [
            100 * (denominator - counts[(administration, view, "no_vesting_clause")]) / denominator
            if denominator else 0
            for administration, denominator in zip(administrations, denominators)
        ]
        axis.plot(
            x_values, values, color="0.25", linestyle="--", linewidth=1.0,
            label="Any vesting clause",
        )

    other_values = [
        100
        * sum(counts[(administration, view, category)] for category in OTHER_AUTHORITY_CATEGORIES)
        / denominator
        if denominator else 0
        for administration, denominator in zip(administrations, denominators)
    ]
    axis.plot(
        x_values,
        other_values,
        color="0.15",
        linestyle=":",
        marker="o",
        markersize=2.2,
        linewidth=0.95,
        label="Other vesting clause types",
    )

    title = {
        "all": "Vesting Clause Authority Type in All Directives",
        "executive_order": "Vesting Clause Authority by Type in EOs",
        "memorandum": "Vesting Clause Authority Type in Memos",
        "letter": "Vesting Clause Authority Type in Letters",
        "proclamation": "Vesting Clause Authority Type in Proclamations",
    }[view]
    axis.set_title(title)
    axis.set_ylabel(f"Percent of {VIEWS[view].lower()}")
    axis.set_ylim(0, 105)
    axis.set_yticks((0, 25, 50, 75, 100))
    axis.grid(axis="y", linewidth=0.35, alpha=0.35)
    axis.spines["top"].set_visible(False)
    axis.legend(
        loc="upper left" if view == "memorandum" else "upper center",
        ncol=1 if view == "memorandum" else 2,
        frameon=True,
        framealpha=0.9,
    )
    axis.set_xticks(x_values, labels, rotation=60, ha="right", rotation_mode="anchor")
    axis.set_xlim(-0.35, len(administrations) - 0.65)
    figure.text(
        0.99,
        0.01,
        f"* Partial through {partial_through.strftime('%b. %-d, %Y')}",
        ha="right",
        va="bottom",
        fontsize=6,
    )
    figure.subplots_adjust(left=0.11, right=0.89, top=0.86, bottom=0.29)

    figure_dir.mkdir(parents=True, exist_ok=True)
    stem = f"vc_shares_{FIGURE_STEM[view]}_with_counts"
    outputs = [figure_dir / f"{stem}.png", figure_dir / f"{stem}.pdf"]
    figure.savefig(outputs[0], dpi=300)
    figure.savefig(outputs[1])
    plt.close(figure)
    return outputs


def build(dev: Path, holdout: Path, output_dir: Path) -> dict:
    rows = load_corpus([dev, holdout])
    latest_date = corpus_latest_date(rows)
    retained_rows, exclusion_reasons = filter_ceremonial(rows)
    _, counts, totals = analyze(retained_rows)
    administrations = administration_order(retained_rows)
    validate_analysis(counts, totals, administrations, len(retained_rows))

    global_means, retained_categories = retain_categories(counts, len(administrations))
    counts_path = output_dir / "counts_by_administration.csv"
    write_counts_csv(
        counts_path,
        counts,
        administrations,
        global_means,
        retained_categories,
    )

    plt = configure_matplotlib()
    figure_paths = []
    variants = (
        ("all_categories", PLOTTED_CATEGORIES),
        ("min50", retained_categories),
        ("core_authority", CORE_AUTHORITY_CATEGORIES),
    )
    for view in VIEW_ORDER:
        for variant, categories in variants:
            figure_paths.extend(
                render_figure(
                    plt,
                    counts,
                    administrations,
                    view,
                    categories,
                    variant=variant,
                    figure_dir=output_dir / "figures",
                    partial_through=latest_date,
                )
            )
    for view in ("all", "executive_order", "memorandum", "letter", "proclamation"):
        figure_paths.extend(
            render_type_share_trend(
                plt,
                counts,
                totals,
                administrations,
                view=view,
                figure_dir=output_dir / "figures",
                partial_through=latest_date,
            )
        )

    manifest = {
        "source_files": [source_display_path(dev), source_display_path(holdout)],
        "corpus_documents": len(rows),
        "ceremonial_exclusions": len(rows) - len(retained_rows),
        "nonceremonial_documents": len(retained_rows),
        "ceremonial_exclusion_reasons": dict(sorted(exclusion_reasons.items())),
        "administrations": len(administrations),
        "latest_document_date": latest_date.strftime("%Y-%m-%d"),
        "partial_administration": PARTIAL_ADMINISTRATION,
        "partial_through": latest_date.strftime("%Y-%m-%d"),
        "category_average_denominator": len(administrations),
        "category_average_includes_zero_count_administrations": True,
        "category_threshold": 50.0,
        "excluded_from_figures": sorted(EXCLUDED_FIGURE_CATEGORIES),
        "plotted_categories": list(PLOTTED_CATEGORIES),
        "retained_categories": list(retained_categories),
        "core_authority_categories": list(CORE_AUTHORITY_CATEGORIES),
        "global_category_means": {
            category: round(global_means[category], 6) for category in CATEGORIES
        },
        "directive_totals": {view: totals[("total", view)] for view in VIEW_ORDER},
        "counts_csv": str(counts_path.relative_to(ANALYSIS_DIR)),
        "figure_files": [str(path.relative_to(ANALYSIS_DIR)) for path in figure_paths],
        "matplotlib_rcparams": {
            **RC_PARAMS,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        },
        "png_dpi": 300,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev", type=Path, default=DEFAULT_DEV)
    parser.add_argument("--holdout", type=Path, default=DEFAULT_HOLDOUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    manifest = build(args.dev, args.holdout, args.output_dir)
    print(
        f"Built {len(manifest['figure_files']) // 2} figures from "
        f"{manifest['nonceremonial_documents']:,} non-ceremonial directives "
        f"({manifest['ceremonial_exclusions']:,} ceremonial exclusions)."
    )
    print(f"Outputs: {args.output_dir}")


if __name__ == "__main__":
    main()
