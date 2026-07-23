"""Tests for deterministic generic vesting-authority classification."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from vesting_authority_stats import classify_vesting_clauses, extract_vesting_clauses


def classify(*clauses: str) -> bool:
    return classify_vesting_clauses(list(clauses))[0]


def test_constitution_alone_qualifies():
    assert classify("By the authority vested in me by the Constitution, I hereby order")


def test_formal_presidential_title_invocation_qualifies():
    assert classify("I, Joseph R. Biden, Jr., President of the United States of America")
    assert classify("I, DONALD J. TRUMP, President of the United States")


def test_incidental_as_president_prose_does_not_qualify():
    assert not classify("I, as President, have the power of appointment")


def test_laws_alone_qualify():
    assert classify("By the authority vested in me by laws of the United States of America")
    assert classify("By the authority vested in me by the law of the United States")


def test_combined_generic_authorities_qualify():
    assert classify("By the Constitution and the laws of the United States, I hereby order")


def test_statutes_alone_do_not_qualify():
    assert not classify("By the authority vested in me by the statutes of the United States")


def test_specific_statute_disqualifies():
    assert not classify(
        "By the Constitution and laws of the United States, including the Defense Production Act"
    )
    assert not classify("By the Constitution and 3 U.S.C. 301")
    assert not classify("By the laws of the United States, including section 2 of title 10")
    assert not classify(
        "Pursuant to 3 U.S.C. 301, I, Example Person, President of the United States"
    )


def test_specific_constitutional_power_disqualifies():
    assert not classify("By the Constitution, including my authority as Commander in Chief")
    assert not classify("By the Constitution, including Article II")


def test_other_named_legal_authority_disqualifies():
    assert not classify("By the laws of the United States and Executive Order 12345")
    assert not classify("By the Constitution and the Paris Agreement")
    assert not classify("By the Constitution and the Treaty of Example")
    assert not classify("By the Constitution and the Geneva Conventions")
    assert not classify('By the Constitution and division A of H.R. 4346 (the "Act")')
    assert not classify("By the Constitution and the International Covenant on Civil Rights")
    assert not classify("By the Constitution and the Convention Against Torture")
    assert not classify("By the Constitution and the Treaty")


def test_generic_legal_language_does_not_disqualify():
    assert classify("By the Constitution and laws of the United States and applicable law")
    assert classify("By the Constitution and the authority granted by law")


def test_specific_authority_in_another_vesting_clause_disqualifies_document():
    assert not classify(
        "By the Constitution, I hereby order",
        "By the authority vested in me by the Example Act, I hereby order",
    )


def test_extracts_only_vesting_clause_prefix():
    clauses = extract_vesting_clauses(
        "By the authority vested in me by the Constitution, it is hereby ordered as follows:  "
        "Section 1. The agency shall act.",
        "executive_order",
    )
    assert clauses == ["By the authority vested in me by the Constitution,"]


def test_comma_in_ordering_formula_still_ends_vesting_clause():
    clauses = extract_vesting_clauses(
        "By virtue of the authority vested in me by the Constitution and laws, "
        "it is hereby, ordered as follows: SECTION 1.",
        "executive_order",
    )
    assert clauses == ["By virtue of the authority vested in me by the Constitution and laws"]


def test_policy_cross_reference_is_not_a_vesting_clause():
    clauses = extract_vesting_clauses(
        "By the authority vested in me by the Constitution, it is hereby ordered as follows:  "
        "Consistent with the policy in section 1 of this order, the agency shall act.",
        "executive_order",
    )
    assert clauses == ["By the authority vested in me by the Constitution,"]


def test_proclamation_recitals_are_not_part_of_vesting_invocation():
    clauses = extract_vesting_clauses(
        "Whereas the Constitution protects liberty; and Whereas Congress acted: "
        "Now, Therefore, I, Example President, do hereby proclaim this day.",
        "proclamation",
    )
    assert clauses == ["Now, Therefore, I, Example President,"]


def test_extracts_formal_presidential_title_invocation():
    clauses = extract_vesting_clauses(
        "I, Example Person, President of the United States of America, do hereby proclaim today.",
        "proclamation",
    )
    assert clauses == ["I, Example Person, President of the United States of America"]


def test_formal_invocation_keeps_preceding_specific_authority():
    clauses = extract_vesting_clauses(
        "Pursuant to 3 U.S.C. 301, I, Example Person, President of the United States, "
        "do hereby proclaim today.",
        "proclamation",
    )
    assert clauses == [
        "Pursuant to 3 U.S.C. 301, I, Example Person, President of the United States,"
    ]


def test_pursuant_to_opener_without_presidential_i_is_extracted():
    # "Pursuant to [law]" at sentence start should be captured even with no standalone "I".
    # The comma after the law citation is the carve cut point (before the ordering phrase).
    clauses = extract_vesting_clauses(
        "Pursuant to section 301 of the Trade Act of 1974, it is hereby ordered as follows:  "
        "Actions shall be taken.",
        "executive_order",
    )
    assert clauses == ["Pursuant to section 301 of the Trade Act of 1974,"]


def test_opening_authority_after_metadata_is_extracted():
    clauses = extract_vesting_clauses(
        "Memorandum for the Secretary  Subject: Example  "
        "Under the authority granted to me in section 12(a) of the Example Act, "
        "43 U.S.C. 1341(a), I hereby withdraw the area.",
        "memorandum",
    )
    assert clauses == [
        "Under the authority granted to me in section 12(a) of the Example Act, "
        "43 U.S.C. 1341(a),"
    ]


def test_mid_sentence_pursuant_authority_is_extracted():
    clauses = extract_vesting_clauses(
        "I hereby designate the funding pursuant to section 251(b)(2)(A) of the "
        "Budget Control Act of 1985, as described in the enclosed list.",
        "letter",
    )
    assert clauses == [
        "pursuant to section 251(b)(2)(A) of the Budget Control Act of 1985,"
    ]


def test_pursuant_to_opener_classifies_as_specific_authority():
    # A "Pursuant to [specific law]" opener cites a specific authority, so qualifies=False.
    assert not classify("Pursuant to section 301 of the Trade Act of 1974,")


def test_consistent_with_opener_is_not_a_vesting_clause():
    # "Consistent with" signals non-disagreement, not statutory authorization.
    clauses = extract_vesting_clauses(
        "Consistent with section 401(c) of the National Emergencies Act, the President "
        "hereby directs the following actions.",
        "executive_order",
    )
    assert clauses == []


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"  PASS  {test.__name__}")
    print(f"\n{len(tests)} passed")
