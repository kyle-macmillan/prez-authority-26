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


def test_inline_vesting_continuation_without_ordering_phrase_stays_in_action():
    segments = segment_ordering(
        "In accordance with section 6(b) of the Consolidated Appropriations Act, 2020, "
        "I hereby designate all funding so designated by the Congress in these Acts "
        "pursuant to section 251(b)(2)(A) of the Balanced Budget and Emergency Deficit "
        "Control Act of 1985, as outlined in the enclosed list of accounts."
    )
    rendered = _merge_vesting_for_display(segments)

    assert [segment["seg_type"] for segment in rendered] == ["order_action"]
    assert rendered[0]["parts"] == [
        (
            "In accordance with section 6(b) of the Consolidated Appropriations Act, 2020, "
            "I hereby designate all funding so designated by the Congress in these Acts",
            False,
        ),
        (
            " pursuant to section 251(b)(2)(A) of the Balanced Budget and Emergency Deficit "
            "Control Act of 1985,",
            True,
        ),
        (" as outlined in the enclosed list of accounts.", False),
    ]
