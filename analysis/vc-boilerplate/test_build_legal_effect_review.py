#!/usr/bin/env python3
"""Tests for the Code 2/3 review viewer."""
from __future__ import annotations

import build_legal_effect_review as viewer


def test_review_sample_is_balanced_and_rendered():
    page, rows = viewer.build()
    assert len(rows) == 30
    assert sum(row["document_type"] == "Executive order" for row in rows) == 15
    assert sum(row["document_type"] == "Memorandum" for row in rows) == 15
    for document_type in viewer.SOURCES:
        subset = [row for row in rows if row["document_type"] == document_type]
        assert {2, 3}.issubset({code for row in subset for code in row["codes"]})
    assert page.count('class="document ') == 30
    assert "Full directive context" in page
    assert "Code 2/3 operative segments" in page


if __name__ == "__main__":
    test_review_sample_is_balanced_and_rendered()
    print("PASS test_review_sample_is_balanced_and_rendered")
