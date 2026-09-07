#!/usr/bin/env python3
"""Classify vague-authority proclamation operative segments via local Codex CLI."""
from __future__ import annotations

import sol_eo_population as population

population.OUTPUTS = population.HERE / "outputs" / "sol_low_proclamation_population"
population.DOCUMENT_TYPE = "proclamation"
population.DOCUMENT_LABEL = "proclamation"
population.DOCUMENT_LABEL_PLURAL = "proclamations"
population.EXPECTED_TARGETS = 170
population.EXPECTED_CALLS = 168
population.EXPECTED_NO_SEGMENTS = 2
population.EXPECTED_SEGMENTS = 253


if __name__ == "__main__":
    population.main()
