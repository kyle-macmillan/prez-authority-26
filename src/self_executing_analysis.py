"""Cross-tabulate self-executing vs. not × vesting-authority specificity for sample-100.

Two modes:
  build     -- resolve document IDs, compute vesting_category (generic/specific/no_vesting_clause),
               and write an empty-coded worksheet CSV ready for manual coding.
  summarize -- read a completed coded worksheet and print/write contingency tables.

Run from the project root:
  python3 src/self_executing_analysis.py build
  python3 src/self_executing_analysis.py summarize --coded data/self_executing_sample75_coded.csv
"""

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from vesting_authority_stats import (
    classify_vesting_clauses,
    extract_vesting_clauses,
    load_corpus,
    DEFAULT_DEV,
    DEFAULT_HOLDOUT,
)

ROOT = Path(__file__).parent.parent
DOC_ID_MAP = ROOT / "data" / "Annotations" / "Sandbox 1" / "doc_id_map_viewer.json"
DEFAULT_WORKSHEET = ROOT / "data" / "self_executing_sample75.csv"
DEFAULT_CODED = ROOT / "data" / "self_executing_sample75_coded.csv"
DEFAULT_SUMMARY = ROOT / "data" / "self_executing_summary.md"

IN_SCOPE_PREFIXES = ("EO", "M", "P")  # letters excluded


def _label_prefix(label: str) -> str:
    return "".join(ch for ch in label if not ch.isdigit())


def _vesting_category(doc_text: str, doc_type: str) -> tuple[str, str, str, str]:
    """Return (vesting_category, generic_matches_json, specific_matches_json, clauses_json)."""
    clauses = extract_vesting_clauses(doc_text, doc_type)
    if not clauses:
        return "no_vesting_clause", "[]", "[]", "[]"
    qualifies, generic, specific = classify_vesting_clauses(clauses)
    cat = "generic" if qualifies else "specific"
    generic_json = json.dumps([{"rule": m.rule, "text": m.text} for m in generic])
    specific_json = json.dumps([{"rule": m.rule, "text": m.text} for m in specific])
    clauses_json = json.dumps(clauses)
    return cat, generic_json, specific_json, clauses_json


def build(worksheet_path: Path) -> None:
    """Build empty-coded worksheet for 75 in-scope sample-100 documents."""
    id_map: dict[str, int] = json.loads(DOC_ID_MAP.read_text())
    corpus_rows = load_corpus([DEFAULT_DEV, DEFAULT_HOLDOUT])
    corpus: dict[int, dict] = {int(row[""]): row for row in corpus_rows}

    rows = []
    for label in sorted(id_map, key=lambda k: (_label_prefix(k), int(k[len(_label_prefix(k)):]))):
        prefix = _label_prefix(label)
        if prefix not in IN_SCOPE_PREFIXES:
            continue
        doc_id = id_map[label]
        row = corpus[doc_id]
        doc_text = row["doc_text"]
        doc_type = row["doc_type"]
        cat, gen_json, spec_json, clauses_json = _vesting_category(doc_text, doc_type)
        rows.append({
            "sample_label": label,
            "document_id": doc_id,
            "doc_type": doc_type,
            "date": row["date"],
            "president": row["president"],
            "url": row["url"],
            "vesting_category": cat,
            "generic_matches": gen_json,
            "specific_matches": spec_json,
            "vesting_clauses": clauses_json,
            "self_executing": "",
            "mixed_flag": "",
            "rationale": "",
            "full_text": doc_text,
        })

    assert len(rows) == 75, f"expected 75 rows, got {len(rows)}"
    prefix_counts = Counter(_label_prefix(r["sample_label"]) for r in rows)
    for p in IN_SCOPE_PREFIXES:
        assert prefix_counts[p] == 25, f"expected 25 {p}, got {prefix_counts[p]}"

    with open(worksheet_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {worksheet_path}")
    vc = Counter(r["vesting_category"] for r in rows)
    for cat, n in sorted(vc.items()):
        print(f"  {cat}: {n}")


def _fmt_table(row_labels: list[str], col_labels: list[str],
               cells: dict[tuple[str, str], int], row_totals: bool = True) -> str:
    col_w = max(len(c) for c in col_labels + ["(total)"])
    row_w = max(len(r) for r in row_labels + [""])
    header = " " * (row_w + 2) + "  ".join(c.rjust(col_w) for c in col_labels)
    if row_totals:
        header += "  " + "total".rjust(col_w)
    lines = [header, "-" * len(header)]
    for rl in row_labels:
        vals = [cells.get((rl, cl), 0) for cl in col_labels]
        line = rl.ljust(row_w) + "  " + "  ".join(str(v).rjust(col_w) for v in vals)
        if row_totals:
            line += "  " + str(sum(vals)).rjust(col_w)
        lines.append(line)
    # column totals
    col_tots = [sum(cells.get((rl, cl), 0) for rl in row_labels) for cl in col_labels]
    tot_line = "total".ljust(row_w) + "  " + "  ".join(str(v).rjust(col_w) for v in col_tots)
    if row_totals:
        tot_line += "  " + str(sum(col_tots)).rjust(col_w)
    lines += ["-" * len(header), tot_line]
    return "\n".join(lines)


def summarize(coded_path: Path, summary_path: Path) -> None:
    """Read completed coded CSV and print/write contingency tables."""
    with open(coded_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    uncoded = [r for r in rows if not r["self_executing"].strip()]
    if uncoded:
        labels = [r["sample_label"] for r in uncoded]
        print(f"WARNING: {len(uncoded)} rows have no self_executing value: {labels[:10]}", file=sys.stderr)

    coded = [r for r in rows if r["self_executing"].strip()]
    mixed_count = sum(1 for r in coded if r.get("mixed_flag", "").strip().lower() in ("true", "1", "yes"))

    se_vals = ["self_executing", "not_self_executing"]
    vc_vals = ["generic", "specific", "no_vesting_clause"]
    doc_types = ["executive_order", "memorandum", "proclamation"]

    # headline table
    headline: dict[tuple[str, str], int] = Counter()
    for r in coded:
        headline[(r["self_executing"], r["vesting_category"])] += 1

    # per-type tables
    per_type: dict[str, dict[tuple[str, str], int]] = {dt: Counter() for dt in doc_types}
    for r in coded:
        per_type[r["doc_type"]][(r["self_executing"], r["vesting_category"])] += 1

    out_lines = ["# Self-executing × vesting authority specificity (sample-100, n=75)\n"]
    out_lines.append(f"Coded: {len(coded)} / {len(rows)}   Mixed-flag (judgment calls): {mixed_count}\n")
    out_lines.append("## Headline table (all doc types)\n")
    out_lines.append("```")
    out_lines.append(_fmt_table(se_vals, vc_vals, headline))
    out_lines.append("```\n")
    for dt in doc_types:
        out_lines.append(f"## {dt.replace('_', ' ').title()}\n")
        out_lines.append("```")
        out_lines.append(_fmt_table(se_vals, vc_vals, per_type[dt]))
        out_lines.append("```\n")

    summary = "\n".join(out_lines)
    print(summary)
    summary_path.write_text(summary, encoding="utf-8")
    print(f"\nSummary written to {summary_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    bp = sub.add_parser("build", help="Build empty-coded worksheet")
    bp.add_argument("--out", type=Path, default=DEFAULT_WORKSHEET)

    sp = sub.add_parser("summarize", help="Summarize coded worksheet")
    sp.add_argument("--coded", type=Path, default=DEFAULT_CODED)
    sp.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY)

    args = parser.parse_args()
    if args.mode == "build":
        build(args.out)
    else:
        summarize(args.coded, args.summary_out)


if __name__ == "__main__":
    main()
