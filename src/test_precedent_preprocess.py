"""Tests for authority masking and shared similarity preprocessing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from precedent_preprocess import mask_authorities, preprocess_for_similarity


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


def test_masks_named_act_and_executive_order():
    masked, _ = mask_authorities(
        "Under the International Emergency Economic Powers Act and Executive Order 12345."
    )
    assert masked == "Under [AUTHORITY] and [AUTHORITY]."


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


def test_retains_findings_and_definitions():
    text = (
        "Section 1. Findings. The Nation faces an unusual threat.  "
        "Sec. 2. Definitions. Agency means an executive department."
    )
    cleaned, _, removed = preprocess_for_similarity(text)
    assert cleaned == text
    assert removed == []


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"  PASS  {test.__name__}")
    print(f"\n{len(tests)} passed")
