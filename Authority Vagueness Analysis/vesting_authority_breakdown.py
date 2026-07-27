"""Report the specificity of authority cited in presidential vesting clauses.

Run from the project root:
  python3 "Authority Vagueness Analysis/vesting_authority_breakdown.py"
"""

import argparse
import html
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
if MODULE_DIR.name != "src":
    sys.path.insert(0, str(MODULE_DIR.parent / "src"))

from vesting_authority_stats import (
    DEFAULT_DEV,
    DEFAULT_HOLDOUT,
    EXPECTED_FULL_CORPUS_SIZE,
    PRESIDENTIAL_TITLE_INVOCATION_RE,
    extract_vesting_clauses,
    load_corpus,
)


ANALYSIS_DIR = Path(__file__).resolve().parent
DEFAULT_HTML = ANALYSIS_DIR / "README.html"

CATEGORIES = (
    "generic_constitution_only",
    "specific_constitution_only",
    "specific_constitutional_provision_only",
    "generic_statute_only",
    "act_of_congress_only",
    "specific_statutory_section_only",
    "generic_constitution_and_generic_statute",
    "generic_constitution_and_act_of_congress",
    "generic_constitution_and_specific_statutory_section",
    "specific_constitution_and_generic_statute",
    "specific_constitution_and_act_of_congress",
    "specific_constitution_and_specific_statutory_section",
    "specific_constitutional_provision_and_generic_statute",
    "specific_constitutional_provision_and_act_of_congress",
    "specific_constitutional_provision_and_specific_statutory_section",
    "no_vesting_clause",
    "other_vesting_authority",
)

CATEGORY_LABELS = {
    "generic_constitution_only": "(1) Generic Constitution only",
    "specific_constitution_only": "(2) Specific Constitution only",
    "specific_constitutional_provision_only": "(3) Specific constitutional provision only",
    "generic_statute_only": "(4) Generic Statute only",
    "act_of_congress_only": "(5) Act of Congress only",
    "specific_statutory_section_only": "(6) Specific statutory section only",
    "generic_constitution_and_generic_statute": "(7) Generic Constitution + Generic Statute",
    "generic_constitution_and_act_of_congress": "(8) Generic Constitution + Act of Congress",
    "generic_constitution_and_specific_statutory_section": (
        "(9) Generic Constitution + Specific statutory section"
    ),
    "specific_constitution_and_generic_statute": "(10) Specific Constitution + Generic Statute",
    "specific_constitution_and_act_of_congress": "(11) Specific Constitution + Act of Congress",
    "specific_constitution_and_specific_statutory_section": (
        "(12) Specific Constitution + Specific statutory section"
    ),
    "specific_constitutional_provision_and_generic_statute": (
        "(13) Specific constitutional provision + Generic Statute"
    ),
    "specific_constitutional_provision_and_act_of_congress": (
        "(14) Specific constitutional provision + Act of Congress"
    ),
    "specific_constitutional_provision_and_specific_statutory_section": (
        "(15) Specific constitutional provision + Specific statutory section"
    ),
    "no_vesting_clause": "(16) No vesting clause",
    "other_vesting_authority": "(17) Other/unclassified vesting authority",
}

CATEGORY_DESCRIPTIONS = {
    "generic_constitution_only": "The Constitution is cited without statutory authority.",
    "specific_constitution_only": (
        "A constitutional Article or the Chief Executive role is cited, without a more "
        "specific constitutional provision or statutory authority."
    ),
    "specific_constitutional_provision_only": (
        "A constitutional section, Amendment, named Clause, Commander in Chief role, "
        "or pardon/reprieve power is cited without statutory authority."
    ),
    "generic_statute_only": "Generic law or statute wording is cited without constitutional authority.",
    "act_of_congress_only": (
        "A named or referenced Act, numbered Public Law, Act of Congress, or authorizing "
        "joint resolution is cited without constitutional authority or a specific statutory section."
    ),
    "specific_statutory_section_only": (
        "A statutory section or subsection, U.S.C. provision, title, or chapter is cited "
        "without constitutional authority."
    ),
    "generic_constitution_and_generic_statute": (
        "Generic constitutional and statutory authority are both cited."
    ),
    "generic_constitution_and_act_of_congress": (
        "Generic constitutional authority and an Act of Congress are cited."
    ),
    "generic_constitution_and_specific_statutory_section": (
        "Generic constitutional authority and a specific statutory section are cited."
    ),
    "specific_constitution_and_generic_statute": (
        "A constitutional Article or the Chief Executive role and generic statutory authority are cited."
    ),
    "specific_constitution_and_act_of_congress": (
        "A constitutional Article or the Chief Executive role and an Act of Congress are cited."
    ),
    "specific_constitution_and_specific_statutory_section": (
        "A constitutional Article or the Chief Executive role and a specific statutory section are cited."
    ),
    "specific_constitutional_provision_and_generic_statute": (
        "A specific constitutional provision and generic statutory authority are cited."
    ),
    "specific_constitutional_provision_and_act_of_congress": (
        "A specific constitutional provision and an Act of Congress are cited."
    ),
    "specific_constitutional_provision_and_specific_statutory_section": (
        "A specific constitutional provision and a specific statutory section are cited."
    ),
    "no_vesting_clause": "No vesting clause was extracted.",
    "other_vesting_authority": (
        "A vesting clause was extracted, but no constitutional or statutory authority was classified."
    ),
}

COMBINATION_CATEGORIES = {
    ("generic_constitution", None): "generic_constitution_only",
    ("specific_constitution", None): "specific_constitution_only",
    ("specific_constitutional_provision", None): "specific_constitutional_provision_only",
    (None, "generic_statute"): "generic_statute_only",
    (None, "act_of_congress"): "act_of_congress_only",
    (None, "specific_statutory_section"): "specific_statutory_section_only",
    ("generic_constitution", "generic_statute"): "generic_constitution_and_generic_statute",
    ("generic_constitution", "act_of_congress"): "generic_constitution_and_act_of_congress",
    ("generic_constitution", "specific_statutory_section"): (
        "generic_constitution_and_specific_statutory_section"
    ),
    ("specific_constitution", "generic_statute"): "specific_constitution_and_generic_statute",
    ("specific_constitution", "act_of_congress"): "specific_constitution_and_act_of_congress",
    ("specific_constitution", "specific_statutory_section"): (
        "specific_constitution_and_specific_statutory_section"
    ),
    ("specific_constitutional_provision", "generic_statute"): (
        "specific_constitutional_provision_and_generic_statute"
    ),
    ("specific_constitutional_provision", "act_of_congress"): (
        "specific_constitutional_provision_and_act_of_congress"
    ),
    ("specific_constitutional_provision", "specific_statutory_section"): (
        "specific_constitutional_provision_and_specific_statutory_section"
    ),
}

VIEWS = {
    "all": "All directives",
    "executive_order": "Executive orders",
    "memorandum": "Memoranda",
    "letter": "Letters",
    "proclamation": "Proclamations",
}

CONSTITUTION_WORD = (
    r"(?:Constitution|Constitutuion|Constutition|Constitutioin|Cosntitution)"
    r"(?:\s+of\s+the\s+United\s+States(?:\s+of\s+America)?)?"
)
US_JURISDICTION = r"United\s+States(?:\s+of\s+America)?"
LAW_WORD = r"(?:laws?|statutes?|statues)"
SECTION_LOCATOR = r"[0-9IVXLC]+[A-Za-z]?(?:\s*\([A-Za-z0-9]+\))*"

CONSTITUTION_RE = re.compile(
    rf"\b(?:the\s+)?{CONSTITUTION_WORD}\b(?!\s+Week\b)",
    re.I,
)
CONSTITUTIONAL_AUTHORITY_RE = re.compile(
    rf"\b(?:my|the\s+President'?s|his|her)\s+(?:constitutional\s+authority|"
    rf"authority\s+under\s+(?:the\s+)?{CONSTITUTION_WORD})\b",
    re.I,
)
COMBINED_RE = re.compile(
    rf"\b(?:the\s+)?{CONSTITUTION_WORD}\s*,?\s*(?:and\s+)?(?:the\s+)?"
    rf"{LAW_WORD}(?:\s+of\s+(?:the\s+)?{US_JURISDICTION})?\b",
    re.I,
)
US_LAW_RE = re.compile(
    rf"\b(?:by|under|pursuant\s+to)\s+(?:the\s+)?{LAW_WORD}\s+of\s+"
    rf"(?:the\s+)?{US_JURISDICTION}\b",
    re.I,
)
BARE_LAW_RE = re.compile(
    r"\b(?:by|under|pursuant\s+to)\s+(?:the\s+|applicable\s+)?(?:law|laws|statute|statutes)\b"
    r"|\bauthority\s+(?:granted|conferred)\s+(?:to\s+me\s+)?by\s+law\b",
    re.I,
)

ARTICLE_RE = re.compile(
    rf"\bArticle\s+[IVXLC\d]+(?:\s*,?\s*(?:Sections?\s+{SECTION_LOCATOR}"
    rf"(?:\s*(?:,|and)\s*{SECTION_LOCATOR})*|paragraph\s+{SECTION_LOCATOR}))?"
    rf"\s*,?\s*(?:of\s+)?(?:the\s+)?{CONSTITUTION_WORD}\b",
    re.I,
)
SECTION_OF_ARTICLE_RE = re.compile(
    rf"\bSections?\s+{SECTION_LOCATOR}(?:\s*(?:,|and)\s*{SECTION_LOCATOR})*"
    rf"\s+of\s+Article\s+[IVXLC\d]+\s+of\s+(?:the\s+)?{CONSTITUTION_WORD}\b",
    re.I,
)
CHIEF_EXECUTIVE_RE = re.compile(
    r"\bChief\s+Executive(?:\s+Officer\s+of\s+the\s+United\s+States)?\b",
    re.I,
)
COMMANDER_RE = re.compile(r"\bCommander[-\s]+in[-\s]+Chief\b", re.I)
AMENDMENT_RE = re.compile(
    r"\b(?:\d+(?:st|nd|rd|th)|First|Second|Third|Fourth|Fifth|Sixth|Seventh|"
    r"Eighth|Ninth|Tenth|Eleventh|Twelfth|Thirteenth|Fourteenth|Fifteenth|"
    r"Sixteenth|Seventeenth|Eighteenth|Nineteenth|Twentieth|Twenty-First|"
    r"Twenty-Second|Twenty-Third|Twenty-Fourth|Twenty-Fifth|Twenty-Sixth|"
    r"Twenty-Seventh)\s+Amendment\b",
    re.I,
)
NAMED_CLAUSE_RE = re.compile(r"\b[A-Z][A-Za-z-]+(?:\s+[A-Z][A-Za-z-]+){0,3}\s+Clause\b")
PARDON_RE = re.compile(
    r"\b(?:power|authority)\s+to\s+grant\s+(?:reprieves?|pardons?)\b"
    r"|\b(?:pardon|reprieve)\s+power\b",
    re.I,
)

PUBLIC_LAW_RE = re.compile(
    r"\bPublic\s+Laws?\s+(?:No\.?\s*)?\d+(?:\s*[-–—]\s*\d+)?\b",
    re.I,
)
JOINT_RESOLUTION_RE = re.compile(r"\b(?:joint|concurrent)\s+resolution\b", re.I)
CONGRESSIONAL_RESOLUTION_RE = re.compile(
    r"\b(?:those|these|the|such|said|aforesaid)\s+resolutions?\s+of\s+(?:the\s+)?Congress\b",
    re.I,
)
ACT_OF_CONGRESS_RE = re.compile(r"\b(?:an?|the|any)\s+acts?\s+of\s+Congress\b", re.I)
DATED_ACT_RE = re.compile(
    r"\b(?:the\s+)?act\s+of\s+(?:January|February|March|April|May|June|July|"
    r"August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b",
    re.I,
)
NAMED_ACT_RE = re.compile(
    r"\b(?:the\s+)?(?:[A-Z][A-Za-z0-9'’&.()/-]*\s+){1,12}Act(?:\s+of\s+\d{4})?\b"
)
REFERENCED_ACT_RE = re.compile(r"\b(?:the|this|such|said|aforesaid)\s+Act\b", re.I)

USC_RE = re.compile(
    r"\b\d+\s+U\.?\s*S\.?\s*[CG]\.?\s*,?\s*(?:§{1,2}\s*)?"
    r"(?:\(\d{4}\)\s*)?(?:App\.?|ch\.?\s*\d+[A-Za-z]?|"
    r"\d+[A-Za-z]?(?:\s*\([A-Za-z0-9]+\))*)",
    re.I,
)
US_CODE_TITLE_RE = re.compile(
    rf"\b(?:sections?\s+{SECTION_LOCATOR}(?:\s*(?:,|and)\s*{SECTION_LOCATOR})*\s+of\s+)?"
    r"title\s+[IVXLC\d]+\s*(?:,|of\s+the)?\s+United\s+States\s+Code\b",
    re.I,
)
CHAPTER_TITLE_RE = re.compile(
    r"\bchapter\s+\d+[A-Za-z]?\s+of\s+title\s+\d+\b",
    re.I,
)
SECTION_RE = re.compile(rf"\bsections?\s+{SECTION_LOCATOR}", re.I)
NONSTATUTORY_SECTION_RE = re.compile(
    rf"^\s*,?\s+of\s+(?:(?:the\s+)?{CONSTITUTION_WORD}|Article|Executive\s+Order|Proclamation|Treaty|Agreement|"
    r"this\s+(?:order|proclamation|directive))\b",
    re.I,
)

AUTHORITY_MARKER_RE = re.compile(
    r"\b(?:authority\s+(?:vested|conferred|granted)|vested\s+in\s+me|"
    r"by\s+virtue\s+of\s+the\s+authority|pursuant\s+to|acting\s+under\s+the\s+authority|"
    r"under\s+the\s+authority)\b",
    re.I,
)
EXCLUDED_TAIL_RE = re.compile(
    r"(?:,\s*(?:and\s+)?|\s+and\s+)(?:consistent\s+with|in\s+accordance\s+with|in\s+order\s+to|"
    r"in\s+furtherance\s+of|in\s+light\s+of|in\s+recognition\s+of|"
    r"in\s+view\s+of|bearing\s+in\s+mind|as\s+contemplated\s+by|"
    r"for\s+the\s+purpose\s+of|having\s+(?:determined|found)|to\s+[A-Za-z]+)\b",
    re.I,
)
RECITAL_SPLIT_RE = re.compile(
    r"(?=\bWhereas\b|\bNow,?\s+Therefore\b|\bBy\s+the\s+President\b)",
    re.I,
)
PRESIDENT_AUTHORIZED_RE = re.compile(
    r"\b(?:(?:authorizes?|authorized|empowers?|empowered|directs?|directed)\s+"
    r"(?:the\s+)?President\s+to|(?:the\s+)?President\s+"
    r"(?:is\s+|was\s+|has\s+been\s+)?(?:authorized|empowered|directed)\s+to)\b",
    re.I,
)
FIRST_PERSON_AUTHORITY_RE = re.compile(
    r"\b(?:my\s+(?:constitutional\s+)?(?:authority|powers?)|"
    r"(?:the\s+)?(?:authority|powers?)\s+(?:vested|conferred|granted)\s+"
    r"(?:in|upon|to)\s+me|vested\s+in\s+me)\b",
    re.I,
)
POSSIBLE_VESTING_RE = re.compile(
    r"vested\s+in\s+me|by\s+virtue\s+of\s+the\s+authority|"
    r"\bnow,?\s+therefore,?\s+i\b|\bpursuant\s+to\b|"
    r"\b(?:joint\s+resolution|public\s+law)\b|"
    r"\bunder\s+(?:section|title|the\s+authority)\b",
    re.I,
)


def extract_authority_spans(clauses: list[str]) -> list[str]:
    """Keep asserted authority sources and discard compliance or purpose citations."""
    spans = []
    for clause in clauses:
        normalized = re.sub(r"\s+", " ", clause).strip()
        for unit in filter(None, (part.strip() for part in RECITAL_SPLIT_RE.split(normalized))):
            marker = AUTHORITY_MARKER_RE.search(unit)
            authorized = PRESIDENT_AUTHORIZED_RE.search(unit)
            first_person = FIRST_PERSON_AUTHORITY_RE.search(unit)
            if re.match(r"^Whereas\b", unit, re.I) and not authorized and not first_person:
                continue
            if not marker and not authorized:
                continue

            start = marker.start() if marker else 0
            end = len(unit)
            excluded = EXCLUDED_TAIL_RE.search(unit, start)
            if excluded:
                end = excluded.start()
            span = unit[start:end].strip(" ,;:")
            if span:
                spans.append(span)
    return spans


def _has_specific_statutory_section(text: str) -> bool:
    if USC_RE.search(text) or US_CODE_TITLE_RE.search(text) or CHAPTER_TITLE_RE.search(text):
        return True
    for match in SECTION_RE.finditer(text):
        if not NONSTATUTORY_SECTION_RE.match(text[match.end():match.end() + 90]):
            return True
    return False


def classify_authority_category(clauses: list[str]) -> str:
    """Return the one document-level category that applies to extracted vesting clauses."""
    if not clauses:
        return "no_vesting_clause"

    spans = extract_authority_spans(clauses)
    authority_text = " ".join(spans)
    if not authority_text:
        return "other_vesting_authority"

    has_constitution = bool(CONSTITUTION_RE.search(authority_text) or CONSTITUTIONAL_AUTHORITY_RE.search(authority_text))
    has_combined = bool(COMBINED_RE.search(authority_text))
    has_generic_law = bool(US_LAW_RE.search(authority_text) or BARE_LAW_RE.search(authority_text))

    article_matches = list(ARTICLE_RE.finditer(authority_text))
    article_has_subpart = any(re.search(r"\b(?:Sections?|paragraph)\b", match.group(0), re.I) for match in article_matches)
    has_constitutional_provision = bool(
        article_has_subpart
        or SECTION_OF_ARTICLE_RE.search(authority_text)
        or COMMANDER_RE.search(authority_text)
        or AMENDMENT_RE.search(authority_text)
        or NAMED_CLAUSE_RE.search(authority_text)
        or PARDON_RE.search(authority_text)
    )
    has_specific_constitution = bool(article_matches or CHIEF_EXECUTIVE_RE.search(authority_text))

    has_act = bool(
        PUBLIC_LAW_RE.search(authority_text)
        or JOINT_RESOLUTION_RE.search(authority_text)
        or CONGRESSIONAL_RESOLUTION_RE.search(authority_text)
        or ACT_OF_CONGRESS_RE.search(authority_text)
        or DATED_ACT_RE.search(authority_text)
        or NAMED_ACT_RE.search(authority_text)
        or REFERENCED_ACT_RE.search(authority_text)
    )
    has_statutory_section = _has_specific_statutory_section(authority_text)
    if has_constitutional_provision:
        constitutional_category = "specific_constitutional_provision"
    elif has_specific_constitution:
        constitutional_category = "specific_constitution"
    elif has_constitution:
        constitutional_category = "generic_constitution"
    else:
        constitutional_category = None

    if has_statutory_section:
        statutory_category = "specific_statutory_section"
    elif has_act:
        statutory_category = "act_of_congress"
    elif has_generic_law or has_combined:
        statutory_category = "generic_statute"
    else:
        statutory_category = None

    if constitutional_category is None and statutory_category is None:
        return "other_vesting_authority"
    return COMBINATION_CATEGORIES[(constitutional_category, statutory_category)]


def analyze(rows: list[dict]) -> tuple[list[dict], Counter, Counter]:
    output = []
    counts = Counter()
    administration_totals = Counter()
    for row in rows:
        text = row["doc_text"]
        if POSSIBLE_VESTING_RE.search(text) or PRESIDENTIAL_TITLE_INVOCATION_RE.search(text):
            clauses = extract_vesting_clauses(text, row["doc_type"])
        else:
            clauses = []
        category = classify_authority_category(clauses)
        administration = f"{row['president']} ({row['term']})"
        administration_totals[(administration, "all")] += 1
        administration_totals[(administration, row["doc_type"])] += 1
        administration_totals[("total", "all")] += 1
        administration_totals[("total", row["doc_type"])] += 1
        counts[(administration, "all", category)] += 1
        counts[(administration, row["doc_type"], category)] += 1
        counts[("total", "all", category)] += 1
        counts[("total", row["doc_type"], category)] += 1
        output.append(
            {
                "document_id": row[""],
                "administration": administration,
                "category": category,
            }
        )
    return output, counts, administration_totals


def administration_order(rows: list[dict]) -> list[str]:
    first_dates = {}
    for row in rows:
        administration = f"{row['president']} ({row['term']})"
        date = datetime.strptime(row["date"], "%B %d, %Y")
        first_dates[administration] = min(date, first_dates.get(administration, date))
    return sorted(first_dates, key=first_dates.get)


def _heat_class(percent: float) -> str:
    if percent == 0:
        return "heat-0"
    if percent < 1:
        return "heat-1"
    if percent < 5:
        return "heat-2"
    if percent < 15:
        return "heat-3"
    if percent < 35:
        return "heat-4"
    return "heat-5"


def validate_category_totals(
    counts: Counter,
    administrations: list[str],
    administration_totals: Counter,
) -> None:
    for view in VIEWS:
        for administration in (*administrations, "total"):
            category_sum = sum(counts[(administration, view, category)] for category in CATEGORIES)
            directive_total = administration_totals[(administration, view)]
            if category_sum != directive_total:
                raise ValueError(
                    f"category total mismatch for {administration}, {view}: "
                    f"{category_sum:,} categories != {directive_total:,} directives"
                )


def render_html(
    counts: Counter,
    document_count: int,
    administrations: list[str],
    administration_totals: Counter,
) -> str:
    if administration_totals[("total", "all")] != document_count:
        raise ValueError(
            f"directive total mismatch: report has {document_count:,} directives, "
            f"counts have {administration_totals[('total', 'all')]:,}"
        )
    validate_category_totals(counts, administrations, administration_totals)
    table_bodies = []
    for view in VIEWS:
        count_rows = []
        for administration in (*administrations, "total"):
            denominator = administration_totals[(administration, view)]
            category_sum = sum(counts[(administration, view, category)] for category in CATEGORIES)
            label = "All administrations" if administration == "total" else administration
            cells = []
            for category in CATEGORIES:
                count = counts[(administration, view, category)]
                if denominator:
                    percent = 100 * count / denominator
                    cells.append(
                        f'<td class="count {_heat_class(percent)}" title="{percent:.2f}% of this administration">'
                        f'<b>{count:,}</b><span class="pct">{percent:.1f}%</span></td>'
                    )
                else:
                    cells.append('<td class="count heat-0 empty" title="No directives of this type">-</td>')
            count_rows.append(
                f'<tr class="{"total-row" if administration == "total" else ""}">'
                f'<th scope="row">{html.escape(label)}</th>{"".join(cells)}'
                f'<td class="count total"><b>{category_sum:,}</b></td>'
                f'<td class="count total"><b>{denominator:,}</b></td>'
                f'<td class="check pass"><b>PASS</b></td></tr>'
            )
        table_bodies.append(
            f'<tbody data-view="{view}"{"" if view == "all" else " hidden"}>'
            f'{"".join(count_rows)}</tbody>'
        )

    definitions = "".join(
        f"<tr><th scope=\"row\">{html.escape(CATEGORY_LABELS[category])}</th>"
        f"<td>{html.escape(CATEGORY_DESCRIPTIONS[category])}</td></tr>"
        for category in CATEGORIES
    )
    headers = "".join(
        f'<th scope="col"><abbr title="{html.escape(CATEGORY_LABELS[category])}">'
        f'({index})</abbr></th>'
        for index, category in enumerate(CATEGORIES, 1)
    )
    view_buttons = "".join(
        f'<button type="button" data-view="{view}" aria-pressed="{"true" if view == "all" else "false"}">'
        f'{html.escape(label)}</button>'
        for view, label in VIEWS.items()
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Vesting Authority Specificity Analysis</title>
  <style>
    :root {{ color: #202936; background: #f5f7fa; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.5; }}
    body {{ margin: 0; }}
    main {{ max-width: 1280px; margin: 0 auto; padding: 32px 20px 48px; }}
    h1 {{ margin: 0 0 10px; font-size: 30px; line-height: 1.2; letter-spacing: 0; }}
    h2 {{ margin: 30px 0 10px; font-size: 21px; letter-spacing: 0; }}
    p {{ margin: 0 0 14px; }}
    .table-wrap {{ overflow-x: auto; margin: 12px 0 18px; border: 1px solid #cfd7e3; background: #fff; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 780px; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid #e2e7ee; text-align: left; vertical-align: top; }}
    thead th {{ background: #e8edf4; white-space: nowrap; }}
    tbody tr:last-child th, tbody tr:last-child td {{ border-bottom: 0; }}
    tbody th {{ font-weight: 650; }}
    .administration-table {{ min-width: 1780px; }}
    .administration-table tbody th {{ position: sticky; left: 0; z-index: 1; min-width: 210px; background: #fff; }}
    .administration-table .total-row th {{ background: #e8edf4; }}
    .count {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
    .count b {{ display: block; }}
    .pct {{ display: block; margin-top: 1px; color: #4c5968; font-size: 12px; }}
    .heat-0 {{ background: #fff; }}
    .heat-1 {{ background: #eef6f3; }}
    .heat-2 {{ background: #d9ebe5; }}
    .heat-3 {{ background: #b9d9cf; }}
    .heat-4 {{ background: #83b9aa; }}
    .heat-5 {{ background: #47917e; color: #fff; }}
    .heat-5 .pct {{ color: #fff; }}
    .total-row th, .total-row td {{ border-top: 2px solid #8795a8; }}
    .total {{ background: #f2f4f7; }}
    .check {{ text-align: center; white-space: nowrap; }}
    .pass {{ background: #d9ebe5; color: #245c4d; }}
    abbr {{ text-decoration: none; cursor: help; }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 8px 0 14px; font-size: 13px; color: #4c5968; }}
    .swatch {{ display: inline-block; width: 16px; height: 16px; margin-right: 5px; border: 1px solid #cfd7e3; vertical-align: -3px; }}
    .view-toggle {{ display: inline-flex; max-width: 100%; overflow-x: auto; margin: 4px 0 12px; border: 1px solid #aab5c3; background: #fff; }}
    .view-toggle button {{ min-height: 38px; padding: 7px 12px; border: 0; border-right: 1px solid #cfd7e3; background: #fff; color: #202936; font: inherit; font-size: 14px; white-space: nowrap; cursor: pointer; }}
    .view-toggle button:last-child {{ border-right: 0; }}
    .view-toggle button[aria-pressed="true"] {{ background: #263d55; color: #fff; font-weight: 650; }}
    .view-toggle button:focus-visible {{ outline: 3px solid #d29b42; outline-offset: -3px; }}
    [hidden] {{ display: none !important; }}
    .note {{ border-left: 4px solid #4f657e; padding: 10px 14px; background: #fff; }}
    code {{ background: #e9edf2; padding: 1px 4px; border-radius: 3px; }}
  </style>
</head>
<body>
<main>
  <h1>Vesting Authority Specificity Analysis</h1>
  <p>This report analyzes {document_count:,} presidential directives in the development and holdout corpora. Each presidential term is reported as a separate administration.</p>
  <p class="note"><strong>Mutually exclusive categories.</strong> Every directive receives exactly one category. Constitutional and statutory specificity are classified independently and then combined: a specific constitutional provision supersedes a constitutional Article or role, and a specific statutory section supersedes an Act of Congress. Additional citations to Executive Orders, treaties, agreements, or similar authorities do not displace a recognized constitutional/statutory combination. Category sums are checked against directive totals for every administration and directive-type view.</p>

  <h2>Counts by Administration</h2>
  <p>Each cell gives the number of matching directives and its share of the selected directive type in that administration. The background color provides an absolute percentage heatmap.</p>
  <div class="view-toggle" role="group" aria-label="Directive type">{view_buttons}</div>
  <div class="legend" aria-label="Heatmap legend">
    <span><i class="swatch heat-0"></i>0%</span><span><i class="swatch heat-1"></i>Less than 1%</span><span><i class="swatch heat-2"></i>1-4.9%</span><span><i class="swatch heat-3"></i>5-14.9%</span><span><i class="swatch heat-4"></i>15-34.9%</span><span><i class="swatch heat-5"></i>35% or more</span>
  </div>
  <div class="table-wrap">
    <table class="administration-table">
      <thead><tr><th scope="col">Administration</th>{headers}<th scope="col">Category sum</th><th scope="col">Directives</th><th scope="col">Check</th></tr></thead>
      {''.join(table_bodies)}
    </table>
  </div>

  <h2>Category Definitions</h2>
  <div class="table-wrap">
    <table>
      <thead><tr><th scope="col">Category</th><th scope="col">Rule</th></tr></thead>
      <tbody>{definitions}</tbody>
    </table>
  </div>

  <h2>Method</h2>
  <p>The analysis first applies the project's existing vesting-clause extractor. Within each extracted clause, it retains sources presented as presidential authority through wording such as <code>by</code>, <code>under</code>, <code>pursuant to</code>, <code>including</code>, or <code>authority conferred/granted by</code>. A proclamation's <code>Whereas</code> recital is retained only when it makes a first-person authority assertion or states that Congress or law authorizes, empowers, or directs the President to act. Contextual uses of <code>pursuant to</code> within other recitals are discarded.</p>
  <p>Citations appearing only as compliance, purpose, or context are excluded, including citations following <code>consistent with</code>, <code>in accordance with</code>, <code>in order to</code>, <code>in furtherance of</code>, <code>in light of</code>, and <code>as contemplated by</code>. Matching tolerates capitalization, punctuation, singular/plural forms, and observed OCR variants; it does not use fuzzy matching.</p>
</main>
<script>
  const buttons = document.querySelectorAll('.view-toggle button');
  const bodies = document.querySelectorAll('.administration-table tbody');
  for (const button of buttons) {{
    button.addEventListener('click', () => {{
      const view = button.dataset.view;
      for (const candidate of buttons) {{
        candidate.setAttribute('aria-pressed', String(candidate === button));
      }}
      for (const body of bodies) {{
        body.hidden = body.dataset.view !== view;
      }}
    }});
  }}
</script>
</body>
</html>
"""


def write_html(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev", type=Path, default=DEFAULT_DEV)
    parser.add_argument("--holdout", type=Path, default=DEFAULT_HOLDOUT)
    parser.add_argument("--html", type=Path, default=DEFAULT_HTML)
    args = parser.parse_args()

    rows = load_corpus([args.dev, args.holdout])
    if args.dev == DEFAULT_DEV and args.holdout == DEFAULT_HOLDOUT and len(rows) != EXPECTED_FULL_CORPUS_SIZE:
        raise ValueError(f"expected {EXPECTED_FULL_CORPUS_SIZE:,} full-corpus documents, found {len(rows):,}")
    _, counts, administration_totals = analyze(rows)
    administrations = administration_order(rows)
    write_html(args.html, render_html(counts, len(rows), administrations, administration_totals))
    print(f"\nHTML: {args.html} ({len(rows):,} directives)")


if __name__ == "__main__":
    main()
