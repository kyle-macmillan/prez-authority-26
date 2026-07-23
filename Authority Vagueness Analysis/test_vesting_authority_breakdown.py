"""Tests for document-level vesting-authority specificity categories."""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from vesting_authority_breakdown import (
    CATEGORIES,
    CATEGORY_LABELS,
    VIEWS,
    classify_authority_categories,
    extract_authority_spans,
    render_html,
)


def categories(*clauses: str) -> tuple[str, ...]:
    return classify_authority_categories(list(clauses))


def test_generic_categories_are_distinct_and_exclusive():
    assert categories("By the authority vested in me by the Constitution,") == (
        "generic_constitution",
    )
    assert categories("By the authority vested in me by law,") == ("generic_statute",)
    assert categories(
        "By the authority vested in me by the Constitution and statutes of the United States,"
    ) == ("constitution_and_laws",)


def test_combined_formula_accepts_singular_and_ocr_variants():
    assert categories(
        "By the authority vested in me by the Constitution and the law of the United States of America,"
    ) == ("constitution_and_laws",)
    assert categories(
        "By the authority vested in me by the Constitutuion and the laws of the United States,"
    ) == ("constitution_and_laws",)
    assert categories(
        "By the authority vested in me by the Constutition and statutes of the United States,"
    ) == ("constitution_and_laws",)
    assert categories(
        "By the authority vested in me by the Constitutioin and laws of the United States,"
    ) == ("constitution_and_laws",)
    assert categories(
        "By the authority vested in me by the Cosntitution and laws of the United States,"
    ) == ("constitution_and_laws",)
    assert categories(
        "By the authority vested in me by the Constitution and the statues of the United States,"
    ) == ("constitution_and_laws",)


def test_specific_constitution_supersedes_generic_wording():
    assert categories(
        "By the authority vested in me by the Constitution, including Article II of the Constitution,"
    ) == ("specific_constitution",)
    assert categories(
        "Pursuant to authority vested in me as the Chief Executive Officer of the United States,"
    ) == ("specific_constitution",)


def test_specific_constitutional_provision_supersedes_article():
    assert categories(
        "Pursuant to my powers under Article II, Section 2, of the Constitution,"
    ) == ("specific_constitutional_provision",)
    assert categories(
        "By virtue of authority vested in me by Section 2 of Article II of the Constitution,"
    ) == ("specific_constitutional_provision",)
    assert categories(
        "Pursuant to my constitutional authority as Commander-in-Chief and Chief Executive,"
    ) == ("specific_constitutional_provision",)


def test_named_clause_in_purpose_tail_does_not_supersede_boilerplate():
    clause = (
        "By the authority vested in me as President by the Constitution and laws of the "
        "United States of America, and in order to ensure due regard for obligations imposed "
        "by the Just Compensation Clause of the Fifth Amendment,"
    )
    assert categories(clause) == ("constitution_and_laws",)


def test_specific_statutory_section_supersedes_act_and_boilerplate():
    clause = (
        "By the authority vested in me by the Constitution and the laws of the United States, "
        "including the National Emergencies Act (50 U.S.C. 1601 et seq.), and section 301 "
        "of title 3, United States Code,"
    )
    assert categories(clause) == ("specific_statutory_section",)


def test_statutory_section_ocr_and_code_forms():
    assert categories(
        "Under the authority granted to me in section 12(a) of the Example Act, 43 U S.C. 1341(a),"
    ) == ("specific_statutory_section",)
    assert categories(
        "Pursuant to chapter 10 of title 5, United States Code,"
    ) == ("specific_statutory_section",)
    assert categories(
        "By authority vested in me by the Uniform Code of Military Justice (10 U.S.C., ch. 47),"
    ) == ("specific_statutory_section",)


def test_compliance_and_purpose_citations_are_excluded():
    assert categories(
        "By the authority vested in me by the Constitution and statutes of the United States, "
        "and in accordance with the Federal Advisory Committee Act (5 U.S.C., App.),"
    ) == ("constitution_and_laws",)
    assert categories(
        "Pursuant to authority vested in me as the Chief Executive Officer of the United States, "
        "and consistent with the Hatch Act Reform Amendment regulations, 5 CFR 734.104, "
        "and section 301 of title 3, United States Code,"
    ) == ("specific_constitution",)
    assert categories(
        "By the authority vested in me by the Constitution and laws of the United States, "
        "and in order to implement Public Law 117-169,"
    ) == ("constitution_and_laws",)


def test_including_is_authority_but_in_furtherance_is_not():
    clause = (
        "By the authority vested in me by the Constitution and laws of the United States, "
        "including the National Emergencies Act (50 U.S.C. 1601 et seq.), and in furtherance "
        "of Proclamation 9994,"
    )
    assert categories(clause) == ("specific_statutory_section",)


def test_authorizing_proclamation_recital_ignores_constitutional_history():
    clause = (
        "joint resolution proposing an amendment to the Constitution; Whereas the resolution "
        "led to adoption of the Thirteenth Amendment; and Whereas, by a joint resolution "
        "approved June 30, 1948, the Congress authorized the President to proclaim February 1 "
        "as National Freedom Day; Now, Therefore, I, Harry S. Truman, President of the United States,"
    )
    assert categories(clause) == ("act_of_congress",)
    assert categories(
        "Whereas those resolutions of the Congress authorize the President to issue annually "
        "a proclamation for Citizenship Day and Constitution Week; Now, Therefore, I proclaim,"
    ) == ("act_of_congress",)


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
    assert categories(clause) == ("other_vesting_authority",)


def test_first_person_pursuant_to_in_recital_remains_authority():
    assert extract_authority_spans([
        "Whereas, pursuant to my authority as President, I established the Council;"
    ]) == ["pursuant to my authority as President, I established the Council"]
    assert categories(
        "Whereas, pursuant to the power vested in me by section 301 of title 3, United States Code, "
        "I delegated that function;"
    ) == ("specific_statutory_section",)


def test_faithful_execution_reference_is_not_generic_statutory_authority():
    assert categories(
        "By authority vested in me as President, I have a duty to ensure that the laws of the "
        "United States are faithfully executed,"
    ) == ("other_vesting_authority",)


def test_nonstatutory_sections_do_not_match_category_six():
    assert categories(
        "Pursuant to my powers under Article II, Section 2, of the Constitution,"
    ) == ("specific_constitutional_provision",)
    assert categories(
        "By authority vested in me under Section 1 of Executive Order 11803,"
    ) == ("other_vesting_authority",)


def test_no_clause_and_unclassified_clause_have_coverage_categories():
    assert categories() == ("no_vesting_clause",)
    assert categories(
        "By the authority vested in me as President of the United States of America,"
    ) == ("other_vesting_authority",)
    assert categories(
        "By the authority vested in me by the North Atlantic Treaty,"
    ) == ("other_vesting_authority",)


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
        (administration, view): 10
        for administration in ("Example President (First)", "total")
        for view in VIEWS
    })
    report = render_html(
        counts,
        18_418,
        ["Example President (First)"],
        administration_totals,
    )
    assert "18,418 presidential directives" in report
    assert "Counts by Administration" in report
    assert "Example President (First)" in report
    assert report.count('<tbody data-view=') == len(VIEWS)
    assert report.count('<button type="button" data-view=') == len(VIEWS)
    assert report.count('<th scope="row">') == len(CATEGORIES) + 2 * len(VIEWS)
    assert "constitutional and statutory families" in report
    assert "Within each family, the categories are hierarchical and mutually exclusive" in report
    assert "Categories (1), (4), and (7) apply only when no specific authority is detected" in report
    assert "Categories (8) and (9) are mutually exclusive coverage categories" in report
    assert "Contextual uses of <code>pursuant to</code> within other recitals are discarded" in report
    for category in CATEGORIES:
        assert CATEGORY_LABELS[category] in report


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"  PASS  {test.__name__}")
    print(f"\n{len(tests)} passed")
