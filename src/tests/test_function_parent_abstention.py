#!/usr/bin/env python3
"""Focused tests for candidate-or-none calibration and request invariants."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from calibrate_deterministic_parent_abstention import choose_threshold, correct
from build_function_parent_acceptance_requests import INSTRUCTION as ACCEPT_INSTRUCTION
from build_function_parent_acceptance_requests import PROMPT_VERSION as ACCEPT_PROMPT_VERSION
from build_gemini_function_rank_requests import INSTRUCTION as RANK_INSTRUCTION
from validate_gemini_function_rankings import parsed


def test_threshold_favors_conservative_tie():
    rows = [{"child_id": "1", "parent_id": "10", "score": .8},
            {"child_id": "2", "parent_id": "20", "score": .2}]
    labels = {"1": {"decision": "candidate", "selected_parent_id": "10"},
              "2": {"decision": "none", "selected_parent_id": None}}
    threshold, accuracy = choose_threshold(rows, labels)
    assert .2 < threshold < .8 and accuracy == 1


def test_exact_outcome_requires_matching_parent():
    row = {"child_id": "1", "parent_id": "10", "score": .8}
    assert not correct(row, {"decision": "candidate", "selected_parent_id": "11"}, .5)
    assert correct(row, {"decision": "none", "selected_parent_id": None}, .9)


def test_parser_accepts_candidate_or_none_shape():
    payload = {"best_candidate_id": "10", "best_candidate_is_plausible": False,
               "plausibility_score": .2, "reason": "generic overlap only"}
    assert parsed("```json\n" + json.dumps(payload) + "\n```") == payload


def test_parser_prefers_final_fenced_answer_after_search_queries():
    answer = {"best_candidate_id": "10", "best_candidate_is_plausible": True}
    text = '```json\n{"queries":["example"]}\n```\nGrounding notes\n```json\n' + json.dumps(answer) + "\n```"
    assert parsed(text) == answer


def test_gemini_prompts_use_drafter_and_target_substitution_standard():
    for instruction in (RANK_INSTRUCTION, ACCEPT_INSTRUCTION):
        lowered = instruction.casefold()
        assert "drafter" in lowered
        assert "different target does not defeat" in lowered
        assert "substantive drafting architecture" in lowered
        assert "generic" in lowered


def test_acceptance_prompt_recognizes_partial_and_structural_parents():
    lowered = " ".join(ACCEPT_INSTRUCTION.casefold().split())
    assert "structural-framework parent" in lowered
    assert "material-provision parent" in lowered
    assert "need not explain or template most of the child" in lowered
    assert "domain-specific regulatory scaffolding" in lowered
    assert "0.50-0.69" in ACCEPT_INSTRUCTION


def test_acceptance_prompt_preserves_negative_controls():
    lowered = " ".join(ACCEPT_INSTRUCTION.casefold().split())
    assert "incidental administrative clause" in lowered
    assert "merely naming, implementing" in lowered
    assert "repealing a policy" in lowered
    assert "without such drafting reuse, is not enough" in lowered


def test_acceptance_prompt_version_records_recalibration():
    assert ACCEPT_PROMPT_VERSION == "function-parent-accept-v3"


def test_acceptance_request_builder_supports_last_subset():
    source = Path(__file__).resolve().parents[1] / "build_function_parent_acceptance_requests.py"
    text = source.read_text()
    assert '"--last"' in text
    assert "ordered[-args.last:]" in text


if __name__ == "__main__":
    tests = [value for key, value in sorted(globals().items()) if key.startswith("test_")]
    for test in tests: test()
    print(f"{len(tests)} passed")
