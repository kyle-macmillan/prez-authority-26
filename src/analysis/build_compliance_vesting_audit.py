#!/usr/bin/env python3
"""Audit compliance-led sentences that appear to contain missed vesting clauses."""

from __future__ import annotations

import csv
import html
import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import segmenter


DATA_FILE = ROOT / "data" / "4_28_2026_build_dev.csv"
OUT_FILE = ROOT / "data" / "sample_segmentation" / "compliance_vesting_audit.html"
COMPLIANCE_OPEN_RE = re.compile(
    r"^\s*(?:consistent\s+with|in\s+compliance\s+with|subject\s+to|"
    r"to\s+the\s+(?:maximum\s+|fullest\s+)?extent\s+"
    r"(?:permitted|authorized)\s+by)\b",
    re.IGNORECASE,
)


def main() -> None:
    ordering_re = segmenter._get_ordering_re(extended=True)
    candidates: list[tuple[dict, str]] = []
    with DATA_FILE.open(newline="") as handle:
        for row in csv.DictReader(handle):
            for chunk in re.split(r" {2,}", row["doc_text"]):
                for sentence in segmenter._split_sentences(chunk) or [chunk]:
                    if not COMPLIANCE_OPEN_RE.match(sentence):
                        continue
                    if not segmenter._LAW_CITATION_RE.search(sentence):
                        continue
                    if not segmenter._PRESIDENTIAL_I_RE.search(sentence):
                        continue
                    if not ordering_re.search(sentence):
                        continue
                    segments = segmenter.segment_ordering(sentence, row["doc_type"])
                    if any(segment.seg_type == "vesting_clause" for segment in segments):
                        continue
                    candidates.append((row, sentence))

    unique_documents = {row[""] for row, _ in candidates}
    document_type_by_id = {row[""]: row["doc_type"] for row, _ in candidates}
    document_types = Counter(document_type_by_id.values())
    cards = []
    for number, (row, sentence) in enumerate(candidates, 1):
        connector = COMPLIANCE_OPEN_RE.match(sentence)
        assert connector is not None
        rendered = (
            html.escape(sentence[: connector.start()])
            + f"<mark>{html.escape(connector.group(0))}</mark>"
            + html.escape(sentence[connector.end() :])
        )
        cards.append(
            f"""<article>
<h2>#{number} &middot; dev:{html.escape(row[''])} &middot;
{html.escape(row['doc_type'])} &middot; {html.escape(row['date'])} &middot;
{html.escape(row['president'])}</h2>
<p>{rendered}</p>
<a href="{html.escape(row['url'])}" target="_blank">Original document &rarr;</a>
</article>"""
        )

    summary = ", ".join(
        f"{document_type}: {count}"
        for document_type, count in sorted(document_types.items())
    )
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Compliance-led missed vesting candidates</title><style>
body {{ font:14px/1.55 system-ui,sans-serif; margin:24px auto; max-width:1100px; color:#172033; }}
header {{ position:sticky; top:0; background:#fff; border-bottom:2px solid #dbe3ef; padding:10px 0; }}
h1 {{ margin:0; font-size:22px; }} header p {{ margin:4px 0; color:#526070; }}
article {{ border:1px solid #dbe3ef; border-radius:7px; margin:14px 0; padding:14px 18px; }}
h2 {{ font-size:13px; color:#526070; margin:0 0 8px; }} article p {{ margin:0 0 8px; }}
mark {{ background:#fde68a; color:#7c2d12; font-weight:700; }} a {{ color:#1d4ed8; }}
</style></head><body><header>
<h1>Compliance-led missed vesting candidates</h1>
<p>{len(candidates)} sentences across {len(unique_documents)} directives. {html.escape(summary)}.</p>
<p>Criteria: compliance-led opening + legal citation + presidential “I” + ordering phrase,
with no vesting clause currently detected.</p></header>{''.join(cards)}</body></html>"""
    OUT_FILE.write_text(page)
    print(f"Wrote {OUT_FILE}")
    print(f"{len(candidates)} sentences across {len(unique_documents)} directives")
    print(summary)


if __name__ == "__main__":
    main()
