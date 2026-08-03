"""Tests for deterministic generic vesting-authority classification."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

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


def test_ocr_code_citation_does_not_truncate_vesting_clause():
    clauses = extract_vesting_clauses(
        "By virtue of the authority vested in me by sections 55 (a), 508, 603, 729 (a), "
        "and 1204 of the Internal Revenue Code of 1939 (53 Stat. 29, 111, 171; 54 Stat. "
        "989, 1008; 55 Stat. 722; 26 13. S. C. 55 (a), 508, 603, 729 (a), and 1204), "
        "and by section 6103 (a) of the Internal Revenue Code of 1954 (68A Stat. 753; "
        "26 U.S.C. 6103 (a)), it is hereby ordered that the returns shall be open.",
        "executive_order",
    )
    assert clauses == [
        "By virtue of the authority vested in me by sections 55 (a), 508, 603, 729 (a), "
        "and 1204 of the Internal Revenue Code of 1939 (53 Stat. 29, 111, 171; 54 Stat. "
        "989, 1008; 55 Stat. 722; 26 13. S. C. 55 (a), 508, 603, 729 (a), and 1204), "
        "and by section 6103 (a) of the Internal Revenue Code of 1954 (68A Stat. 753; "
        "26 U.S.C. 6103 (a)),"
    ]


def test_reviewed_historical_and_post_ordering_vesting_clauses():
    cases = [
        (
            "By virtue of and pursuant to the authority vested in the President by section 18 "
            "of the Pay Readjustment Act of 1942 (56 Stat. 368), and for the purpose of carrying "
            "into effect certain provisions of section 14 of the said Act as amended by section 3 "
            "of the act of March 25, 1948 Public Law 460, 80th Congress, Executive Order No. 9195 "
            "of July 7, 1942, as amended, prescribing regulations, is hereby further amended.",
            "executive_order",
            "By virtue of and pursuant to the authority vested in the President by section 18 "
            "of the Pay Readjustment Act of 1942 (56 Stat. 368), and for the purpose of carrying "
            "into effect certain provisions of section 14 of the said Act as amended by section 3 "
            "of the act of March 25, 1948 Public Law 460, 80th Congress, Executive Order No. 9195 "
            "of July 7, 1942",
        ),
        (
            "It is hereby ordered, pursuant to the provisions of Section 4 of Proclamation 3044 "
            "of March 1, 1954, that the flag shall be flown at half-staff.",
            "executive_order",
            "pursuant to the provisions of Section 4 of Proclamation 3044 of March 1, 1954,",
        ),
        (
            "It is hereby ordered, pursuant to the provisions of Section 4 of Proclamation 3044 "
            "of March 1, 1954, as amended, that the flag shall be flown at half-staff.",
            "executive_order",
            "pursuant to the provisions of Section 4 of Proclamation 3044 of March 1, 1954,",
        ),
        (
            "I hereby order, by virtue of the authority vested in me as President of the United "
            "States of America by Section 175 of Title 36 of the United States Code, that the flag "
            "shall be flown at half-staff.",
            "proclamation",
            "by virtue of the authority vested in me as President of the United States of America "
            "by Section 175 of Title 36 of the United States Code,",
        ),
        (
            "I hereby order, by virtue of the authority vested in me as President of the United "
            "States of America, that the flag shall be flown at half-staff.",
            "proclamation",
            "by virtue of the authority vested in me as President of the United States of America,",
        ),
        (
            "I hereby order, by the authority vested in me as President of the United States of "
            "America by section 175 of title 36 of the United States Code, that the flag shall be "
            "flown at half-staff.",
            "proclamation",
            "by the authority vested in me as President of the United States of America by section "
            "175 of title 36 of the United States Code,",
        ),
        (
            "I hereby order, by the authority vested in me as President by the Constitution and "
            "the laws of the United States of America, that the flag shall be flown at half-staff.",
            "proclamation",
            "by the authority vested in me as President by the Constitution and the laws of the "
            "United States of America,",
        ),
        (
            "Memorandum for the Secretary Subject: Delegation of Authority Under Section 1424 "
            "By the authority vested in my by the Constitution and the laws of the United States "
            "of America, including section 301 of title 3 of the United States Code, I hereby "
            "delegate the function.",
            "memorandum",
            "By the authority vested in my by the Constitution and the laws of the United States "
            "of America, including section 301 of title 3 of the United States Code,",
        ),
        (
            "Pursuant to my constitutional authority to conduct the foreign relations of the "
            "United States, I have determined that deportation should be deferred.",
            "memorandum",
            "Pursuant to my constitutional authority to conduct the foreign relations of the "
            "United States,",
        ),
        (
            "By virtue of my authority as President of the United States of America, and in "
            "order to promote equality for women, it is hereby ordered as follows.",
            "executive_order",
            "By virtue of my authority as President of the United States of America",
        ),
        (
            "Therefore, pursuant to my authority to regulate federal employment, I have "
            "determined that agencies may receive applications from these individuals.",
            "memorandum",
            "pursuant to my authority to regulate federal employment,",
        ),
        (
            "In relation to the agreement, pursuant to my authority under subsection 405(b)(1) "
            "of the Trade Act of 1974 (19 U.S.C. 2435(b)(1)), I reconfirm that a satisfactory "
            "balance of concessions has been maintained.",
            "memorandum",
            "pursuant to my authority under subsection 405(b)(1) of the Trade Act of 1974 "
            "(19 U.S.C. 2435(b)(1)),",
        ),
        (
            "Pursuant to my authority as Commander in Chief, I hereby approve and direct the "
            "implementation of the revised Unified Command Plan.",
            "memorandum",
            "Pursuant to my authority as Commander in Chief,",
        ),
        (
            "Based on a petition submitted by the Governor, pursuant to Section 110(f) of the "
            "Clean Air Act, I hereby determine that a regional energy emergency exists.",
            "memorandum",
            "pursuant to Section 110(f) of the Clean Air Act,",
        ),
        (
            "Thus, pursuant to section 1106(a) of the 1988 Act, I determine that state trading "
            "enterprises do not account for a significant share of exports.",
            "memorandum",
            "pursuant to section 1106(a) of the 1988 Act,",
        ),
        (
            "Presidential Determination No. 98-34 Memorandum for the Secretary of State Subject: "
            "Assistance to Kosovo Pursuant to section 2(c)(1) of the Migration and Refugee "
            "Assistance Act of 1962, as amended, 22 U.S.C. 2601(c)(1), I hereby determine that "
            "it is important to the national interest to make funds available.",
            "memorandum",
            "Pursuant to section 2(c)(1) of the Migration and Refugee Assistance Act of 1962, "
            "as amended, 22 U.S.C. 2601(c)(1),",
        ),
        (
            "Presidential Determination No. 97-24 Memorandum for the Secretary of State Subject: "
            "Assistance to Turkey Pursuant to subsection (b) of section 620I of the Foreign "
            "Assistance Act of 1961, as amended, I hereby determine that assistance should be "
            "furnished to Turkey.",
            "memorandum",
            "Pursuant to subsection (b) of section 620I of the Foreign Assistance Act of 1961, "
            "as amended,",
        ),
        (
            "I find that exemption is in the paramount interest of the United States. Therefore, "
            "pursuant to 42 U.S.C. § 6961(a), I hereby exempt the Air Force operating location "
            "from requirements that would disclose classified information.",
            "memorandum",
            "pursuant to 42 U.S.C. § 6961(a),",
        ),
    ]
    for text, doc_type, expected in cases:
        assert extract_vesting_clauses(text, doc_type) == [expected]


def test_reviewed_action_reports_remain_without_vesting_clauses():
    assert extract_vesting_clauses(
        "This is to inform you that, pursuant to Section 22 of the Agricultural Adjustment Act "
        "of 1933, as amended, I have modified the quotas established in another directive.",
        "letter",
    ) == []
    assert extract_vesting_clauses(
        "Section 1105 requires the President to determine whether concessions were made. "
        "I hereby determine that there has been no failure to make concessions.",
        "memorandum",
    ) == []
    assert extract_vesting_clauses(
        "Subject: Determination Pursuant to Section 207(b) of the Act In accordance with "
        "section 207(b) of the Act, I hereby determine that an emergency exists.",
        "memorandum",
    ) == []


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
