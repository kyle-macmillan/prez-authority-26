from refresh_full_function_profile_plan import refreshed_status


def test_refreshed_status_prefers_validated_then_saved_then_unknown():
    rows = {
        "2": {"response_saved": "true", "validation_status": "invalid"},
        "3": {"response_saved": "false", "validation_status": "unknown"},
    }
    assert refreshed_status("1", validated={"1"}, run_status=rows,
                            prior="requested_not_submitted") == "validated"
    assert refreshed_status("2", validated=set(), run_status=rows,
                            prior="requested_not_submitted") == "completed_invalid"
    assert refreshed_status("3", validated=set(), run_status=rows,
                            prior="requested_not_submitted") == "submitted_unknown"
    assert refreshed_status("4", validated=set(), run_status=rows,
                            prior="legacy_consumed") == "legacy_consumed"
