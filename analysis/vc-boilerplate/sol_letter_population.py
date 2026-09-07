#!/usr/bin/env python3
"""Classify vague-authority letter operative segments via local Codex CLI."""
from __future__ import annotations

import sol_eo_population as population

population.OUTPUTS = population.HERE / "outputs" / "sol_low_letter_population"
population.DOCUMENT_TYPE = "letter"
population.DOCUMENT_LABEL = "letter"
population.DOCUMENT_LABEL_PLURAL = "letters"
population.EXPECTED_TARGETS = 4
population.EXPECTED_CALLS = 2
population.EXPECTED_NO_SEGMENTS = 2
population.EXPECTED_SEGMENTS = 4


if __name__ == "__main__":
    population.main()
