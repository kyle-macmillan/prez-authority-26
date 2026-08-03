"""Regression tests for segment rendering in annotation viewers."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from segmenter import segment_ordering
from view_segments import _merge_vesting_for_display


def test_distinct_wp_actions_in_one_source_chunk_stay_split_for_display():
    segments = segment_ordering(
        "The Secretary shall develop a plan. "
        "The Secretary shall implement the plan."
    )
    rendered = _merge_vesting_for_display(segments)

    assert [segment.seg_type for segment in segments] == [
        "order_action",
        "order_action",
    ]
    assert [segment["seg_type"] for segment in rendered] == [
        "order_action",
        "order_action",
    ]
