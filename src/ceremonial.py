"""
Heuristic classifier for ceremonial proclamations.

Ceremonial proclamations — national holidays/observances, half-staff memorials,
seal/flag design approvals — fall outside the definition of unilateral presidential
action and are excluded from analysis samples when --exclude-ceremonial is passed.

Only proclamations are tested; all other doc types return False.
"""

import re

# ── Positive signals (any one marks a row as ceremonial) ──────────────────────

# Half-staff / half-mast memorial orders. Very high precision.
_HALF_STAFF_RE = re.compile(r"\bhalf[- ]?(?:staff|mast)\b", re.IGNORECASE)

# "do hereby (proclaim|designate|request|urge|...) ... as [National] X Day/Week/Month/Year/Holiday"
# Covers the main observance-designation formula and its common variants.
# Bounded to 400 chars so the match doesn't span multiple paragraphs.
_OBSERVANCE_RE = re.compile(
    r"\bdo\s+hereby\s+(?:proclaim|designate|request|urge|invite|ask|call\s+upon|affirm)\b"
    r".{0,400}?\bas\s+(?:National\s+|the\s+)?[A-Z][\w\s,.'`\-]{1,100}?"
    r"\b(?:Day|Week|Month|Year|Holiday)\b",
    re.IGNORECASE | re.DOTALL,
)

# Presidential call on Americans/the public to observe, commemorate, or attend ceremonies.
# Covers "I call upon", "I urge", "urge all Americans", "call upon the people of the
# United States to observe", etc. — the standard closing of observance proclamations.
_CALL_UPON_RE = re.compile(
    r"\b(?:I\s+)?(?:call\s+upon|urge|invite|ask)"
    r"\s+(?:all\s+)?(?:Americans?|the\s+people\s+of\s+the\s+United\s+States)\b"
    r".{0,300}?\b(?:observe|observance|commemorate|celebration|ceremonies)\b",
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
    r"\b(?:approv\w+\s+the\s+design|design\s+of\s+the\s+(?:seal|flag)|official\s+seal\s+of)\b",
    re.IGNORECASE,
)

_POSITIVE_PATTERNS = [
    _HALF_STAFF_RE,
    _OBSERVANCE_RE,
    _CALL_UPON_RE,
    _NAT_DAY_RE,
    _SEAL_DESIGN_RE,
]

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


def is_ceremonial(row: dict) -> bool:
    """Return True if the row is a ceremonial proclamation that should be excluded.

    Ceremonial proclamations are national holidays/observances, half-staff memorial
    orders, and seal/flag design approvals. Returns False for all non-proclamation
    doc types so it is safe to call on any row.
    """
    if row.get("doc_type") != "proclamation":
        return False

    text = row.get("doc_text", "")

    if not any(pat.search(text) for pat in _POSITIVE_PATTERNS):
        return False

    if any(pat.search(text) for pat in _VETO_PATTERNS):
        return False

    return True
