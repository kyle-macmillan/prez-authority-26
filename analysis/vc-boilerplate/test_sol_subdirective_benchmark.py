"""Tests for the Codex-CLI Sol/low sub-directive benchmark."""
from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("sol_benchmark", HERE / "sol_subdirective_benchmark.py")
bench = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(bench)


def test_partition_counts_alignment_and_document_isolation():
    dev, validation, _ = bench.load_partitioned_records()
    assert len(dev) == 91
    assert len(validation) == 198
    assert len({row["document_id"] for row in dev}) == 40
    assert len({row["document_id"] for row in validation}) == 80
    assert {row["document_id"] for row in dev}.isdisjoint(row["document_id"] for row in validation)
    assert all(bench.normalize(row["target_text"]) in bench.normalize(row["full_context"]) for row in dev + validation)


def test_fixed_examples_cover_every_code_once():
    dev, _, _ = bench.load_partitioned_records()
    examples = bench.example_rows(dev)
    assert [row["code"] for row in examples] == [0, 1, 2, 3, 4]
    assert [row["target_id"] for row in examples] == ["19275:002", "338:002", "3306:001", "10067:002", "3841:001"]


def test_prompt_marks_target_and_never_embeds_its_gold_label():
    dev, _, _ = bench.load_partitioned_records()
    row = dev[0]
    prompt = bench.request_prompt(bench.base_prompt(bench.DRAFT_GUIDANCE), row)
    assert "FULL_DIRECTIVE_CONTEXT" in prompt
    assert "TARGET_SUBDIRECTIVE" in prompt
    assert row["target_text"] in prompt
    assert "gold_code" not in prompt


def test_answer_validation_and_tool_audit():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        answer = root / "answer.json"
        answer.write_text(json.dumps({"code": 3, "rationale": "Direct waiver.", "evidence": "I hereby waive X."}))
        parsed, errors = bench.parse_answer(answer, "Accordingly, I hereby waive X.")
        assert parsed["code"] == 3 and not errors
        events = root / "events.jsonl"
        events.write_text(json.dumps({"type": "item.completed", "item": {"type": "command_execution"}}) + "\n")
        assert bench.event_audit(events) == ["command_execution"]
        events.write_text(json.dumps({"type": "item.completed", "item": {"type": "web_search"}}) + "\n")
        assert bench.event_audit(events) == []
        assert bench.event_metadata(events)["web_search_used"] is True


def test_evidence_match_tolerates_quote_punctuation_but_not_paraphrase():
    target = 'I proclaim this as the 30th "Small Business Week," and call upon Americans.'
    assert bench.evidence_matches('the 30th "Small Business Week"', target)
    assert bench.evidence_matches("the termination of the duties is in the national interest",
                                  "the termination (as modified by items 1 through 5) of the duties is in the national interest")
    assert bench.evidence_matches("The Secretary of HUD shall investigate",
                                  "The Secretary of Housing and Urban Development (HUD) shall investigate")
    assert not bench.evidence_matches("the thirtieth celebration of small businesses", target)


def test_metrics_include_minority_and_combined_legal_effect_scores():
    rows = [{"document_id": str(i), "gold_code": i, "prediction": i} for i in range(5)]
    report = bench.metrics(rows)
    assert report["accuracy"] == 1.0
    assert report["macro_f1"] == 1.0
    assert report["codes_2_or_3"]["recall"] == 1.0


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"{len(tests)} tests passed")
