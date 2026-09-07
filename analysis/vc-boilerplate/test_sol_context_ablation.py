#!/usr/bin/env python3
"""Tests for the paired context-instruction experiment."""
from __future__ import annotations

import importlib.util
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("sol_context_ablation", HERE / "sol_context_ablation.py")
ablation = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(ablation)


def test_prompt_pair_differs_only_by_frozen_context_instruction():
    prompts = ablation.prompt_artifacts()
    v1 = prompts["v1"]["prompt"]
    v2 = prompts["v2"]["prompt"]
    assert ablation.CONTEXT_INSTRUCTION not in v1
    assert ablation.CONTEXT_INSTRUCTION in v2
    assert v2.replace("\n\n" + ablation.CONTEXT_INSTRUCTION, "") == v1
    for phrase in (
        "operative verbs and ordering phrases", "fragments or segments",
        "full directive context", "do not classify surrounding actions",
        "Evidence must come from the target", "rationale and classification may rely",
    ):
        assert phrase in ablation.CONTEXT_INSTRUCTION


def test_jobs_are_complete_balanced_and_deterministic():
    requests = [{"target_id": "a"}, {"target_id": "b"}, {"target_id": "c"}]
    first = ablation.paired_jobs(requests)
    second = ablation.paired_jobs(requests)
    assert first == second
    assert len(first) == 6
    assert {(row["condition"], row["target_id"]) for row in first} == {
        (condition, target) for condition in ("v1", "v2") for target in ("a", "b", "c")
    }


def test_exact_mcnemar_known_values():
    assert ablation.exact_mcnemar(0, 0)["p_value"] == 1.0
    assert ablation.exact_mcnemar(0, 5)["p_value"] == 0.0625
    assert ablation.exact_mcnemar(2, 2)["p_value"] == 1.0


def test_clustered_delta_is_zero_for_identical_predictions():
    rows = [
        {"document_id": str(i // 2), "gold_code": i % 5,
         "v1_prediction": i % 5, "v2_prediction": i % 5}
        for i in range(10)
    ]
    intervals = ablation.paired_clustered_intervals(rows, repetitions=20)
    assert intervals["accuracy_delta_95ci"] == [0.0, 0.0]
    assert intervals["macro_f1_delta_95ci"] == [0.0, 0.0]


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"{len(tests)} tests passed")
