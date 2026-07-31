#!/usr/bin/env python3
"""Build an HTML audit of bounded comma-delimited ``shall`` matches."""

from __future__ import annotations

import csv
import html
import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from segmenter import _get_ordering_re


DATA_FILE = ROOT / "data" / "4_28_2026_build_dev.csv"
OUT_FILE = ROOT / "data" / "sample_segmentation" / "shall_comma_extension_audit.html"
def context(text: str, start: int, end: int, radius: int = 240) -> tuple[str, str, str]:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return text[left:start], text[start:end], text[end:right]


def main() -> None:
    ordering_re = _get_ordering_re(extended=True)
    matches: list[tuple[dict, re.Match]] = []
    with DATA_FILE.open(newline="") as handle:
        for row in csv.DictReader(handle):
            for match in ordering_re.finditer(row["doc_text"]):
                if re.match(r"shall\s*,", match.group(0), re.IGNORECASE):
                    matches.append((row, match))

    type_counts = Counter(row["doc_type"] for row, _ in matches)
    cards = []
    for number, (row, match) in enumerate(matches, 1):
        before, matched, after = context(row["doc_text"], match.start(), match.end())
        cards.append(
            f"""<article>
  <h2>#{number} &middot; dev:{html.escape(row[''])} &middot;
      {html.escape(row['doc_type'])} &middot; {html.escape(row['date'])} &middot;
      {html.escape(row['president'])}</h2>
  <p>{html.escape(before)}<mark>{html.escape(matched)}</mark>{html.escape(after)}</p>
  <a href="{html.escape(row['url'])}" target="_blank">Original document &rarr;</a>
</article>"""
        )

    summary = ", ".join(f"{key}: {value}" for key, value in sorted(type_counts.items()))
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Comma-delimited shall extension audit</title>
<style>
body {{ font: 14px/1.55 system-ui,sans-serif; margin: 24px auto; max-width: 1100px; color:#172033; }}
header {{ position:sticky; top:0; background:#fff; border-bottom:2px solid #dbe3ef; padding:10px 0; }}
h1 {{ margin:0; font-size:22px; }} header p {{ margin:4px 0; color:#526070; }}
article {{ border:1px solid #dbe3ef; border-radius:7px; margin:14px 0; padding:14px 18px; }}
h2 {{ font-size:13px; color:#526070; margin:0 0 8px; }}
article p {{ white-space:pre-wrap; margin:0 0 8px; }}
mark {{ background:#fde68a; color:#7c2d12; font-weight:700; padding:1px 2px; }}
a {{ color:#1d4ed8; }}
</style></head><body>
<header><h1>Bounded comma-delimited <code>shall</code> extension</h1>
<p>{len(matches)} newly matched instances. {html.escape(summary)}.</p>
<p>Highlighted text is the complete trigger match; context is shown on both sides.</p></header>
{''.join(cards)}
</body></html>"""
    OUT_FILE.write_text(page)
    print(f"Wrote {OUT_FILE} ({len(matches)} matches)")
    print(summary)


if __name__ == "__main__":
    main()
