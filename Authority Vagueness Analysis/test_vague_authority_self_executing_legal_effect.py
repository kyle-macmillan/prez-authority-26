"""Tests for vague-authority self-executing legal effect rules."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from vague_authority_self_executing_legal_effect import classify_self_executing_legal_effect


def category(text: str, doc_type: str = "executive_order") -> str:
    return classify_self_executing_legal_effect(text, doc_type)[0]


def test_tariff_import_hts_changes_are_self_executing():
    assert category(
        "The Harmonized Tariff Schedule of the United States (HTSUS) is modified "
        "to increase duties on imports of these articles."
    ) == "self_executing_legal_effect"


def test_immigration_entry_restrictions_are_self_executing():
    assert category(
        "The entry of certain immigrants and nonimmigrants into the United States "
        "is hereby suspended and restricted."
    ) == "self_executing_legal_effect"


def test_property_blocking_or_transaction_prohibitions_are_self_executing():
    assert category(
        "All property and interests in property are blocked and may not be "
        "transferred, paid, exported, withdrawn, or otherwise dealt in."
    ) == "self_executing_legal_effect"
    assert category(
        "All transactions by United States persons involving these entities are prohibited."
    ) == "self_executing_legal_effect"


def test_agency_reporting_review_coordination_is_not_self_executing():
    assert category(
        "The Secretary shall review existing programs, coordinate with agencies, "
        "and submit a report to the President within 180 days."
    ) == "not_self_executing_legal_effect"


def test_ceremonial_proclamations_are_not_self_executing():
    assert category(
        "I do hereby proclaim May 1 as Loyalty Day, and I call upon the people "
        "of the United States to observe that day with appropriate ceremonies.",
        "proclamation",
    ) == "not_self_executing_legal_effect"


def test_commission_or_task_force_establishment_is_internal_management():
    assert category(
        "There is established a council to advise the President on policy matters."
    ) == "not_self_executing_legal_effect"
    assert category(
        "There is hereby established an Interagency Task Force on market competition."
    ) == "not_self_executing_legal_effect"


def test_legal_instrument_status_changes_are_self_executing():
    assert category(
        "Executive Order 12345 is hereby revoked."
    ) == "self_executing_legal_effect"
    assert category(
        "The designation of the monument is hereby modified."
    ) == "self_executing_legal_effect"


def test_funding_and_eligibility_consequences_are_self_executing():
    assert category(
        "No federal funds shall be made available to entities that violate this order."
    ) == "self_executing_legal_effect"
    assert category(
        "Covered contractors are hereby ineligible for federal benefits."
    ) == "self_executing_legal_effect"


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"  PASS  {test.__name__}")
    print(f"\n{len(tests)} passed")
