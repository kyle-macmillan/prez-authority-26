import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from ceremonial import ceremonial_reason, is_ceremonial


def row(document_type: str, text: str, title: str = "") -> dict:
    return {"doc_type": document_type, "doc_text": text, "title": title, "url": ""}


def test_observance_proclamation_is_ceremonial():
    item = row(
        "proclamation",
        "I do hereby proclaim May 1, 2026, as National Service Day.",
    )
    assert ceremonial_reason(item) == "observance_designation"


def test_observance_reference_does_not_exclude_other_directive_types():
    item = row("memorandum", "The agency shall report on National Service Day programs.")
    assert not is_ceremonial(item)


def test_strong_symbolic_actions_apply_to_all_directive_types():
    assert ceremonial_reason(row(
        "executive_order", "The flag shall be flown at half-staff for the late Justice."
    )) == "memorial_half_staff"
    assert ceremonial_reason(row(
        "executive_order",
        "There is hereby established an official seal for the agency.",
        "Establishing a Seal for the Agency",
    )) == "symbol_design"
    assert ceremonial_reason(row(
        "memorandum", "I call upon all Americans to commemorate this anniversary."
    )) == "public_commemoration"
    assert ceremonial_reason(row(
        "executive_order", "Eligibility is amended.", "Expanding the Service Medal"
    )) == "symbolic_honor"


def test_substantive_vetoes_override_symbolic_phrases():
    item = row(
        "proclamation",
        "I do hereby proclaim this action as Trade Week and modify the Harmonized Tariff Schedule.",
    )
    assert not is_ceremonial(item)
