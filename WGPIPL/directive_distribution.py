"""Count presidential directives and plot their distribution by administration."""

from __future__ import annotations

import csv
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import seaborn as sns  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "WGPIPL"
AUTHORITY_ANALYSIS_DIR = ROOT / "Authority Vagueness Analysis"
sys.path.insert(0, str(AUTHORITY_ANALYSIS_DIR))
sys.path.insert(0, str(ROOT / "src"))

from vesting_authority_breakdown import (  # noqa: E402
    CATEGORY_LABELS,
    POSSIBLE_VESTING_RE,
    PRESIDENTIAL_TITLE_INVOCATION_RE,
    SUBSTANTIVE_CATEGORIES,
    classify_authority_category,
    extract_vesting_clauses,
)
from ceremonial import is_ceremonial  # noqa: E402
INPUT_FILES = (
    ROOT / "data" / "4_28_2026_build_dev.csv",
    ROOT / "data" / "4_28_2026_build_holdout.csv",
)

DIRECTIVE_TYPES = (
    ("executive_order", "Executive orders"),
    ("memorandum", "Memoranda"),
    ("letter", "Letters"),
    ("proclamation", "Proclamations"),
)
AUTHORITY_CATEGORY_LABELS = {
    category: CATEGORY_LABELS[category].removeprefix(f"({index}) ")
    for index, category in enumerate(SUBSTANTIVE_CATEGORIES, 1)
}
EXPECTED_INPUT_COUNT = 20_232
EXPECTED_ANALYSIS_COUNT = 13_460
EXPECTED_TOTALS = {
    "executive_order": 4_386,
    "memorandum": 3_454,
    "letter": 4_043,
    "proclamation": 1_577,
}
EXCLUDED_URL = (
    "https://www.presidency.ucsb.edu/documents/"
    "letter-the-nation-announcing-diagnosis-alzheimers-disease"
)

SURNAME_LABELS = {
    "Harry S Truman": "Truman",
    "Dwight D. Eisenhower": "Eisenhower",
    "John F. Kennedy": "Kennedy",
    "Lyndon B. Johnson": "Johnson",
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
plt.rcParams.update(
    {
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
)
plt.rcParams["pdf.fonttype"] = 42
plt.rcParams["ps.fonttype"] = 42


def parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%B %d, %Y")


def load_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    required = {"url", "date", "president", "doc_type", "term"}

    for path in INPUT_FILES:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            missing = required.difference(reader.fieldnames or ())
            if missing:
                raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
            rows.extend(reader)

    if len(rows) != EXPECTED_INPUT_COUNT:
        raise ValueError(f"expected {EXPECTED_INPUT_COUNT:,} input rows, found {len(rows):,}")
    if len({row["url"] for row in rows}) != len(rows):
        raise ValueError("input URLs are not unique across the combined corpus")
    if any(not row[field].strip() for row in rows for field in required):
        raise ValueError("one or more required grouping fields are blank")

    excluded = [row for row in rows if row["url"] == EXCLUDED_URL]
    if len(excluded) != 1:
        raise ValueError(f"expected one excluded Reagan letter, found {len(excluded)}")
    rows = [
        row for row in rows
        if row["url"] != EXCLUDED_URL and not is_ceremonial(row)
    ]

    if len(rows) != EXPECTED_ANALYSIS_COUNT:
        raise ValueError(
            f"expected {EXPECTED_ANALYSIS_COUNT:,} analysis rows, found {len(rows):,}"
        )
    totals = Counter(row["doc_type"] for row in rows)
    if dict(totals) != EXPECTED_TOTALS:
        raise ValueError(f"unexpected directive totals: {dict(totals)}")
    return rows


def aggregate(rows: list[dict[str, str]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["parsed_date"] = frame["date"].map(parse_date)

    administrations = (
        frame.groupby(["president", "term"], as_index=False)["parsed_date"]
        .min()
        .sort_values("parsed_date")
        .reset_index(drop=True)
    )
    if len(administrations) != 22:
        raise ValueError(f"expected 22 administrations, found {len(administrations)}")
    administrations["administration_order"] = administrations.index + 1
    administrations["administration"] = administrations["president"].map(SURNAME_LABELS)

    counts = (
        frame.groupby(["president", "term", "doc_type"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )
    result = administrations.merge(counts, on=["president", "term"], validate="one_to_one")
    columns = [key for key, _ in DIRECTIVE_TYPES]
    result = result[
        ["administration_order", "administration", "president", "term", *columns]
    ]

    for directive_type, expected in EXPECTED_TOTALS.items():
        actual = int(result[directive_type].sum())
        if actual != expected:
            raise ValueError(f"{directive_type} sums to {actual:,}, expected {expected:,}")
    return result


def write_counts(counts: pd.DataFrame) -> Path:
    output = OUTPUT_DIR / "directive_counts_by_administration.csv"
    counts.to_csv(output, index=False)
    return output


def aggregate_authority_categories(
    rows: list[dict[str, str]], administrations: pd.DataFrame
) -> pd.DataFrame:
    categorized = []
    for row in rows:
        text = row["doc_text"]
        clauses = (
            extract_vesting_clauses(text, row["doc_type"])
            if POSSIBLE_VESTING_RE.search(text)
            or PRESIDENTIAL_TITLE_INVOCATION_RE.search(text)
            else []
        )
        categorized.append(
            {
                "president": row["president"],
                "term": row["term"],
                "authority_category": classify_authority_category(clauses),
            }
        )

    category_counts = (
        pd.DataFrame(categorized)
        .groupby(["president", "term", "authority_category"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )
    result = administrations[
        ["administration_order", "administration", "president", "term"]
    ].merge(category_counts, on=["president", "term"], validate="one_to_one")
    for category in SUBSTANTIVE_CATEGORIES:
        if category not in result:
            result[category] = 0
    return result[
        ["administration_order", "administration", "president", "term", *SUBSTANTIVE_CATEGORIES]
    ]


def write_authority_category_counts(counts: pd.DataFrame) -> Path:
    output = OUTPUT_DIR / "authority_category_counts_by_administration.csv"
    counts.to_csv(output, index=False)
    return output


def authority_category_change_from_baseline(
    category_counts: pd.DataFrame, directive_counts: pd.DataFrame
) -> pd.DataFrame:
    directive_totals = directive_counts[[key for key, _ in DIRECTIVE_TYPES]].sum(axis=1)
    proportions = category_counts[list(SUBSTANTIVE_CATEGORIES)].div(directive_totals, axis=0)
    changes = 100 * proportions.subtract(proportions.iloc[0], axis="columns")
    result = category_counts[
        ["administration_order", "administration", "president", "term"]
    ].copy()
    result[list(SUBSTANTIVE_CATEGORIES)] = changes
    return result


def write_authority_category_changes(changes: pd.DataFrame) -> Path:
    output = OUTPUT_DIR / "authority_category_percentage_point_change_from_truman.csv"
    changes.to_csv(output, index=False, float_format="%.4f")
    return output


def plot_counts(counts: pd.DataFrame) -> tuple[Path, Path]:
    figure, axis = plt.subplots()
    colors = sns.color_palette("colorblind", n_colors=len(DIRECTIVE_TYPES))

    for color, (directive_type, display_name) in zip(colors, DIRECTIVE_TYPES):
        total = int(counts[directive_type].sum())
        sns.lineplot(
            data=counts,
            x="administration_order",
            y=directive_type,
            marker="o",
            markersize=3.5,
            linewidth=1.2,
            color=color,
            label=f"{display_name} (N={total:,})",
            ax=axis,
        )

    axis.set_xlabel("Administration")
    axis.set_ylabel("Number of directives")
    axis.set_xticks(counts["administration_order"])
    axis.set_xticklabels(counts["administration"], rotation=55, ha="right")
    axis.legend(frameon=True)
    sns.despine(ax=axis, top=True, right=True)
    figure.text(
        0.99,
        0.01,
        "Data through March 12, 2026; excludes ceremonial directives and Reagan's post-presidency letter.",
        ha="right",
        va="bottom",
        fontsize=6,
    )
    figure.tight_layout(rect=(0, 0.055, 1, 1))

    pdf_output = OUTPUT_DIR / "directive_distribution_by_administration.pdf"
    png_output = OUTPUT_DIR / "directive_distribution_by_administration.png"
    figure.savefig(pdf_output, bbox_inches="tight")
    figure.savefig(png_output, dpi=300, bbox_inches="tight")
    plt.close(figure)
    return pdf_output, png_output


def plot_authority_categories(counts: pd.DataFrame) -> tuple[Path, Path]:
    figure, axis = plt.subplots()
    colors = sns.color_palette("colorblind", n_colors=len(SUBSTANTIVE_CATEGORIES))

    for color, category in zip(colors, SUBSTANTIVE_CATEGORIES):
        total = int(counts[category].sum())
        sns.lineplot(
            data=counts,
            x="administration_order",
            y=category,
            marker="o",
            markersize=3.5,
            linewidth=1.2,
            color=color,
            label=f"{AUTHORITY_CATEGORY_LABELS[category]} (N={total:,})",
            ax=axis,
        )

    axis.set_xlabel("Administration")
    axis.set_ylabel("Number of directives")
    axis.set_xticks(counts["administration_order"])
    axis.set_xticklabels(counts["administration"], rotation=55, ha="right")
    axis.legend(frameon=True, ncol=2, columnspacing=0.8, handlelength=1.7)
    sns.despine(ax=axis, top=True, right=True)
    figure.text(
        0.99,
        0.01,
        "Data through March 12, 2026; excludes ceremonial, no-clause, other/unclassified, and Reagan's post-presidency letter.",
        ha="right",
        va="bottom",
        fontsize=6,
    )
    figure.tight_layout(rect=(0, 0.055, 1, 1))

    pdf_output = OUTPUT_DIR / "authority_category_distribution_by_administration.pdf"
    png_output = OUTPUT_DIR / "authority_category_distribution_by_administration.png"
    figure.savefig(pdf_output, bbox_inches="tight")
    figure.savefig(png_output, dpi=300, bbox_inches="tight")
    plt.close(figure)
    return pdf_output, png_output


def plot_authority_category_changes(changes: pd.DataFrame) -> tuple[Path, Path]:
    figure, axis = plt.subplots()
    colors = sns.color_palette("colorblind", n_colors=len(SUBSTANTIVE_CATEGORIES))

    for color, category in zip(colors, SUBSTANTIVE_CATEGORIES):
        sns.lineplot(
            data=changes,
            x="administration_order",
            y=category,
            marker="o",
            markersize=3.5,
            linewidth=1.2,
            color=color,
            label=AUTHORITY_CATEGORY_LABELS[category],
            ax=axis,
        )

    axis.axhline(0, color="black", linewidth=0.7, alpha=0.65)
    axis.set_xlabel("Administration")
    axis.set_ylabel("Change (percentage points)")
    axis.set_xticks(changes["administration_order"])
    axis.set_xticklabels(changes["administration"], rotation=55, ha="right")
    axis.legend(frameon=True, ncol=2, columnspacing=0.8, handlelength=1.7)
    sns.despine(ax=axis, top=True, right=True)
    figure.text(
        0.99,
        0.01,
        "Excludes ceremonial directives; category share of all remaining directives in each administration; Truman = 0.",
        ha="right",
        va="bottom",
        fontsize=6,
    )
    figure.tight_layout(rect=(0, 0.055, 1, 1))

    pdf_output = OUTPUT_DIR / "authority_category_change_from_truman.pdf"
    png_output = OUTPUT_DIR / "authority_category_change_from_truman.png"
    figure.savefig(pdf_output, bbox_inches="tight")
    figure.savefig(png_output, dpi=300, bbox_inches="tight")
    plt.close(figure)
    return pdf_output, png_output


def main() -> None:
    rows = load_rows()
    counts = aggregate(rows)
    csv_output = write_counts(counts)
    pdf_output, png_output = plot_counts(counts)
    authority_counts = aggregate_authority_categories(rows, counts)
    authority_csv_output = write_authority_category_counts(authority_counts)
    authority_pdf_output, authority_png_output = plot_authority_categories(authority_counts)
    authority_changes = authority_category_change_from_baseline(authority_counts, counts)
    authority_changes_csv = write_authority_category_changes(authority_changes)
    authority_changes_pdf, authority_changes_png = plot_authority_category_changes(authority_changes)

    print("Directive totals:")
    for directive_type, display_name in DIRECTIVE_TYPES:
        print(f"  {display_name}: {int(counts[directive_type].sum()):,}")
    print(f"Wrote {csv_output.relative_to(ROOT)}")
    print(f"Wrote {pdf_output.relative_to(ROOT)}")
    print(f"Wrote {png_output.relative_to(ROOT)}")
    print("Authority-category totals:")
    for category in SUBSTANTIVE_CATEGORIES:
        print(f"  {AUTHORITY_CATEGORY_LABELS[category]}: {int(authority_counts[category].sum()):,}")
    print(f"Wrote {authority_csv_output.relative_to(ROOT)}")
    print(f"Wrote {authority_pdf_output.relative_to(ROOT)}")
    print(f"Wrote {authority_png_output.relative_to(ROOT)}")
    print(f"Wrote {authority_changes_csv.relative_to(ROOT)}")
    print(f"Wrote {authority_changes_pdf.relative_to(ROOT)}")
    print(f"Wrote {authority_changes_png.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
