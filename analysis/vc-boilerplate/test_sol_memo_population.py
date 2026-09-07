"""Coverage tests for the one-call-per-memorandum Sol population classifier."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location("sol_memo_population", HERE / "sol_memo_population.py")
memo = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(memo)


def test_population_is_nonceremonial_and_has_expected_segment_coverage():
    requests, no_segments = memo.population.target_eos()
    assert len(requests) == 165
    assert len(no_segments) == 6
    assert sum(len(row["segments"]) for row in requests) == 758
    assert all(row["segments"] for row in requests)


def test_memo_configuration_is_isolated():
    assert memo.population.DOCUMENT_TYPE == "memorandum"
    assert memo.population.OUTPUTS.name == "sol_low_memo_population"
    assert memo.population.MODEL == "gpt-5.6-sol"
    assert memo.population.REASONING_EFFORT == "low"
