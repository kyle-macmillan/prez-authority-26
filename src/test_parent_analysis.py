"""Tests for automatic executive-order parent edges."""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from parent_analysis import (
    EODocument,
    build_similarity_artifacts,
    build_automatic_edges,
    eo_number_from_url,
    extract_eo_references,
)


def document(document_id: str, number: int | str, date: str, text: str) -> EODocument:
    return EODocument(
        document_id=document_id,
        eo_number=str(number),
        date=datetime.strptime(date, "%B %d, %Y"),
        date_text=date,
        url=f"https://example.test/executive-order-{number}-title",
        text=text,
    )


def test_extracts_common_reference_forms():
    text = (
        "Executive Order 12345 remains in effect.  "
        "Executive Order No. 12346 is discussed.  E.O. 12347 is relevant."
    )
    assert [item.eo_number for item in extract_eo_references(text)] == ["12345", "12346", "12347"]


def test_assigns_nearby_formal_relation_or_citation_fallback():
    references = extract_eo_references(
        "Executive Order 12345 is hereby revoked.  We discuss Executive Order 12346."
    )
    assert [item.relation for item in references] == ["revokes", "citation_discussion"]


def test_builds_only_resolved_earlier_edges():
    parent = document("p", 12345, "January 1, 2020", "Parent.")
    child = document(
        "c",
        12346,
        "January 2, 2020",
        "Executive Order 12345 is hereby amended. Executive Order 99999 is discussed.",
    )
    edges, unresolved = build_automatic_edges([child, parent])
    assert [(row["parent_id"], row["relation"]) for row in edges] == [("p", "amends")]
    assert unresolved[0]["referenced_eo_number"] == "99999"
    assert unresolved[0]["reason"] == "outside_corpus"


def test_same_day_lower_number_is_earlier():
    parent = document("p", 12345, "January 1, 2020", "Parent.")
    child = document("c", 12346, "January 1, 2020", "See Executive Order 12345.")
    edges, _ = build_automatic_edges([child, parent])
    assert len(edges) == 1


def test_url_number_extraction():
    assert eo_number_from_url("https://x/documents/executive-order-14388-title") == "14388"


def test_a_suffix_is_preserved():
    refs = extract_eo_references("Executive Order 10695-A remains in force.")
    assert refs[0].eo_number == "10695-A"


def test_similarity_artifacts_have_stable_operative_ids():
    doc = document(
        "c",
        12346,
        "January 2, 2020",
        "By the Constitution, it is hereby ordered:  "
        "The Secretary shall perform the work.  The agency shall issue guidance.",
    )
    documents, segments = build_similarity_artifacts([doc], set())
    assert documents[0]["document_id"] == "c"
    assert "[AUTHORITY]" in documents[0]["cleaned_masked_text"]
    assert [row["segment_id"] for row in segments] == ["c:oa:001", "c:oa:002"]


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"  PASS  {test.__name__}")
    print(f"\n{len(tests)} passed")
