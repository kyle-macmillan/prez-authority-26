#!/usr/bin/env python3
"""Coverage tests for proclamation and letter population wrappers."""
from __future__ import annotations

import importlib


def check(module_name: str, targets: int, calls: int, no_segments: int, segments: int) -> None:
    module = importlib.import_module(module_name)
    requests, missing = module.population.target_eos()
    assert targets == calls + no_segments
    assert len(requests) == calls
    assert len(missing) == no_segments
    assert sum(len(row["segments"]) for row in requests) == segments


def test_proclamation_population():
    check("sol_proclamation_population", 170, 168, 2, 253)


def test_letter_population():
    # Reload the common runner because each wrapper intentionally configures its globals.
    import sol_eo_population
    importlib.reload(sol_eo_population)
    import sys
    sys.modules.pop("sol_letter_population", None)
    check("sol_letter_population", 4, 2, 2, 4)


if __name__ == "__main__":
    test_proclamation_population()
    test_letter_population()
    print("PASS remaining population coverage")
