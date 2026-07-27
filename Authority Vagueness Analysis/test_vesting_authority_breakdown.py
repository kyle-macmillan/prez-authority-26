"""Tests for document-level vesting-authority specificity categories."""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from vesting_authority_breakdown import (
    CATEGORIES,
    CATEGORY_LABELS,
    VIEWS,
    classify_authority_category,
    extract_authority_spans,
    render_html,
)
from export_vesting_authority_categories_xlsx import worksheet_xml


def category(*clauses: str) -> str:
    return classify_authority_category(list(clauses))


def test_generic_categories_are_distinct_and_exclusive():
    assert category("By the authority vested in me by the Constitution,") == (
        "generic_constitution_only"
    )
    assert category("By the authority vested in me by law,") == "generic_statute_only"
    assert category(
        "By the authority vested in me by the Constitution and statutes of the United States,"
    ) == "generic_constitution_and_generic_statute"


def test_combined_formula_accepts_singular_and_ocr_variants():
    assert category(
        "By the authority vested in me by the Constitution and the law of the United States of America,"
    ) == "generic_constitution_and_generic_statute"
    assert category(
        "By the authority vested in me by the Constitutuion and the laws of the United States,"
    ) == "generic_constitution_and_generic_statute"
    assert category(
        "By the authority vested in me by the Constutition and statutes of the United States,"
    ) == "generic_constitution_and_generic_statute"
    assert category(
        "By the authority vested in me by the Constitutioin and laws of the United States,"
    ) == "generic_constitution_and_generic_statute"
    assert category(
        "By the authority vested in me by the Cosntitution and laws of the United States,"
    ) == "generic_constitution_and_generic_statute"
    assert category(
        "By the authority vested in me by the Constitution and the statues of the United States,"
    ) == "generic_constitution_and_generic_statute"


def test_specific_constitution_supersedes_generic_wording():
    assert category(
        "By the authority vested in me by the Constitution, including Article II of the Constitution,"
    ) == "specific_constitution_only"
    assert category(
        "Pursuant to authority vested in me as the Chief Executive Officer of the United States,"
    ) == "specific_constitution_only"


def test_specific_constitutional_provision_supersedes_article():
    assert category(
        "Pursuant to my powers under Article II, Section 2, of the Constitution,"
    ) == "specific_constitutional_provision_only"
    assert category(
        "By virtue of authority vested in me by Section 2 of Article II of the Constitution,"
    ) == "specific_constitutional_provision_only"
    assert category(
        "Pursuant to my constitutional authority as Commander-in-Chief and Chief Executive,"
    ) == "specific_constitutional_provision_only"


def test_all_specificity_combinations_are_mutually_exclusive():
    cases = {
        "generic_constitution_only": (
            "By the authority vested in me by the Constitution,"
        ),
        "specific_constitution_only": (
            "By the authority vested in me by Article II of the Constitution,"
        ),
        "specific_constitutional_provision_only": (
            "By the authority vested in me as Commander in Chief,"
        ),
        "generic_statute_only": (
            "By the authority vested in me by the laws of the United States,"
        ),
        "act_of_congress_only": (
            "By the authority vested in me by the Example Act,"
        ),
        "specific_statutory_section_only": (
            "By the authority vested in me by section 301 of title 3, United States Code,"
        ),
        "generic_constitution_and_generic_statute": (
            "By the authority vested in me by the Constitution and laws of the United States,"
        ),
        "generic_constitution_and_act_of_congress": (
            "By the authority vested in me by the Constitution and the Example Act,"
        ),
        "generic_constitution_and_specific_statutory_section": (
            "By the authority vested in me by the Constitution and section 301 of title 3, "
            "United States Code,"
        ),
        "specific_constitution_and_generic_statute": (
            "By the authority vested in me by Article II of the Constitution and under the "
            "laws of the United States,"
        ),
        "specific_constitution_and_act_of_congress": (
            "By the authority vested in me by Article II of the Constitution and the Example Act,"
        ),
        "specific_constitution_and_specific_statutory_section": (
            "By the authority vested in me by Article II of the Constitution and section 301 "
            "of title 3, United States Code,"
        ),
        "specific_constitutional_provision_and_generic_statute": (
            "By the authority vested in me as Commander in Chief and under the laws of the "
            "United States,"
        ),
        "specific_constitutional_provision_and_act_of_congress": (
            "By the authority vested in me as Commander in Chief and by the Example Act,"
        ),
        "specific_constitutional_provision_and_specific_statutory_section": (
            "By the authority vested in me as Commander in Chief and by section 301 of title 3, "
            "United States Code,"
        ),
    }
    assert set(cases) == set(CATEGORIES) - {"no_vesting_clause", "other_vesting_authority"}
    for expected, clause in cases.items():
        assert category(clause) == expected


def test_named_clause_in_purpose_tail_does_not_supersede_boilerplate():
    clause = (
        "By the authority vested in me as President by the Constitution and laws of the "
        "United States of America, and in order to ensure due regard for obligations imposed "
        "by the Just Compensation Clause of the Fifth Amendment,"
    )
    assert category(clause) == "generic_constitution_and_generic_statute"


def test_specific_statutory_section_supersedes_act_and_boilerplate():
    clause = (
        "By the authority vested in me by the Constitution and the laws of the United States, "
        "including the National Emergencies Act (50 U.S.C. 1601 et seq.), and section 301 "
        "of title 3, United States Code,"
    )
    assert category(clause) == "generic_constitution_and_specific_statutory_section"


def test_statutory_section_ocr_and_code_forms():
    assert category(
        "Under the authority granted to me in section 12(a) of the Example Act, 43 U S.C. 1341(a),"
    ) == "specific_statutory_section_only"
    assert category(
        "Pursuant to chapter 10 of title 5, United States Code,"
    ) == "specific_statutory_section_only"
    assert category(
        "By authority vested in me by the Uniform Code of Military Justice (10 U.S.C., ch. 47),"
    ) == "specific_statutory_section_only"


def test_compliance_and_purpose_citations_are_excluded():
    assert category(
        "By the authority vested in me by the Constitution and statutes of the United States, "
        "and in accordance with the Federal Advisory Committee Act (5 U.S.C., App.),"
    ) == "generic_constitution_and_generic_statute"
    assert category(
        "Pursuant to authority vested in me as the Chief Executive Officer of the United States, "
        "and consistent with the Hatch Act Reform Amendment regulations, 5 CFR 734.104, "
        "and section 301 of title 3, United States Code,"
    ) == "specific_constitution_only"
    assert category(
        "By the authority vested in me by the Constitution and laws of the United States, "
        "and in order to implement Public Law 117-169,"
    ) == "generic_constitution_and_generic_statute"


def test_including_is_authority_but_in_furtherance_is_not():
    clause = (
        "By the authority vested in me by the Constitution and laws of the United States, "
        "including the National Emergencies Act (50 U.S.C. 1601 et seq.), and in furtherance "
        "of Proclamation 9994,"
    )
    assert category(clause) == "generic_constitution_and_specific_statutory_section"


def test_authorizing_proclamation_recital_ignores_constitutional_history():
    clause = (
        "joint resolution proposing an amendment to the Constitution; Whereas the resolution "
        "led to adoption of the Thirteenth Amendment; and Whereas, by a joint resolution "
        "approved June 30, 1948, the Congress authorized the President to proclaim February 1 "
        "as National Freedom Day; Now, Therefore, I, Harry S. Truman, President of the United States,"
    )
    assert category(clause) == "act_of_congress_only"
    assert category(
        "Whereas those resolutions of the Congress authorize the President to issue annually "
        "a proclamation for Citizenship Day and Constitution Week; Now, Therefore, I proclaim,"
    ) == "act_of_congress_only"


def test_contextual_pursuant_to_in_recital_is_not_presidential_authority():
    clause = (
        "Whereas entitlement is limited to service between dates fixed by or pursuant to law; "
        "Whereas the President is empowered to determine the terminal dates; "
        "Now, Therefore, I, Dwight D. Eisenhower, President of the United States, acting under "
        "and by virtue of the authority vested in me as President"
    )
    assert extract_authority_spans([clause]) == (
        ["Whereas the President is empowered to determine the terminal dates", "by virtue of the authority vested in me as President"]
    )
    assert category(clause) == "other_vesting_authority"


def test_first_person_pursuant_to_in_recital_remains_authority():
    assert extract_authority_spans([
        "Whereas, pursuant to my authority as President, I established the Council;"
    ]) == ["pursuant to my authority as President, I established the Council"]
    assert category(
        "Whereas, pursuant to the power vested in me by section 301 of title 3, United States Code, "
        "I delegated that function;"
    ) == "specific_statutory_section_only"


def test_faithful_execution_reference_is_not_generic_statutory_authority():
    assert category(
        "By authority vested in me as President, I have a duty to ensure that the laws of the "
        "United States are faithfully executed,"
    ) == "other_vesting_authority"


def test_nonstatutory_sections_do_not_match_category_six():
    assert category(
        "Pursuant to my powers under Article II, Section 2, of the Constitution,"
    ) == "specific_constitutional_provision_only"
    assert category(
        "By authority vested in me under Section 1 of Executive Order 11803,"
    ) == "other_vesting_authority"


def test_no_clause_and_unclassified_clause_have_coverage_categories():
    assert category() == "no_vesting_clause"
    assert category(
        "By the authority vested in me as President of the United States of America,"
    ) == "other_vesting_authority"
    assert category(
        "By the authority vested in me by the North Atlantic Treaty,"
    ) == "other_vesting_authority"


def test_other_authority_does_not_displace_a_recognized_category():
    assert category(
        "By the authority vested in me by the Constitution and Executive Order 12345,"
    ) == "generic_constitution_only"
    assert category(
        "By the authority vested in me by section 301 of title 3, United States Code, "
        "and the North Atlantic Treaty,"
    ) == "specific_statutory_section_only"


def test_authority_spans_cut_all_reviewed_tail_connectors():
    for connector in (
        "consistent with",
        "in accordance with",
        "in order to",
        "in furtherance of",
        "in light of",
        "in recognition of",
        "as contemplated by",
    ):
        clause = f"By authority vested in me by the Constitution, and {connector} Public Law 1-2,"
        assert extract_authority_spans([clause]) == ["authority vested in me by the Constitution"]

    assert extract_authority_spans([
        "By authority vested in me by the Constitution and laws of the United States "
        "and in order to implement Public Law 1-2,"
    ]) == ["authority vested in me by the Constitution and laws of the United States"]


def test_html_contains_every_category_and_count_column():
    counts = {
        (administration, view, category): 1
        for administration in ("Example President (First)", "total")
        for view in VIEWS
        for category in CATEGORIES
    }
    administration_totals = Counter({
        (administration, view): len(CATEGORIES)
        for administration in ("Example President (First)", "total")
        for view in VIEWS
    })
    report = render_html(
        counts,
        len(CATEGORIES),
        ["Example President (First)"],
        administration_totals,
    )
    assert "17 presidential directives" in report
    assert "Counts by Administration" in report
    assert "Example President (First)" in report
    assert report.count('<tbody data-view=') == len(VIEWS)
    assert report.count('<button type="button" data-view=') == len(VIEWS)
    assert report.count('<th scope="row">') == len(CATEGORIES) + 2 * len(VIEWS)
    assert "Mutually exclusive categories" in report
    assert "Category sum" in report
    assert report.count("<b>PASS</b>") == 2 * len(VIEWS)
    assert "Contextual uses of <code>pursuant to</code> within other recitals are discarded" in report
    for category in CATEGORIES:
        assert CATEGORY_LABELS[category] in report


def test_html_rejects_category_total_mismatches():
    counts = Counter()
    administration_totals = Counter({
        ("Example President (First)", view): 1
        for view in VIEWS
    })
    administration_totals.update({
        ("total", view): 1
        for view in VIEWS
    })
    try:
        render_html(
            counts,
            1,
            ["Example President (First)"],
            administration_totals,
        )
    except ValueError as error:
        assert "category total mismatch" in str(error)
    else:
        raise AssertionError("render_html accepted mismatched category totals")


def test_empty_excel_category_sheet_omits_empty_hyperlinks_element():
    worksheet = worksheet_xml([])
    assert "<hyperlinks>" not in worksheet
    assert '<autoFilter ref="A1:F1"/>' in worksheet


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"  PASS  {test.__name__}")
    print(f"\n{len(tests)} passed")
