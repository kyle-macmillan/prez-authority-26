"""Heuristic classifier for ceremonial presidential directives.

The project codebook treats public-facing symbolic acts as outside the governance
analysis: observances, memorial tributes, national symbols, and honorary medals or
certificates.  Strong symbolic forms apply to every directive type; observance-only
forms remain proclamation-specific to avoid treating incidental discussion as an act.
"""

from __future__ import annotations

import re

# ── Positive signals (any one marks a row as ceremonial) ──────────────────────

# Half-staff / half-mast memorial orders. Very high precision.
_HALF_STAFF_RE = re.compile(r"\bhalf[- ]?(?:staff|mast)\b", re.IGNORECASE)

# "do hereby (proclaim|designate|request|urge|...) ... as [National] X Day/Week/Month/Year/Holiday"
# Covers the main observance-designation formula and its common variants.
# Bounded to 400 chars so the match doesn't span multiple paragraphs.
_OBSERVANCE_RE = re.compile(
    r"\bdo\s+hereby\s+(?:proclaim|designate|request|urge|invite|ask|call\s+upon|affirm|set\s+aside)\b"
    r".{0,400}?\bas\s+(?:National\s+|the\s+)?[A-Z][\w\s,.'`\-]{1,100}?"
    r"\b(?:Day|Week|Month|Year|Holiday)\b",
    re.IGNORECASE | re.DOTALL,
)

# Presidential call on Americans/the public to observe, commemorate, or attend ceremonies.
# Covers "I call upon", "I urge", "urge all Americans", "call upon the people of the
# United States to observe", etc. — the standard closing of observance proclamations.
_CALL_UPON_RE = re.compile(
    r"\b(?:I\s+)?(?:call\s+upon|urge|invite|ask)"
    r"\s+(?:all\s+)?(?:Americans?|the\s+(?:people|citizens)\s+of\s+the\s+United\s+States)\b"
    r".{0,300}?\b(?:observe|observance|commemorate|celebration|ceremonies|honor|pay\s+tribute)\b",
    re.IGNORECASE | re.DOTALL,
)

# "National Day(s) of Prayer / Remembrance / Mourning / Observance / Service / …"
_NAT_DAY_RE = re.compile(
    r"\bnational\s+days?\s+of\s+(?:prayer|remembrance|mourning|observance|service"
    r"|thanksgiving|reconciliation|unity|honor|solidarity|healing)\b",
    re.IGNORECASE,
)

# Seal or flag design approvals.
_SEAL_DESIGN_RE = re.compile(
    r"\b(?:approv\w+\s+the\s+design|design\s+of\s+the\s+(?:seal|flag)"
    r"|official\s+seal\s+of|establish\w*\s+(?:an?\s+)?(?:official\s+)?(?:seal|flag)\b)\b",
    re.IGNORECASE,
)

# Symbolic honors named in a directive title.  Requiring title language avoids broad
# false positives from policy documents that merely discuss grants, awards, or medals.
_SYMBOLIC_HONOR_TITLE_RE = re.compile(
    r"\b(?:medals?|military\s+decorations?|service\s+decorations?"
    r"|presidential\s+(?:service\s+)?(?:awards?|certificates?|badges?)"
    r"|campaign\s+(?:medals?|ribbons?)|service\s+(?:medals?|ribbons?)"
    r"|medal\s+of\s+(?:honor|freedom|valor)|national\s+security\s+medal)\b",
    re.IGNORECASE,
)

# ── Negative vetoes (any one cancels a positive match) ────────────────────────

# Trade / tariff proclamations share the "do hereby proclaim" template but are
# substantive policy actions, not ceremonial.
_TRADE_RE = re.compile(
    r"\b(?:tariff|Harmonized\s+Tariff\s+Schedule|HTSUS|duty[- ]free|trade\s+agreement"
    r"|column\s+\d+\s+(?:general|special)\s+rate|import\s+quota"
    r"|Generalized\s+System\s+of\s+Preferences|GSP\b)\b",
    re.IGNORECASE,
)

# Entry-restriction and national-emergency proclamations. Kept narrow: only veto on
# specific entry-suspension language or an explicit emergency declaration, not on
# mere references to past emergencies (which appear in otherwise ceremonial docs).
_EMERGENCY_RE = re.compile(
    r"\b(?:suspend(?:s|ed)?\s+entry|nonimmigrant"
    r"|declar\w+\s+(?:a\s+)?national\s+emergency)\b",
    re.IGNORECASE,
)

_VETO_PATTERNS = [_TRADE_RE, _EMERGENCY_RE]


def ceremonial_reason(row: dict) -> str | None:
    """Return the codebook reason for exclusion, or ``None`` when in scope."""
    document_type = row.get("doc_type", "")
    text = row.get("doc_text", "")
    title = row.get("title", "") or row.get("url", "").rstrip("/").rsplit("/", 1)[-1]

    if any(pat.search(text) for pat in _VETO_PATTERNS):
        return None
    if _HALF_STAFF_RE.search(text):
        return "memorial_half_staff"
    if _SEAL_DESIGN_RE.search(text) and (
        document_type == "proclamation" or re.search(r"\b(?:seal|flag)\b", title, re.I)
    ):
        return "symbol_design"
    if _CALL_UPON_RE.search(text):
        return "public_commemoration"
    if _SYMBOLIC_HONOR_TITLE_RE.search(title.replace("-", " ")):
        return "symbolic_honor"
    if document_type == "proclamation":
        if _OBSERVANCE_RE.search(text):
            return "observance_designation"
        if _NAT_DAY_RE.search(text):
            return "national_observance"
    return None


def is_ceremonial(row: dict) -> bool:
    """Return whether a directive is ceremonial under the project codebook."""
    return ceremonial_reason(row) is not None
