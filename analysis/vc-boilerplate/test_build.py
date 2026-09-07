"""Focused tests for the deterministic vc-boilerplate analysis."""

from __future__ import annotations

import importlib.util
import json
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("vc_boilerplate_build", HERE / "build.py")
build = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build)


def test_finalized_gold_and_split_are_exact_and_deterministic():
    records = build.load_gold()
    first_dev, first_validation = build.build_split(records)
    second_dev, second_validation = build.build_split(records)
    assert [row["global_dev_id"] for row in first_dev] == [row["global_dev_id"] for row in second_dev]
    assert [row["global_dev_id"] for row in first_validation] == [row["global_dev_id"] for row in second_validation]
    assert len(first_dev) == 46
    assert len(first_validation) == 93
    assert {row["global_dev_id"] for row in first_dev}.isdisjoint(
        row["global_dev_id"] for row in first_validation
    )
    assert Counter(row["labels"]["code"] for row in first_dev) == build.DEV_TARGETS
    assert Counter(row["labels"]["code"] for row in first_validation) == {
        "0": 60, "1": 15, "2": 1, "3": 17
    }


def test_text_codebook_boundaries():
    assert build.classify_text(
        "I hereby proclaim May 3 as Sun Day and call upon Americans to observe it with ceremonies."
    )["predicted_code"] == "0"
    assert build.classify_text(
        "There is hereby established a Council. The Council shall study the issue and report."
    )["predicted_code"] == "1"
    assert build.classify_text(
        "Each agency shall require as a condition of every grant that recipients comply with X."
    )["predicted_code"] == "2"
    assert build.classify_text(
        "I hereby waive the statutory restriction on assistance."
    )["predicted_code"] == "3"
    assert build.classify_text(
        "Agencies shall be closed, employees shall be excused from duty, and the day shall be considered a holiday."
    )["predicted_code"] == "4"


def test_profile_classifier_has_explicit_missing_state():
    result = build.classify_profile(None)
    assert result["predicted_code"] == "0"
    assert result["rule"] == "P0_NO_PROFILE"


def test_profile_classifier_does_not_read_evidence_or_metadata():
    profile = {
        "document_id": "x",
        "doc_type": "executive_order",
        "profile": {
            "policy_functions": [],
            "operative_functions": [{
                "actor": "Council",
                "action": "study",
                "target": "policy",
                "mechanism": "review",
                "effect": "recommendations",
                "condition": "",
                "timing": "",
                "label": "Study policy",
                "evidence": "I hereby waive the statute and block all property.",
                "confidence": "high",
            }],
        },
    }
    flattened, count = build.profile_text(profile)
    assert count == 1
    assert "waive" not in flattened
    assert "block all property" not in flattened
    assert "executive_order" not in flattened
    assert build.classify_profile(profile)["predicted_code"] == "1"


def test_generated_manifest_matches_current_target_definition():
    manifest = json.loads((HERE / "outputs" / "manifest.json").read_text())
    assert manifest["development_documents"] == 46
    assert manifest["validation_documents"] == 93
    assert manifest["target_documents"] == 1369
    assert manifest["gold_sha256"] == build.GOLD_SHA256


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"{len(tests)} tests passed")
