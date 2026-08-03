"""Tests for presidential-directive parent artifacts."""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from parent_analysis import (
    DirectiveDocument,
    build_similarity_artifacts,
    build_automatic_edges,
    eo_number_from_url,
    extract_directive_references,
    extract_eo_references,
)


def document(
    document_id: str,
    document_type: str,
    date: str,
    text: str,
    *,
    identifier: str = "",
    title: str = "",
) -> DirectiveDocument:
    return DirectiveDocument(
        document_id=document_id,
        document_type=document_type,
        identifier=identifier,
        title=title,
        date=datetime.strptime(date, "%B %d, %Y"),
        date_text=date,
        url=f"https://example.test/{document_type}/{document_id}",
        text=text,
    )


def test_extracts_common_eo_reference_forms():
    text = (
        "Executive Order 12345 remains in effect.  "
        "Executive Order No. 12346 is discussed.  E.O. 12347 is relevant."
    )
    assert [item.identifier for item in extract_eo_references(text)] == [
        "12345",
        "12346",
        "12347",
    ]


def test_extracts_numbered_proclamation_and_memorandum_references():
    references = extract_directive_references(
        "Proclamation 9984 remains in force.  PPD-41 is also discussed."
    )
    assert [(item.document_type, item.identifier) for item in references] == [
        ("proclamation", "9984"),
        ("memorandum", "PPD-41"),
    ]


def test_extracts_unnumbered_date_and_exact_title_references():
    references = extract_directive_references(
        'I revoke my memorandum of March 31, 2010.  '
        'The letter entitled "Report to the Congress" remains relevant.'
    )
    assert [
        (item.document_type, item.date_text, item.title) for item in references
    ] == [
        ("memorandum", "March 31, 2010", ""),
        ("letter", "", "Report to the Congress"),
    ]


def test_assigns_nearby_formal_relation_or_citation_fallback():
    references = extract_eo_references(
        "Executive Order 12345 is hereby revoked.  We discuss Executive Order 12346."
    )
    assert [item.relation for item in references] == ["revokes", "citation_discussion"]


def test_builds_only_resolved_earlier_same_type_edges():
    parent = document(
        "p", "executive_order", "January 1, 2020", "Parent.", identifier="12345"
    )
    child = document(
        "c",
        "executive_order",
        "January 2, 2020",
        "Executive Order 12345 is hereby amended. Executive Order 99999 is discussed.",
        identifier="12346",
    )
    edges, unresolved = build_automatic_edges([child, parent])
    assert [(row["parent_id"], row["relation"]) for row in edges] == [("p", "amends")]
    assert unresolved[0]["referenced_identifier"] == "99999"
    assert unresolved[0]["reason"] == "outside_corpus"


def test_cross_type_reference_is_not_a_parent_edge():
    parent = document(
        "p", "proclamation", "January 1, 2020", "Parent.", identifier="9984"
    )
    child = document(
        "c",
        "executive_order",
        "January 2, 2020",
        "Proclamation 9984 remains in force.",
        identifier="12346",
    )
    edges, unresolved = build_automatic_edges([child, parent])
    assert edges == []
    assert unresolved[0]["reason"] == "cross_type_reference"


def test_unique_exact_date_resolves_unnumbered_memorandum():
    parent = document(
        "p", "memorandum", "March 31, 2010", "Parent.", title="Prior Policy"
    )
    child = document(
        "c",
        "memorandum",
        "January 2, 2020",
        "I hereby revoke my memorandum of March 31, 2010.",
        title="New Policy",
    )
    edges, unresolved = build_automatic_edges([child, parent])
    assert [row["parent_id"] for row in edges] == ["p"]
    assert unresolved == []


def test_ambiguous_exact_date_remains_unresolved():
    parents = [
        document("p1", "letter", "March 31, 2010", "Parent.", title="First"),
        document("p2", "letter", "March 31, 2010", "Parent.", title="Second"),
    ]
    child = document(
        "c",
        "letter",
        "January 2, 2020",
        "See my letter of March 31, 2010.",
        title="New",
    )
    edges, unresolved = build_automatic_edges([child, *parents])
    assert edges == []
    assert unresolved[0]["reason"] == "ambiguous_match"


def test_duplicate_number_remains_unresolved():
    parents = [
        document(
            "p1", "proclamation", "March 11, 2020", "Parent.", identifier="9996", title="First"
        ),
        document(
            "p2", "proclamation", "March 14, 2020", "Parent.", identifier="9996", title="Second"
        ),
    ]
    child = document(
        "c",
        "proclamation",
        "March 20, 2020",
        "Proclamation 9996 remains relevant.",
        identifier="10000",
    )
    edges, unresolved = build_automatic_edges([child, *parents])
    assert edges == []
    assert unresolved[0]["reason"] == "ambiguous_match"


def test_exact_title_resolves_unnumbered_letter():
    parent = document(
        "p", "letter", "March 31, 2010", "Parent.", title="Report to the Congress"
    )
    child = document(
        "c",
        "letter",
        "January 2, 2020",
        'The letter entitled "Report to the Congress" is continued.',
        title="New",
    )
    edges, _ = build_automatic_edges([child, parent])
    assert [row["parent_id"] for row in edges] == ["p"]


def test_same_day_document_is_not_earlier():
    parent = document(
        "p", "executive_order", "January 1, 2020", "Parent.", identifier="12345"
    )
    child = document(
        "c",
        "executive_order",
        "January 1, 2020",
        "See Executive Order 12345.",
        identifier="12346",
    )
    edges, unresolved = build_automatic_edges([child, parent])
    assert edges == []
    assert unresolved[0]["reason"] == "not_earlier"


def test_own_numbered_header_is_not_a_reference():
    child = document(
        "c",
        "memorandum",
        "January 1, 2020",
        "Presidential Policy Directive/PPD-41  Subject: Example",
        identifier="PPD-41",
    )
    edges, unresolved = build_automatic_edges([child])
    assert edges == []
    assert unresolved == []


def test_url_number_extraction():
    assert eo_number_from_url("https://x/documents/executive-order-14388-title") == "14388"


def test_a_suffix_is_preserved():
    refs = extract_eo_references("Executive Order 10695-A remains in force.")
    assert refs[0].identifier == "10695-A"


def test_similarity_artifacts_have_type_and_stable_operative_ids():
    doc = document(
        "c",
        "memorandum",
        "January 2, 2020",
        "By the Constitution, it is hereby ordered:  "
        "The Secretary shall perform the work.  The agency shall issue guidance.",
        title="Example",
    )
    documents, segments = build_similarity_artifacts([doc], set())
    assert documents[0]["document_id"] == "c"
    assert documents[0]["document_type"] == "memorandum"
    assert "[AUTHORITY]" in documents[0]["cleaned_masked_text"]
    assert [row["segment_id"] for row in segments] == ["c:oa:001", "c:oa:002"]
    assert {row["document_type"] for row in segments} == {"memorandum"}


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"  PASS  {test.__name__}")
    print(f"\n{len(tests)} passed")
