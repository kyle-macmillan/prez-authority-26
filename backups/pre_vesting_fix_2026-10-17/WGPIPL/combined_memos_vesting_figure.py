"""Plot vesting-clause shares for memoranda and letters combined as "Memos."""

from __future__ import annotations

import csv
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "WGPIPL" / "vc_shares_memos_with_counts.pdf"
AUTHORITY_DIR = ROOT / "Authority Vagueness Analysis"
sys.path.insert(0, str(AUTHORITY_DIR))
sys.path.insert(0, str(ROOT / "src"))

from ceremonial import is_ceremonial  # noqa: E402
from vesting_authority_breakdown import (  # noqa: E402
    POSSIBLE_VESTING_RE,
    PRESIDENTIAL_TITLE_INVOCATION_RE,
    classify_authority_category,
    extract_vesting_clauses,
)


INPUT_FILES = (
    ROOT / "data" / "4_28_2026_build_dev.csv",
    ROOT / "data" / "4_28_2026_build_holdout.csv",
)
EXCLUDED_URL = (
    "https://www.presidency.ucsb.edu/documents/"
    "letter-the-nation-announcing-diagnosis-alzheimers-disease"
)
DISPLAY_NAMES = {
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
HIGHLIGHTED_CATEGORIES = (
    "specific_statute_only",
    "generic_constitution_and_generic_statute",
    "generic_constitution_and_specific_statute",
)


def load_memos() -> list[dict[str, str]]:
    rows = []
    for path in INPUT_FILES:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows.extend(csv.DictReader(handle))
    return [
        row
        for row in rows
        if row["doc_type"] in {"memorandum", "letter"}
        and row["url"] != EXCLUDED_URL
        and not is_ceremonial(row)
    ]


def aggregate(rows: list[dict[str, str]]) -> tuple[list[str], list[int], dict[str, list[float]]]:
    first_dates = {}
    totals = Counter()
    categories = Counter()
    for row in rows:
        administration = (row["president"], row["term"])
        date = datetime.strptime(row["date"], "%B %d, %Y")
        first_dates[administration] = min(first_dates.get(administration, date), date)
        totals[administration] += 1

        text = row["doc_text"]
        clauses = (
            extract_vesting_clauses(text, row["doc_type"])
            if POSSIBLE_VESTING_RE.search(text)
            or PRESIDENTIAL_TITLE_INVOCATION_RE.search(text)
            else []
        )
        categories[administration, classify_authority_category(clauses)] += 1

    administrations = sorted(first_dates, key=first_dates.get)
    labels = [DISPLAY_NAMES[president] for president, _ in administrations]
    labels[-1] += "*"
    counts = [totals[administration] for administration in administrations]

    series = {category: [] for category in HIGHLIGHTED_CATEGORIES}
    series["any_vesting_clause"] = []
    series["other_vesting_clause_types"] = []
    for administration, denominator in zip(administrations, counts):
        selected = sum(categories[administration, category] for category in HIGHLIGHTED_CATEGORIES)
        no_clause = categories[administration, "no_vesting_clause"]
        for category in HIGHLIGHTED_CATEGORIES:
            series[category].append(100 * categories[administration, category] / denominator)
        series["any_vesting_clause"].append(100 * (denominator - no_clause) / denominator)
        series["other_vesting_clause_types"].append(
            100 * (denominator - no_clause - selected) / denominator
        )

    if sum(counts) != 7_497:
        raise ValueError(f"expected 7,497 combined memos, found {sum(counts):,}")
    return labels, counts, series


def plot(labels: list[str], counts: list[int], series: dict[str, list[float]]) -> None:
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.size": 10,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )
    figure, axis = plt.subplots(figsize=(6.25, 3.86))
    count_axis = axis.twinx()
    x = list(range(len(labels)))

    count_axis.bar(x, counts, width=0.72, color="#E6E6E6", alpha=0.75, zorder=0)
    count_axis.set_ylim(0, 800)
    count_axis.set_yticks([0, 200, 400, 600, 800])
    count_axis.set_ylabel("Number of memos")
    count_axis.tick_params(axis="y", colors="#666666", width=0.4)
    count_axis.spines["top"].set_visible(False)
    count_axis.grid(False)

    styles = (
        ("specific_statute_only", "Specific Statute only", "#E41A1C", "-", "D"),
        (
            "generic_constitution_and_generic_statute",
            "Generic Constitution + Generic Statute",
            "#9467BD",
            "-",
            "v",
        ),
        (
            "generic_constitution_and_specific_statute",
            "Generic Constitution + Specific Statute",
            "#8C564B",
            "-",
            "P",
        ),
        ("any_vesting_clause", "Any vesting clause", "#444444", "--", None),
        ("other_vesting_clause_types", "Other vesting clause types", "#1A1A1A", ":", "o"),
    )
    for key, label, color, linestyle, marker in styles:
        axis.plot(
            x,
            series[key],
            color=color,
            linestyle=linestyle,
            marker=marker,
            markersize=3.5,
            linewidth=1.2,
            label=label,
            zorder=3,
        )

    axis.set_title("Vesting Clause Authority Type in Memos", fontsize=15)
    axis.set_ylabel("Percent of memos")
    axis.set_ylim(0, 100)
    axis.set_yticks([0, 25, 50, 75, 100])
    axis.set_xticks(x)
    axis.set_xticklabels(labels, rotation=58, ha="right")
    axis.grid(axis="y", color="#D9D9D9", linewidth=0.4)
    axis.spines["top"].set_visible(False)
    axis.legend(loc="upper left", frameon=True, fontsize=7.5)
    axis.set_zorder(count_axis.get_zorder() + 1)
    axis.patch.set_visible(False)

    figure.text(
        0.995,
        0.012,
        '* "Memos" combines memoranda and letters; partial through Mar. 12, 2026',
        ha="right",
        va="bottom",
        fontsize=6.5,
    )
    figure.tight_layout(rect=(0, 0.055, 1, 1))
    figure.savefig(OUTPUT, bbox_inches="tight")
    plt.close(figure)


def main() -> None:
    labels, counts, series = aggregate(load_memos())
    plot(labels, counts, series)
    print(f"Wrote {OUTPUT.relative_to(ROOT)} from {sum(counts):,} combined memos")


if __name__ == "__main__":
    main()
