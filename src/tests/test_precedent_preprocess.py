"""Tests for authority masking and shared similarity preprocessing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from precedent_preprocess import (
    mask_authorities, preprocess_for_similarity, preprocess_for_similarity_detailed,
)


def test_masks_authorities_but_preserves_connectors():
    masked, spans = mask_authorities(
        "By the authority vested in me by the Constitution and pursuant to "
        "section 301 of title 3, United States Code, I hereby order."
    )
    assert masked == (
        "By the authority vested in me by [AUTHORITY] and pursuant to "
        "[AUTHORITY], I hereby order."
    )
    assert [span.kind for span in spans] == ["constitution", "usc_section"]


def test_masks_usc_section_with_of_the_before_code_name():
    citation = "section 301 of title 3 of the United States Code"
    masked, spans = mask_authorities(citation)
    assert masked == "[AUTHORITY]"
    assert len(spans) == 1
    assert spans[0].kind == "usc_section"
    assert spans[0].text == citation


def test_masks_named_act_and_executive_order():
    masked, _ = mask_authorities(
        "Under the International Emergency Economic Powers Act and Executive Order 12345."
    )
    assert masked == "Under [AUTHORITY] and [AUTHORITY]."


def test_masks_revised_statutes_and_dated_act_authorities():
    text = (
        "By authority of section 1753 of the Revised Statutes of the United States "
        "and the act of August 26, 1950, the Secretary shall act."
    )
    masked, spans = mask_authorities(text)
    assert "1753 of the Revised Statutes" not in masked
    assert "act of August 26, 1950" not in masked
    assert "the Secretary shall act" in masked
    assert {span.kind for span in spans} >= {"revised_statutes_section", "dated_act"}


def test_masks_other_directive_references():
    masked, spans = mask_authorities(
        "Under Proclamation 9984, PPD-41, my memorandum of March 31, 2010, "
        'and the letter entitled "Report to the Congress".'
    )
    assert masked == "Under [AUTHORITY], [AUTHORITY], my [AUTHORITY], and the [AUTHORITY]."
    assert [span.kind for span in spans] == [
        "proclamation",
        "numbered_memorandum",
        "dated_unnumbered_directive",
        "titled_unnumbered_directive",
    ]


def test_does_not_mask_internal_section_reference():
    masked, spans = mask_authorities("The Secretary shall act under section 2 of this order.")
    assert masked == "The Secretary shall act under section 2 of this order."
    assert spans == []


def test_removes_only_recurring_general_provisions_language():
    text = (
        "Sec. 1. The Secretary shall establish a program.  "
        "Sec. 2. General Provisions. (a) Nothing in this order shall be construed "
        "to impair or otherwise affect:  "
        "(i) the authority granted by law to an executive department or agency; or  "
        "(ii) the functions of the Director of the Office of Management and Budget.  "
        "(d) The Secretary shall issue EO-specific guidance."
    )
    cleaned, _, removed = preprocess_for_similarity(text)
    assert "establish a program" in cleaned
    assert "EO-specific guidance" in cleaned
    assert "Nothing in this order" not in cleaned
    assert "authority granted by law" not in cleaned
    assert len(removed) == 3


def test_removes_severability_clause():
    text = (
        "The agency shall act.  If any provision of this order is held invalid, "
        "the remainder of this order shall not be affected."
    )
    cleaned, _, removed = preprocess_for_similarity(text)
    assert cleaned == "The agency shall act."
    assert len(removed) == 1


def test_removes_non_eo_limitation_and_severability_language():
    text = (
        "The Secretary shall establish a program.  "
        "This memorandum shall be implemented consistent with applicable law.  "
        "If any provision of this proclamation is held invalid, "
        "the remainder shall not be affected."
    )
    cleaned, _, removed = preprocess_for_similarity(text)
    assert cleaned == "The Secretary shall establish a program."
    assert len(removed) == 2


def test_retains_findings_and_definitions():
    text = (
        "Section 1. Findings. The Nation faces an unusual threat.  "
        "Sec. 2. Definitions. Agency means an executive department."
    )
    cleaned, _, removed = preprocess_for_similarity(text)
    assert cleaned == text
    assert removed == []


def test_removes_full_vesting_clause_but_keeps_operative_connector():
    result = preprocess_for_similarity_detailed(
        "By the authority vested in me as President by the Constitution and "
        "50 U.S.C. 1701, it is hereby ordered:  The Secretary shall act."
    )
    assert result.text == "it is hereby ordered:  The Secretary shall act."
    assert "authority vested" not in result.text.casefold()
    assert len(result.removed_vesting_clauses) == 1
    assert "50 U.S.C. 1701" in result.removed_vesting_clauses[0]


def test_removes_vesting_clause_with_usc_of_the_wording():
    result = preprocess_for_similarity_detailed(
        "By virtue of the authority vested in me by section 301 of title 3 of the "
        "United States Code, I hereby delegate the following functions."
    )
    assert result.text == "I hereby delegate the following functions."
    assert len(result.removed_vesting_clauses) == 1
    assert (
        "section 301 of title 3 of the United States Code"
        in result.removed_vesting_clauses[0]
    )


def test_removes_vesting_clause_when_connector_starts_next_source_paragraph():
    result = preprocess_for_similarity_detailed(
        "By virtue of the authority vested in me by the Constitution,  "
        "I hereby proclaim that imports are restricted."
    )
    assert result.text == "I hereby proclaim that imports are restricted."
    assert len(result.removed_vesting_clauses) == 1


def test_removes_standalone_vesting_clause_after_an_uppercase_title():
    result = preprocess_for_similarity_detailed(
        "PROGRAM ADMINISTRATION  By the authority vested in me by the Constitution,  "
        "Section 1. The Secretary shall establish a program."
    )
    assert result.text == "PROGRAM ADMINISTRATION  Section 1. The Secretary shall establish a program."


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"  PASS  {test.__name__}")
    print(f"\n{len(tests)} passed")
