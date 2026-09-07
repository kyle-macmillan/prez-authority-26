#!/usr/bin/env python3
"""Tests for the full Code 2/3 review viewer."""
from __future__ import annotations

import build_all_legal_effect_review as viewer


def test_all_legal_effect_segments_are_present_once():
    page, rows = viewer.build()
    segment_ids = [
        (row["document_type"], row["document_id"], segment["segment_id"])
        for row in rows for segment in row["segments"]
    ]
    assert len(segment_ids) == len(set(segment_ids)) == 586
    assert sum(segment["code"] == 2 for row in rows for segment in row["segments"]) == 416
    assert sum(segment["code"] == 3 for row in rows for segment in row["segments"]) == 170
    assert all(segment["code"] in (2, 3) for row in rows for segment in row["segments"])
    assert all(segment_id[2] in page for segment_id in segment_ids)
    assert "Full directive context" in page


if __name__ == "__main__":
    test_all_legal_effect_segments_are_present_once()
    print("PASS test_all_legal_effect_segments_are_present_once")
