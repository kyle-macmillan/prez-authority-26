from build_candidate_function_profile_batch import build_candidate_inventory


def test_candidate_inventory_deduplicates_and_excludes_all_prior_work():
    rows = [
        {"child_id": "10", "parent_id": "1", "child_date": "January 10, 2020",
         "parent_date": "January 01, 2020", "document_embedding_rank": "1"},
        {"child_id": "11", "parent_id": "1", "child_date": "January 11, 2020",
         "parent_date": "January 01, 2020", "document_embedding_rank": "2"},
        {"child_id": "10", "parent_id": "2", "child_date": "January 10, 2020",
         "parent_date": "January 02, 2020", "document_embedding_rank": "2"},
        {"child_id": "10", "parent_id": "3", "child_date": "January 10, 2020",
         "parent_date": "January 03, 2020", "document_embedding_rank": "3"},
    ]
    inventory, requested, summary = build_candidate_inventory(
        {"10", "11"}, rows, validated_ids={"2"}, completed_ids={"3"}, legacy_ids=set()
    )
    assert requested == ["1"]
    parent_one = next(row for row in inventory if row["document_id"] == "1")
    assert parent_one["candidate_for_children"] == 2
    assert summary == {
        "children": 2, "children_with_candidates": 2, "children_without_candidates": 0,
        "candidate_pairs": 4, "unique_candidate_parents": 3, "already_validated": 1,
        "prior_response_saved": 1, "legacy_consumed": 0, "requests": 1,
    }
