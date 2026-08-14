from build_full_function_profile_plan import build_scope, interleave_by_document_type, prior_statuses


def test_prior_status_precedence_is_safe():
    inventory = [
        {"document_id": "2", "response_saved": "true", "validation_status": "invalid"},
        {"document_id": "3", "response_saved": "false", "validation_status": "unknown"},
    ]
    assert prior_statuses({"1", "2"}, inventory, {"2", "4"}) == {
        "1": "validated", "2": "validated", "3": "submitted_unknown",
        "4": "legacy_consumed",
    }


def test_scope_is_union_of_ranked_children_and_parents():
    rows = [
        {"child_id": "10", "parent_id": "1"},
        {"child_id": "10", "parent_id": "2"},
        {"child_id": "11", "parent_id": "2"},
    ]
    children, parents, counts = build_scope(rows)
    assert children == {"10", "11"}
    assert parents == {"1", "2"}
    assert counts == {"1": 1, "2": 2}


def test_requests_are_interleaved_by_document_type():
    def request(document_id, document_type):
        return {"metadata": {"document_id": document_id, "document_type": document_type}}
    rows = [request("1", "executive_order"), request("2", "executive_order"),
            request("3", "letter"), request("4", "letter")]
    assert [row["metadata"]["document_type"] for row in interleave_by_document_type(rows)] == [
        "executive_order", "letter", "executive_order", "letter"
    ]
