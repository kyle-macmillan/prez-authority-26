"""Focused regression tests for extended ordering-phrase segmentation.

Run from the project root:
  python3 src/test_segmenter.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from segmenter import segment, segment_ordering


ALLOWLISTED_VERBS = (
    "take", "develop", "designate", "establish", "perform", "make", "issue",
    "identify", "prepare", "implement", "determine", "recommend", "prescribe",
    "seek", "assist",
)


def _section_type(predicate: str, *, strict_wp: bool = False) -> str:
    text = f"Introductory context.  Section 1. The Board shall {predicate} the work."
    matches = [
        seg for seg in segment_ordering(text, strict_wp=strict_wp)
        if f"shall {predicate}" in seg.text
    ]
    assert len(matches) == 1
    return matches[0].seg_type


def test_allowlisted_verbs_split_regardless_of_formal_sections():
    for verb in ALLOWLISTED_VERBS:
        assert _section_type(verb) == "order_action", verb


def test_explicit_modifiers_are_supported():
    assert _section_type("promptly develop") == "order_action"
    assert _section_type("also promptly make") == "order_action"
    assert _section_type("immediately perform") == "order_action"


def test_status_and_definition_verbs_are_excluded():
    for verb in ("be", "have", "include", "apply"):
        assert _section_type(verb) == "preamble", verb


def test_actor_does_not_affect_matching():
    text = (
        "Section 1. The Board shall perform the work.  "
        "Section 2. Federal agencies shall make recommendations.  "
        "Section 3. The Secretary shall issue guidance."
    )
    actions = [seg.text for seg in segment_ordering(text) if seg.seg_type == "order_action"]
    assert actions == [
        "The Board shall perform the work. Section 2.",
        "Federal agencies shall make recommendations. Section 3.",
        "The Secretary shall issue guidance.",
    ]


def test_section_paragraph_strategy_uses_same_extension():
    text = "Section 1. The Board shall perform the work."
    sections = segment(text)
    assert len(sections) == 1
    assert sections[0].seg_type == "section"


def test_hyphen_numbered_sections_and_subsections_split_for_coding():
    text = (
        "By authority vested in me, it is hereby ordered as follows:  "
        "1-1. National Contingency Plan.  "
        "1-101. The plan shall be the primary vehicle for coordination.  "
        "1-102. The Chairman is delegated authority.  "
        "2-1. Response Authorities.  "
        "2-101. The Administrator shall coordinate responses."
    )
    sections = [seg.text for seg in segment(text) if seg.seg_type == "section"]
    assert sections == [
        "1-1. National Contingency Plan.",
        "1-101. The plan shall be the primary vehicle for coordination.",
        "1-102. The Chairman is delegated authority.",
        "2-1. Response Authorities.",
        "2-101. The Administrator shall coordinate responses.",
    ]


def test_hyphen_numbered_subsections_merge_with_parent_for_display():
    text = (
        "By authority vested in me, it is hereby ordered as follows:  "
        "1-1. National Contingency Plan.  "
        "1-101. The plan shall be the primary vehicle for coordination.  "
        "1-102. The Chairman is delegated authority.  "
        "2-1. Response Authorities.  "
        "2-101. The Administrator shall coordinate responses."
    )
    sections = [seg.text for seg in segment(text, split_subsections=False) if seg.seg_type == "section"]
    assert sections == [
        (
            "1-1. National Contingency Plan. "
            "1-101. The plan shall be the primary vehicle for coordination. "
            "1-102. The Chairman is delegated authority."
        ),
        "2-1. Response Authorities. 2-101. The Administrator shall coordinate responses.",
    ]


def test_purpose_and_definitions_sections_are_order_actions():
    text = (
        "Section 1. Purpose. The Board shall perform the work.  "
        "Section 2. Definitions. The agency shall make determinations."
    )
    actions = [seg.text for seg in segment_ordering(text) if seg.seg_type == "order_action"]
    assert actions == [
        "The Board shall perform the work. Section 2. Definitions.",
        "The agency shall make determinations.",
    ]


def test_section_continuation_after_vesting_is_order_action():
    text = (
        "Section 1. First section. The Board shall perform the work.  "
        "Sec. 2. Senior Executive Service.  "
        "Pursuant to section 5382 of title 5, United States Code, "
        "the rates of basic pay are set forth on Schedule 4."
    )
    segments = segment_ordering(text)
    continuation = [
        seg for seg in segments
        if seg.text.startswith("the rates of basic pay")
    ]
    assert len(continuation) == 1
    assert continuation[0].seg_type == "order_action"


def test_extension_splits_unstructured_documents():
    text = "Background context. The Board shall perform the work."
    segments = segment_ordering(text)
    assert [(seg.seg_type, seg.text) for seg in segments] == [
        ("preamble", "Background context."),
        ("order_action", "The Board shall perform the work."),
    ]


def test_strict_wp_disables_section_extension():
    assert _section_type("perform", strict_wp=True) == "preamble"


def test_original_wp_phrase_still_matches_in_strict_mode():
    assert _section_type("provide procedures", strict_wp=True) == "order_action"


def _vesting_texts(text: str) -> list[str]:
    return [seg.text for seg in segment_ordering(text) if seg.seg_type == "vesting_clause"]


def test_sample_100_opening_authority_phrases_are_vesting_clauses():
    cases = (
        (
            "Under the authority granted to me in section 12(a) of the Outer Continental "
            "Shelf Lands Act, 43 U.S.C. 1341(a), I hereby withdraw the area.",
            "Under the authority granted to me in section 12(a) of the Outer Continental "
            "Shelf Lands Act, 43 U.S.C. 1341(a),",
        ),
        (
            "Pursuant to section 2(c)(1) of the Migration and Refugee Assistance Act of 1962, "
            "22 U.S.C. 2601(c)(1), I hereby determine that funds be made available.",
            "Pursuant to section 2(c)(1) of the Migration and Refugee Assistance Act of 1962, "
            "22 U.S.C. 2601(c)(1),",
        ),
    )
    for text, expected in cases:
        assert _vesting_texts(text) == [expected]


def test_mid_sentence_pursuant_clause_is_vesting():
    text = (
        "In accordance with section 6(b) of the Consolidated Appropriations Act, 2020, "
        "I hereby designate all funding so designated by the Congress in these Acts "
        "pursuant to section 251(b)(2)(A) of the Balanced Budget and Emergency Deficit "
        "Control Act of 1985, as outlined in the enclosed list of accounts."
    )
    segments = segment_ordering(text)
    assert [(seg.seg_type, seg.text) for seg in segments] == [
        (
            "order_action",
            "In accordance with section 6(b) of the Consolidated Appropriations Act, 2020, "
            "I hereby designate all funding so designated by the Congress in these Acts",
        ),
        (
            "vesting_clause",
            "pursuant to section 251(b)(2)(A) of the Balanced Budget and Emergency Deficit "
            "Control Act of 1985,",
        ),
        ("order_action", "as outlined in the enclosed list of accounts."),
    ]


def test_inline_citation_continuations_stay_in_vesting_clause():
    text = (
        "I hereby determine the action pursuant to section 2(c) of the Migration Act of "
        "1962, as amended, 22 U.S.C. 2601(c), and direct publication."
    )
    assert [(seg.seg_type, seg.text) for seg in segment_ordering(text)] == [
        ("order_action", "I hereby determine the action"),
        (
            "vesting_clause",
            "pursuant to section 2(c) of the Migration Act of 1962, as amended, "
            "22 U.S.C. 2601(c),",
        ),
        ("order_action", "and direct publication."),
    ]


def test_year_inside_inline_act_citation_is_not_a_boundary():
    text = (
        "I hereby designate funding pursuant to section 6 of the Consolidated "
        "Appropriations Act, 2020, for overseas operations."
    )
    assert _vesting_texts(text) == [
        "pursuant to section 6 of the Consolidated Appropriations Act, 2020,"
    ]


def test_opening_authority_carve_stops_after_statutory_citation_comma():
    text = (
        "Pursuant to section 5382 of title 5, United States Code, "
        "the rates of basic pay are set forth on Schedule 4."
    )
    assert [(seg.seg_type, seg.text) for seg in segment_ordering(text)] == [
        (
            "vesting_clause",
            "Pursuant to section 5382 of title 5, United States Code,"
        ),
        ("preamble", "the rates of basic pay are set forth on Schedule 4."),
    ]


def test_opening_authority_carve_stops_after_public_law_comma():
    text = (
        "Pursuant to section 601 of Public Law 102 - 190, "
        "the rates of monthly basic pay are set forth at Schedule 8."
    )
    assert [(seg.seg_type, seg.text) for seg in segment_ordering(text)] == [
        ("vesting_clause", "Pursuant to section 601 of Public Law 102 - 190,"),
        ("preamble", "the rates of monthly basic pay are set forth at Schedule 8."),
    ]


def test_ordering_formula_carve_still_keeps_full_opening_authority_list():
    text = (
        "By the authority vested in me as President by the Constitution and the laws "
        "of the United States of America, including section 601 of Public Law 102 - 190; "
        "and section 461(a) of title 28, United States Code, it is hereby ordered as follows:"
    )
    assert [(seg.seg_type, seg.text) for seg in segment_ordering(text)] == [
        (
            "vesting_clause",
            "By the authority vested in me as President by the Constitution and the laws "
            "of the United States of America, including section 601 of Public Law 102 - 190; "
            "and section 461(a) of title 28, United States Code,"
        ),
        ("ordering_phrase", "it is hereby ordered as follows:"),
    ]


def test_cabinet_mid_sentence_pursuant_clause_is_not_vesting():
    text = "The Secretary shall, pursuant to section 5 of the Trade Act, submit reports."
    assert _vesting_texts(text) == []


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"  PASS  {test.__name__}")
    print(f"\n{len(tests)} passed")
