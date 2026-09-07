#!/usr/bin/env python3
"""Tests for aggregate boilerplate-vesting statistics."""
from __future__ import annotations

import build_population_statistics as stats


def test_population_totals_and_grouping():
    directives, segments = stats.load_data()
    directive_rows, segment_rows = stats.summarize(directives, segments)
    overall_d = next(row for row in directive_rows if row["level"] == "Overall")
    overall_s = next(row for row in segment_rows if row["level"] == "Overall")
    assert overall_d["directives"] == 1361
    assert overall_d["no_operative_segment"] == 33
    assert overall_s["segments"] == 6239
    assert sum(overall_s[f"code_{code}_segments"] for code in stats.CODES) == 6239
    types = {row["directive_type"]: row for row in directive_rows if row["level"] == "Directive type"}
    assert {"executive_order", "memorandum", "proclamation", "letter"} == set(types)
    assert all(row["directives_containing_code_2"] <= row["directives"] for row in directive_rows)
    legal_effect = stats.legal_effect_administration_summary(directives, segments)
    overall_legal_effect = legal_effect[0]
    assert overall_legal_effect["directives_with_code_2_or_3"] == 299
    assert overall_legal_effect["code_2_segments"] == 412
    assert overall_legal_effect["code_3_segments"] == 165


if __name__ == "__main__":
    test_population_totals_and_grouping()
    print("PASS test_population_totals_and_grouping")
