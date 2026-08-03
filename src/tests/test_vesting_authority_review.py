"""Tests for comparative vesting-authority review sampling and summaries."""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from vesting_authority_review import (
    GROUPS,
    TYPE_ALLOCATION,
    build_html,
    select_sample,
    summarize_rows,
)


def synthetic_audit() -> list[dict]:
    rows = []
    document_id = 1
    for group in GROUPS:
        for doc_type, sample_n in TYPE_ALLOCATION.items():
            for _ in range(sample_n + 5):
                rows.append(
                    {
                        "document_id": str(document_id),
                        "qualifies": "true" if group == "generic_only" else "false",
                        "doc_type": doc_type,
                        "source_file": "source.csv",
                        "vesting_clauses": "[]",
                        "generic_authority_matches": "[]",
                        "specific_authority_matches": "[]" if group == "generic_only" else '[{"rule":"usc","text":"3 U.S.C."}]',
                    }
                )
                document_id += 1
    return rows


def test_sample_is_deterministic_and_unique():
    first = select_sample(synthetic_audit())
    second = select_sample(synthetic_audit())
    assert [row["document_id"] for row in first] == [row["document_id"] for row in second]
    assert len(first) == 200
    assert len({row["document_id"] for row in first}) == 200


def test_sample_has_matched_allocation_and_weights():
    sample = select_sample(synthetic_audit())
    counts = Counter((row["authority_footing"], row["doc_type"]) for row in sample)
    for group in GROUPS:
        for doc_type, sample_n in TYPE_ALLOCATION.items():
            assert counts[group, doc_type] == sample_n
            rows = [
                row for row in sample
                if row["authority_footing"] == group and row["doc_type"] == doc_type
            ]
            assert {row["sample_weight"] for row in rows} == {(sample_n + 5) / sample_n}


def test_html_contains_all_records_and_coding_controls():
    records = [
        {
            "sample_id": "VA001",
            "doc_type": "executive_order",
            "date": "January 1, 2020",
            "authority_footing": "generic_only",
            "president": "Example",
            "document_id": "1",
            "sample_weight": "1.0",
            "vesting_clauses": '["By the Constitution"]',
            "specific_authority_matches": "[]",
            "operative_excerpt": "The agency shall act.",
            "full_text": "Full text.",
            "primary_action_mode": "",
            "agency_authority_reliance": "",
            "reviewer_confidence": "",
            "reviewer_notes": "",
        }
    ]
    output = build_html(records)
    assert "VA001" in output
    assert "primary_action_mode" in output
    assert "Export coded CSV" in output


def test_summary_uses_weights_and_ignores_uncoded_fields():
    rows = [
        {
            "sample_id": "VA001", "authority_footing": "generic_only", "sample_weight": "3",
            "primary_action_mode": "agency_direction", "agency_authority_reliance": "both",
            "reviewer_confidence": "high",
        },
        {
            "sample_id": "VA002", "authority_footing": "generic_only", "sample_weight": "1",
            "primary_action_mode": "direct_legal_effect", "agency_authority_reliance": "neither",
            "reviewer_confidence": "medium",
        },
        {
            "sample_id": "VA003", "authority_footing": "generic_plus_specific", "sample_weight": "2",
            "primary_action_mode": "direct_legal_effect", "agency_authority_reliance": "",
            "reviewer_confidence": "",
        },
    ]
    summary = summarize_rows(rows)
    assert summary["generic_only"]["agency_direction"][0] == 0.75
    assert summary["generic_only"]["explicit_agency_reliance"][0] == 0.75
    assert summary["generic_plus_specific"]["direct_effect"][0] == 1.0


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"  PASS  {test.__name__}")
    print(f"\n{len(tests)} passed")
