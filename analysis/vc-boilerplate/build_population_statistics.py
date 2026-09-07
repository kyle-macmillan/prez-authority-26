#!/usr/bin/env python3
"""Summarize original-prompt boilerplate-vesting classifications by administration and type."""
from __future__ import annotations

import collections
import csv
import html
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUTPUTS = HERE / "outputs"
OUT_DIR = OUTPUTS / "boilerplate_vesting_statistics"

POPULATIONS = {
    "executive_order": OUTPUTS / "sol_low_eo_population",
    "memorandum": OUTPUTS / "sol_low_memo_population",
    "proclamation": OUTPUTS / "sol_low_proclamation_population",
    "letter": OUTPUTS / "sol_low_letter_population",
}
CODES = range(5)


def load_build_module():
    spec = importlib.util.spec_from_file_location("vc_boilerplate_build_for_statistics", HERE / "build.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_data() -> tuple[list[dict], list[dict]]:
    build = load_build_module()
    directives = []
    for row in build.select_target(build.load_source_rows()):
        directives.append({
            "document_id": str(row["ucsb_identifier"]), "president": row["president"],
            "doc_type": row["doc_type"], "date": row["date"], "url": row["url"],
            "source_file": row["source_file"],
        })
    eligible = {
        (row["source_file"], row["doc_type"], row["document_id"])
        for row in directives
    }
    segments = []
    for doc_type, directory in POPULATIONS.items():
        with (directory / "classifications.csv").open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                segment = {
                    "document_id": str(row["document_id"]), "president": row["president"],
                    "doc_type": doc_type, "source_file": row["source_file"], "code": int(row["code"]),
                }
                key = (segment["source_file"], segment["doc_type"], segment["document_id"])
                if key in eligible:
                    segments.append(segment)
    return directives, segments


def group_keys(row: dict) -> list[tuple[str, str, str]]:
    return [
        ("Overall", "All administrations", "All directive types"),
        ("Administration", row["president"], "All directive types"),
        ("Directive type", "All administrations", row["doc_type"]),
        ("Administration × type", row["president"], row["doc_type"]),
    ]


def summarize(directives: list[dict], segments: list[dict]) -> tuple[list[dict], list[dict]]:
    directive_map = {(row["source_file"], row["doc_type"], row["document_id"]): row for row in directives}
    if len(directive_map) != len(directives):
        raise ValueError("duplicate directive type/ID pairs")
    segment_codes: dict[tuple[str, str, str], set[int]] = collections.defaultdict(set)
    for segment in segments:
        key = (segment["source_file"], segment["doc_type"], segment["document_id"])
        if key not in directive_map:
            raise ValueError(f"classified segment outside boilerplate-vesting population: {key}")
        segment_codes[key].add(segment["code"])

    directive_groups: dict[tuple[str, str, str], list[dict]] = collections.defaultdict(list)
    for directive in directives:
        for key in group_keys(directive):
            directive_groups[key].append(directive)
    directive_rows = []
    for (level, administration, doc_type), members in sorted(directive_groups.items()):
        classified = sum(bool(segment_codes.get((member["source_file"], member["doc_type"], member["document_id"]))) for member in members)
        row = {
            "level": level, "administration": administration, "directive_type": doc_type,
            "directives": len(members), "classified_directives": classified,
            "no_operative_segment": len(members) - classified,
        }
        for code in CODES:
            count = sum(code in segment_codes.get((member["source_file"], member["doc_type"], member["document_id"]), set()) for member in members)
            row[f"directives_containing_code_{code}"] = count
            row[f"share_of_directives_containing_code_{code}"] = count / len(members) if members else 0.0
        directive_rows.append(row)

    segment_groups: dict[tuple[str, str, str], list[dict]] = collections.defaultdict(list)
    for segment in segments:
        for key in group_keys(segment):
            segment_groups[key].append(segment)
    segment_rows = []
    for (level, administration, doc_type), members in sorted(segment_groups.items()):
        row = {
            "level": level, "administration": administration, "directive_type": doc_type,
            "segments": len(members), "directives_with_segments": len({member["document_id"] for member in members}),
        }
        for code in CODES:
            count = sum(member["code"] == code for member in members)
            row[f"code_{code}_segments"] = count
            row[f"code_{code}_share"] = count / len(members) if members else 0.0
        segment_rows.append(row)
    return directive_rows, segment_rows


def legal_effect_administration_summary(directives: list[dict], segments: list[dict]) -> list[dict]:
    """Count directives containing Code 2 and/or Code 3, without double-counting overlap."""
    total_by_administration = collections.Counter(row["president"] for row in directives)
    codes_by_directive: dict[tuple[str, str, str], set[int]] = collections.defaultdict(set)
    metadata = {}
    segment_counts: dict[tuple[str, str, str], collections.Counter] = collections.defaultdict(collections.Counter)
    for segment in segments:
        if segment["code"] not in (2, 3):
            continue
        key = (segment["source_file"], segment["doc_type"], segment["document_id"])
        codes_by_directive[key].add(segment["code"])
        segment_counts[key][segment["code"]] += 1
        metadata[key] = segment
    grouped: dict[str, dict] = collections.defaultdict(lambda: {
        "qualifying_directives": set(), "code_2_directives": set(),
        "code_3_directives": set(), "both_code_2_and_3": set(),
        "code_2_segments": 0, "code_3_segments": 0,
    })
    for key, codes in codes_by_directive.items():
        president = metadata[key]["president"]
        group = grouped[president]
        group["qualifying_directives"].add(key)
        if 2 in codes:
            group["code_2_directives"].add(key)
        if 3 in codes:
            group["code_3_directives"].add(key)
        if codes == {2, 3}:
            group["both_code_2_and_3"].add(key)
        group["code_2_segments"] += segment_counts[key][2]
        group["code_3_segments"] += segment_counts[key][3]
    rows = []
    for president, values in sorted(grouped.items()):
        qualifying = len(values["qualifying_directives"])
        total = total_by_administration[president]
        rows.append({
            "administration": president,
            "all_boilerplate_vesting_directives": total,
            "directives_with_code_2_or_3": qualifying,
            "share_with_code_2_or_3": qualifying / total,
            "directives_containing_code_2": len(values["code_2_directives"]),
            "directives_containing_code_3": len(values["code_3_directives"]),
            "directives_containing_both_code_2_and_3": len(values["both_code_2_and_3"]),
            "code_2_segments": values["code_2_segments"],
            "code_3_segments": values["code_3_segments"],
        })
    overall = {
        "administration": "All administrations",
        "all_boilerplate_vesting_directives": len(directives),
        "directives_with_code_2_or_3": sum(row["directives_with_code_2_or_3"] for row in rows),
        "directives_containing_code_2": sum(row["directives_containing_code_2"] for row in rows),
        "directives_containing_code_3": sum(row["directives_containing_code_3"] for row in rows),
        "directives_containing_both_code_2_and_3": sum(row["directives_containing_both_code_2_and_3"] for row in rows),
        "code_2_segments": sum(row["code_2_segments"] for row in rows),
        "code_3_segments": sum(row["code_3_segments"] for row in rows),
    }
    overall["share_with_code_2_or_3"] = overall["directives_with_code_2_or_3"] / len(directives)
    return [overall, *rows]


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def table(rows: list[dict], fields: list[tuple[str, str]], percent_fields: set[str] = set()) -> str:
    head = "".join(f"<th>{html.escape(label)}</th>" for _, label in fields)
    body = []
    for row in rows:
        cells = []
        for key, _ in fields:
            value = row[key]
            rendered = f"{value:.1%}" if key in percent_fields else f"{value:,}" if isinstance(value, int) else str(value)
            cells.append(f"<td>{html.escape(rendered)}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def render_html(directive_rows: list[dict], segment_rows: list[dict]) -> str:
    overall_directives = next(row for row in directive_rows if row["level"] == "Overall")
    overall_segments = next(row for row in segment_rows if row["level"] == "Overall")
    by_type_directives = [row for row in directive_rows if row["level"] == "Directive type"]
    by_type_segments = [row for row in segment_rows if row["level"] == "Directive type"]
    by_admin_type_directives = [row for row in directive_rows if row["level"] == "Administration × type"]
    by_admin_type_segments = [row for row in segment_rows if row["level"] == "Administration × type"]
    directive_fields = [
        ("administration", "Administration"), ("directive_type", "Directive type"),
        ("directives", "Directives"), ("classified_directives", "With segments"),
        ("no_operative_segment", "No segment"),
        *[(f"directives_containing_code_{code}", f"Contains C{code}") for code in CODES],
    ]
    segment_fields = [
        ("administration", "Administration"), ("directive_type", "Directive type"),
        ("segments", "Segments"),
        *[(f"code_{code}_segments", f"C{code}") for code in CODES],
    ]
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Boilerplate vesting-clause classifications</title><style>
body{{font:15px/1.45 system-ui,sans-serif;margin:0;background:#f4f6f8;color:#182132}}main{{max-width:1400px;margin:auto;padding:24px}}h1{{margin-bottom:4px}}h2{{margin-top:34px}}.note{{color:#596579;max-width:1000px}}.cards{{display:flex;gap:14px;flex-wrap:wrap;margin:20px 0}}.card{{background:#fff;border:1px solid #d8e0e8;border-radius:10px;padding:14px;min-width:180px}}.number{{font-size:28px;font-weight:700}}.scroll{{overflow:auto;background:#fff;border:1px solid #d8e0e8;border-radius:10px}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{padding:8px 10px;border-bottom:1px solid #e6ebf0;text-align:right;white-space:nowrap}}th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){{text-align:left}}th{{position:sticky;top:0;background:#eaf0f6}}details{{margin-top:18px}}summary{{cursor:pointer;font-weight:700}}</style></head><body><main>
<h1>Boilerplate vesting-clause classifications</h1><p class="note">Original frozen prompt, full vague-authority population. Segment codes are mutually exclusive. A directive can contain multiple segment codes, so directive-level “contains Code X” columns overlap and must not be added together.</p>
<div class="cards"><div class="card"><div class="number">{overall_directives['directives']:,}</div>directives</div><div class="card"><div class="number">{overall_directives['classified_directives']:,}</div>with operative segments</div><div class="card"><div class="number">{overall_directives['no_operative_segment']:,}</div>without operative segment</div><div class="card"><div class="number">{overall_segments['segments']:,}</div>classified segments</div></div>
<h2>By directive type</h2><div class="scroll">{table(by_type_directives, directive_fields)}</div><h2>Segment codes by directive type</h2><div class="scroll">{table(by_type_segments, segment_fields)}</div>
<h2>By administration × directive type</h2><div class="scroll">{table(by_admin_type_directives, directive_fields)}</div><h2>Segment codes by administration × directive type</h2><div class="scroll">{table(by_admin_type_segments, segment_fields)}</div>
<details><summary>How to read these statistics</summary><p>“No segment” is a preprocessing outcome, not Code 0. Segment-level counts describe every extracted operative segment. Directive-level Code columns count a directive once for each code it contains.</p></details>
</main></body></html>"""


def main() -> None:
    directives, segments = load_data()
    directive_rows, segment_rows = summarize(directives, segments)
    legal_effect_rows = legal_effect_administration_summary(directives, segments)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(OUT_DIR / "directive_statistics.csv", directive_rows)
    write_csv(OUT_DIR / "segment_statistics.csv", segment_rows)
    write_csv(OUT_DIR / "legal_effect_directives_by_administration.csv", legal_effect_rows)
    (OUT_DIR / "legal_effect_directives_by_administration.json").write_text(
        json.dumps(legal_effect_rows, indent=2) + "\n", encoding="utf-8"
    )
    (OUT_DIR / "report.html").write_text(render_html(directive_rows, segment_rows), encoding="utf-8")
    overall_directives = next(row for row in directive_rows if row["level"] == "Overall")
    overall_segments = next(row for row in segment_rows if row["level"] == "Overall")
    print(json.dumps({"directives": overall_directives["directives"], "segments": overall_segments["segments"],
                      "no_operative_segment": overall_directives["no_operative_segment"], "output": str(OUT_DIR)}, indent=2))


if __name__ == "__main__":
    main()
