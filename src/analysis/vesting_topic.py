"""Helpers for identifying topic citations inside a directive's vesting clause."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from vesting_authority_stats import extract_vesting_clauses  # noqa: E402


def topic_in_vesting_clause(text: str, doc_type: str, pattern: re.Pattern) -> bool:
    """Return whether *pattern* appears in the extracted vesting clause(s)."""
    vesting_text = " ".join(extract_vesting_clauses(text, doc_type))
    return bool(pattern.search(vesting_text))
