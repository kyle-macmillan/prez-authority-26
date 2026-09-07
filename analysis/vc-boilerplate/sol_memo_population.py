#!/usr/bin/env python3
"""Classify all nonceremonial generic-authority memorandum operative segments via local Codex CLI."""
from __future__ import annotations

import sol_eo_population as population

population.OUTPUTS = population.HERE / "outputs" / "sol_low_memo_population"
population.DOCUMENT_TYPE = "memorandum"
population.DOCUMENT_LABEL = "memorandum"
population.DOCUMENT_LABEL_PLURAL = "memoranda"
population.EXPECTED_TARGETS = 171
population.EXPECTED_CALLS = 165
population.EXPECTED_NO_SEGMENTS = 6
population.EXPECTED_SEGMENTS = 758


if __name__ == "__main__":
    population.main()
