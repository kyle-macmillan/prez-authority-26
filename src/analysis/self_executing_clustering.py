"""Build self-executing × vesting-authority cross-tab with scope clustering.

Produces:
  data/self_executing_sample75_claude_recode.csv  -- Claude's independent SE coding
  data/self_executing_review.html                 -- interactive review doc

Run from project root:
  python3 src/analysis/self_executing_clustering.py
"""

import csv
import json
import re
from collections import Counter
from pathlib import Path
from html import escape

ROOT = Path(__file__).parents[2]

# ---------------------------------------------------------------------------
# Claude's independent self-executing classifications
# Coded by reading operative language; rationale quotes key operative phrase.
# Disagreements with existing coding noted in rationale.
# ---------------------------------------------------------------------------

# fmt: off
CLAUDE_CODES = {
    # --- Executive Orders ---
    "EO1":  ("not_self_executing", "false", '"agencies shall take all appropriate actions within their authority...to combat wildlife trafficking" — principally directs agencies to take action.'),
    "EO2":  ("not_self_executing", "false", '"All executive departments and agencies shall...respect and protect" — directs agencies; "the Secretary of the Treasury shall ensure..."'),
    "EO3":  ("self_executing",     "false", '"Executive Order No. 10530...be, and it is hereby, amended as follows" — directly amends prior EO, effective on signing.'),
    "EO4":  ("not_self_executing", "false", '"Each executive department and agency...shall, to the maximum extent permitted by law" — directs agencies to create programs.'),
    "EO5":  ("self_executing",     "false", '"Executive Order 12989...is further amended" — directly amends prior EO, effective on signing.'),
    "EO6":  ("self_executing",     "false", '"Executive Order No. 10016...is hereby revoked" — directly establishes VP coat of arms, seal, and flag design; revokes prior EO.'),
    "EO7":  ("self_executing",     "true",  '"possession, use, and control...shall be restored to the Territory of Hawaii" — conditional land transfer with immediate legal effect upon fulfillment of conditions; requires third-party certification before transfer executes.'),
    "EO8":  ("self_executing",     "false", '"The requirement of Section 205(b)(2) of Executive Order No. 10000...is suspended" — directly suspends a requirement in a prior EO, effective on signing.'),
    "EO9":  ("self_executing",     "false", '"I hereby approve such seal as the official seal of the United States Civil Service Commission" — directly approves an official seal.'),
    "EO10": ("not_self_executing", "false", '"Section 101. Policy. The Federal Government faces broad exposure to the mounting risks..." — policy statement followed by directives to agencies on climate change.'),
    "EO11": ("self_executing",     "false", '"Executive Order No. 11017...be, and it is hereby, further amended" — directly amends prior EO, effective on signing.'),
    "EO12": ("self_executing",     "false", '"the provisions for administration of that act...shall continue in full force and effect and shall authorize" — directly continues prior EO provisions notwithstanding statute expiration.'),
    "EO13": ("self_executing",     "false", '"I hereby order blocked all property and interests in property of the Government of Panama" — directly blocks property; immediate legal effect on signing.'),
    "EO14": ("self_executing",     "false", '"Executive Order 13010, as amended, is further amended by adding..." — directly amends prior EO; generic vesting authority (OLC counterexample).'),
    "EO15": ("self_executing",     "false", '"Parts II and IV of the Manual for Courts-Martial, United States, are amended as described in the Annex" — directly amends the Manual for Courts-Martial.'),
    "EO16": ("self_executing",     "false", '"I hereby order the following" — establishes the Task Force on the United States Postal System by direct presidential action; task force immediately exists.'),
    "EO17": ("self_executing",     "true",  '"sections 4 and 5 of Executive Order No. 10560...be, and they are hereby, further amended" — directly amends prior EO (effective on signing); however, amended provisions direct agency allocation of PL 480 foreign currencies. [DISAGREES with existing not_self_executing; mixed_flag=true for the agency-directive content of the amendment.]'),
    "EO18": ("self_executing",     "false", '"the National Defense Service Medal, as established" — establishes a military medal by direct presidential action, effective on signing.'),
    "EO19": ("self_executing",     "false", '"I hereby designate GRECO as a public international organization entitled to enjoy the privileges, exemptions, and immunities conferred by the Act" — directly designates an organization.'),
    "EO20": ("self_executing",     "false", '"Section 2(e) of Executive Order No. 11763...is revised to read in its entirety as follows" — directly revises prior EO; generic vesting authority (OLC counterexample).'),
    "EO21": ("self_executing",     "false", '"All existing reemployment rights...are hereby revoked" — directly revokes reemployment rights, effective on signing.'),
    "EO22": ("not_self_executing", "false", '"I hereby direct the Secretary of State to assign to the Inspector General, Foreign Service, all duties and responsibilities" — directs Secretary of State to reassign duties; requires Secretary\'s action.'),
    "EO23": ("self_executing",     "false", '"There is hereby established the President\'s Advisory Council on the Arts" — directly establishes an advisory council; the Council immediately exists by EO.'),
    "EO24": ("not_self_executing", "false", '"I am directing the Assistant to the President for National Security Affairs and the Director of the National Economic Council to lead..." — directs NSC/NEC to lead a process.'),
    "EO25": ("not_self_executing", "false", '"The Attorney General shall assist Federal departments and agencies to coordinate their programs and activities" — directs the Attorney General; primarily agency coordination directive.'),

    # --- Memoranda ---
    "M1":  ("self_executing",     "false", '"I hereby revoke my memorandum of March 31, 2010...I hereby withdraw from disposition by leasing" — directly revokes prior memo and withdraws OCS areas from leasing.'),
    "M2":  ("not_self_executing", "false", '"must further ensure that applicants for Federal funding...are not burdened by requirements" — directs agencies to streamline application processes.'),
    "M3":  ("self_executing",     "false", 'Memorandum of disapproval of a private-claims bill arising from Elephant Butte dam construction. Presidential disapproval is constitutionally immediate — the bill does not become law.'),
    "M4":  ("not_self_executing", "false", '"I am directing you and your staff to consider ways to provide leadership to advance the adoption alternative" — directs staff to consider future action.'),
    "M5":  ("not_self_executing", "false", '"I hereby direct you to take the following steps: Within 30 days, identify and report" — directs agency heads to identify and report.'),
    "M6":  ("not_self_executing", "false", 'Notification/informational memo about ceramic tableware tariff rates reverting under a prior proclamation; no directive that itself has independent legal effect.'),
    "M7":  ("not_self_executing", "false", 'Administrative directive to agency heads to report on DOJ case dispositions; requires agency reporting action.'),
    "M8":  ("self_executing",     "false", '"I determine, pursuant to Subsections 402(d)(5) and (d)(5)(c) of the Act, that the further extension of the waiver authority...will substantially promote the objectives" — formal Jackson-Vanik presidential determination under the Trade Act, effective on signing.'),
    "M9":  ("not_self_executing", "false", 'Encouragement memo about participation in United Fund/Community Chest charitable giving campaigns; no directive with legal effect.'),
    "M10": ("self_executing",     "false", '"I hereby delegate to the Secretary of State...the function vested in the President by section 301 of title 3, United States Code" — direct delegation of presidential authority under 3 U.S.C. 301, effective on signing.'),
    "M11": ("not_self_executing", "false", 'Commendatory memo about implementation of ethics EO 11222; no directive with independent legal effect.'),
    "M12": ("not_self_executing", "false", '"I ask each of you to make a commitment to removing any remaining barriers to Federal employment" — hortatory request; no directive with legal effect.'),
    "M13": ("not_self_executing", "false", 'Guidance memo directing agency action on HIV education programs; requires agency implementation.'),
    "M14": ("self_executing",     "false", '"I hereby determine that it is important to the national interest that up to $5,000,000 be made available from the U.S. Emergency Refugee and Migration Assistance Fund" — formal presidential determination making funds available under statute.'),
    "M15": ("self_executing",     "false", '"I hereby determine that the transaction...encompassing the provision of defense articles and services to foreign forces...facilitating or participating in an attack" — formal presidential determination/finding under AECA sections 40 and 40A.'),
    "M16": ("self_executing",     "false", '"I hereby delegate to the Secretary of the Treasury...the function vested in the President by section 102(d) of the Hizballah International Financing Prevention Act" — direct delegation of presidential authority, effective on signing.'),
    "M17": ("not_self_executing", "false", '"I hereby direct each department and agency...To cooperate fully with Federal, State and local civil defense authorities; to take part in this civil defense exercise" — directs departments/agencies to participate.'),
    "M18": ("not_self_executing", "false", 'Directive memo about improving Hispanic education; requires agency action to implement.'),
    "M19": ("self_executing",     "false", '"I hereby assign to you the functions of the President under section 1321 of the Act" — direct assignment/delegation of presidential statutory functions, effective on signing.'),
    "M20": ("self_executing",     "false", 'Memorandum of disapproval of nurse training legislation. Presidential disapproval is constitutionally immediate — the bill does not become law.'),
    "M21": ("not_self_executing", "false", 'Memo about coordinating the George C. Marshall Research Foundation; informational/coordinative, no directive with independent legal effect.'),
    "M22": ("not_self_executing", "false", '"is hereby established to coordinate the work of the Departments and Agencies" — establishes a domestic policy coordination system; primarily directs agencies to coordinate. Requires agency participation to function.'),
    "M23": ("not_self_executing", "false", '"The Interagency Textile Administrative Committee is to be established" — directs agencies to establish a committee; creation requires agency action.'),
    "M24": ("not_self_executing", "false", '"I am directing the Assistant to the President for National Security Affairs and the Director of the National Economic Council to lead [China censorship monitoring process]" — directs White House officials to lead a process. [DISAGREES with existing self_executing; the memo\'s title references \'establishment\' but operative language is directive.]'),
    "M25": ("not_self_executing", "false", '"you to co-chair the project and report to me within ninety days" — directs an official to co-chair and report; requires action by that official.'),

    # --- Proclamations (all self_executing) ---
    "P1":  ("self_executing", "false", '"hereby proclaim the objects identified above...to be the San Juan Islands National Monument" — directly designates a national monument under the Antiquities Act.'),
    "P2":  ("self_executing", "false", '"do proclaim that: (1) In order to modify the quantitative limitations applicable to imports of washers" — directly modifies tariff/import quotas under the Trade Act.'),
    "P3":  ("self_executing", "false", '"do proclaim that the abnormal [trade conditions exist]" — tariff proclamation under section 350(a) of the Tariff Act, modifying trade agreement terms.'),
    "P4":  ("self_executing", "false", '"do proclaim that: (1) General note 3(c)(ix)(A) to the HTS is modified" — directly modifies the Harmonized Tariff Schedule under ATPA.'),
    "P5":  ("self_executing", "false", '"do proclaim that: (1)..." — trade proclamation directly modifying tariff schedules under CAFTA-DR.'),
    "P6":  ("self_executing", "false", '"do hereby call upon the people of this Nation...to observe Wright Brothers Day, December 17, 1974" — proclamation designating an observance; the presidential declaration itself is the legally effective action.'),
    "P7":  ("self_executing", "false", '"do declare and proclaim: That...citizens of Israel are...entitled to [copyright protection]" — proclamation directly extending US copyright eligibility to Israeli nationals under 17 U.S.C.; generic vesting authority (OLC counterexample).'),
    "P8":  ("self_executing", "false", '"do proclaim" — trade proclamation under TSUS section 203/604 and the Trade Act directly modifying import quotas.'),
    "P9":  ("self_executing", "false", '"do hereby proclaim that the Emancipation Proclamation expresses our Nation\'s policy...fitting and proper to commemorate the centennial" — ceremonial proclamation designating the 1963 centennial year; no agency action required for the proclamation to take effect.'),
    "P10": ("self_executing", "false", '"do hereby proclaim May 17, 2024, as the 70th anniversary of Brown v. Board of Education" — ceremonial proclamation designating an anniversary; generic vesting authority.'),
    "P11": ("self_executing", "false", '"call upon all the people of our Nation to observe Thursday, November 11, 1965, as Veterans Day" — ceremonial proclamation designating Veterans Day; generic vesting authority.'),
    "P12": ("self_executing", "false", '"do hereby proclaim that, effective as of this date, paragraph (b) of section 4 of Proclamation No. 3279, as [amended]" — directly amends a prior proclamation, effective on signing.'),
    "P13": ("self_executing", "false", '"do hereby proclaim: (1) The Tariff Schedules of the United States (TSUS)...are modified" — directly modifies tariff schedules under section 123 of the Trade Act.'),
    "P14": ("self_executing", "false", '"do declare and proclaim that...the conditions specified in section 104(b)(5) and section 104A(g) [of title 17 have been fulfilled]" — statutory copyright proclamation declaring conditions met under the Uruguay Round Agreements Act.'),
    "P15": ("self_executing", "false", '"do hereby proclaim April 2, 2015, World Autism Awareness Day" — ceremonial proclamation designating a day; generic vesting authority.'),
    "P16": ("self_executing", "false", '"do hereby proclaim April 6 through April 12, 2025, as National Crime Victims\' Rights Week" — ceremonial proclamation designating a week; generic vesting authority.'),
    "P17": ("self_executing", "false", '"do hereby proclaim Sunday, May 10, 1959, to be Mother\'s Day; and I direct the appropriate officials...to display the flag" — proclamation designating Mother\'s Day and directing flag display.'),
    "P18": ("self_executing", "false", '"do proclaim that: (1) In order to provide for an accelerated schedule" — trade proclamation under ATPA and the 1974 Trade Act modifying duty elimination schedule.'),
    "P19": ("self_executing", "false", '"do proclaim that: (1) In order to provide..." — trade proclamation under the HOPE II Act modifying Caribbean Basin trade preferences.'),
    "P20": ("self_executing", "false", '"do hereby proclaim that the lands hereinafter described are excepted from the transfer to the Government of American Samoa" — directly establishes a land exception from statutory transfer.'),
    "P21": ("self_executing", "false", '"do hereby proclaim that the Secretary of the Treasury has found the drug Keto-bemidone...to have an addiction-forming liability" — drug scheduling proclamation with direct legal effect under narcotics laws; generic vesting authority.'),
    "P22": ("self_executing", "false", '"invite the American people to observe Thursday, May 1, 1980, as Law Day, U.S.A." — ceremonial proclamation designating Law Day.'),
    "P23": ("self_executing", "false", '"do proclaim that: PART III (A) Agreement supplementary to a trade agreement...On and after August 29, 1963, those provisions [apply]" — trade proclamation modifying GATT tariff schedules for Spain.'),
    "P24": ("self_executing", "false", '"hereby find that the unrestricted entry [would be detrimental]" — proclamation under INA section 212(f) suspending certain entry; direct legal effect on signing.'),
    "P25": ("self_executing", "false", '"urge the people of this nation to join in commemorating...Veterans Day" — ceremonial proclamation designating Veterans Day 1968; generic vesting authority.'),
}
# fmt: on


# ---------------------------------------------------------------------------
# Scope votes from 4 annotators (majority; KyleM breaks ties)
# ---------------------------------------------------------------------------

SCOPE_TIE_BREAK = {  # KyleM's vote for 2-2 ties
    "EO17": "foreign",
    "M6":   "foreign",
    "M10":  "domestic",
    "M24":  "foreign",
    "P3":   "foreign",
    "P8":   "foreign",
}


def _compute_scope(label: str, annotators: list) -> tuple[str, str]:
    """Return (majority_scope, tie_info)."""
    votes = []
    for _, d in annotators:
        c = d.get(label, {}).get("classification") or {}
        s = c.get("scope")
        if s:
            votes.append(s)
    ct = Counter(votes)
    total = sum(ct.values())
    if total == 0:
        return "unknown", ""
    top, top_n = ct.most_common(1)[0]
    if top_n > total / 2:
        return top, ""
    # tie
    tiebreak = SCOPE_TIE_BREAK.get(label, top)
    return tiebreak, "tie"


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

def load_annotators() -> list:
    result_dir = ROOT / "data" / "sample_100" / "results"
    annotators = []
    for f in sorted(result_dir.glob("*.json")):
        d = json.loads(f.read_text())
        annotators.append((d.get("annotator", f.stem), d))
    return annotators


def load_existing() -> dict:
    """Return {sample_label: row_dict} from human-coded CSV."""
    with open(ROOT / "data" / "self_executing_sample75_coded.csv", newline="", encoding="utf-8") as f:
        return {r["sample_label"]: r for r in csv.DictReader(f)}


def slug_to_title(url: str) -> str:
    slug = url.rstrip("/").split("/")[-1]
    slug = re.sub(r"-\d{4,}$", "", slug)  # strip trailing numeric ID
    return slug.replace("-", " ").title()


# ---------------------------------------------------------------------------
# Build recode CSV
# ---------------------------------------------------------------------------

IN_SCOPE_PREFIXES = ("EO", "M", "P")
RECODE_PATH = ROOT / "data" / "self_executing_sample75_claude_recode.csv"


def build_recode(existing: dict, annotators: list) -> list:
    rows = []
    label_order = sorted(
        existing.keys(),
        key=lambda k: (
            {"EO": 0, "M": 1, "P": 2}.get("".join(c for c in k if not c.isdigit()), 3),
            int("".join(c for c in k if c.isdigit())),
        ),
    )
    for label in label_order:
        ex = existing[label]
        se, mixed, rationale = CLAUDE_CODES[label]
        scope, tie = _compute_scope(label, annotators)
        row = {
            "sample_label": label,
            "document_id": ex["document_id"],
            "doc_type": ex["doc_type"],
            "date": ex["date"],
            "president": ex["president"],
            "url": ex["url"],
            "vesting_category": ex["vesting_category"],
            "generic_matches": ex["generic_matches"],
            "specific_matches": ex["specific_matches"],
            "vesting_clauses": ex["vesting_clauses"],
            "self_executing": se,
            "mixed_flag": mixed,
            "rationale": rationale,
            "full_text": ex["full_text"],
            # extra columns for clustering
            "scope": scope,
            "scope_tie": tie,
            "existing_se": ex["self_executing"],
            "existing_mixed": ex.get("mixed_flag", ""),
            "existing_rationale": ex.get("rationale", ""),
            "title": slug_to_title(ex["url"]),
        }
        rows.append(row)

    # Write only the 14 base columns so the existing summarizer can consume the file.
    base_fields = ["sample_label","document_id","doc_type","date","president","url",
                   "vesting_category","generic_matches","specific_matches","vesting_clauses",
                   "self_executing","mixed_flag","rationale","full_text"]
    with open(RECODE_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=base_fields)
        writer.writeheader()
        writer.writerows({k: r[k] for k in base_fields} for r in rows)
    print(f"Wrote recode CSV to {RECODE_PATH}")
    return rows


# ---------------------------------------------------------------------------
# Cross-tabs
# ---------------------------------------------------------------------------

SE_VALS = ["self_executing", "not_self_executing"]
VC_VALS = ["generic", "specific", "no_vesting_clause"]
DT_VALS = ["executive_order", "memorandum", "proclamation"]


def crosstab(rows, row_key, col_key) -> dict:
    ct: dict[tuple, int] = Counter()
    for r in rows:
        ct[(r[row_key], r[col_key])] += 1
    return ct


def fmt_table(row_labels, col_labels, cells, col_label_map=None) -> str:
    cmap = col_label_map or {}
    hdrs = [cmap.get(c, c) for c in col_labels]
    col_w = max(max(len(h) for h in hdrs), len("total"), 5)
    row_w = max(max(len(r) for r in row_labels), len("total"))
    header = " " * (row_w + 2) + "  ".join(h.rjust(col_w) for h in hdrs) + "  " + "total".rjust(col_w)
    sep = "-" * len(header)
    lines = [header, sep]
    for rl in row_labels:
        vals = [cells.get((rl, cl), 0) for cl in col_labels]
        line = rl.ljust(row_w) + "  " + "  ".join(str(v).rjust(col_w) for v in vals)
        line += "  " + str(sum(vals)).rjust(col_w)
        lines.append(line)
    col_tots = [sum(cells.get((rl, cl), 0) for rl in row_labels) for cl in col_labels]
    tot_line = "total".ljust(row_w) + "  " + "  ".join(str(v).rjust(col_w) for v in col_tots)
    tot_line += "  " + str(sum(col_tots)).rjust(col_w)
    lines += [sep, tot_line]
    return "\n".join(lines)


def compute_agreement(rows) -> dict:
    agree = sum(1 for r in rows if r["self_executing"] == r["existing_se"])
    disagree = [r for r in rows if r["self_executing"] != r["existing_se"]]
    n = len(rows)
    # Cohen's kappa (2-category: SE vs not-SE; exclude undecided)
    coded = [(r["self_executing"], r["existing_se"]) for r in rows
             if r["self_executing"] in SE_VALS and r["existing_se"] in SE_VALS]
    n2 = len(coded)
    po = sum(1 for a, b in coded if a == b) / n2 if n2 else 0
    p_se = (sum(1 for a, _ in coded if a == "self_executing") / n2 *
            sum(1 for _, b in coded if b == "self_executing") / n2) if n2 else 0
    p_nse = (sum(1 for a, _ in coded if a == "not_self_executing") / n2 *
             sum(1 for _, b in coded if b == "not_self_executing") / n2) if n2 else 0
    pe = p_se + p_nse
    kappa = (po - pe) / (1 - pe) if pe < 1 else 1.0
    return {"agree": agree, "disagree": disagree, "n": n, "pct": agree / n, "kappa": kappa}


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

HTML_PATH = ROOT / "data" / "self_executing_review.html"

BADGE_COLORS = {
    "self_executing":     ("#1a7f37", "white"),
    "not_self_executing": ("#c93f3f", "white"),
    "undecided":          ("#7a6500", "white"),
    "generic":            ("#0550ae", "white"),
    "specific":           ("#8250df", "white"),
    "no_vesting_clause":  ("#666666", "white"),
    "domestic":           ("#2da44e", "white"),
    "foreign":            ("#bf3989", "white"),
    "tie":                ("#7a6500", "white"),
    "executive_order":    ("#0550ae", "white"),
    "memorandum":         ("#bf3989", "white"),
    "proclamation":       ("#2da44e", "white"),
    "mixed":              ("#e16812", "white"),
    "disagree":           ("#c93f3f", "white"),
}

DOC_TYPE_ABBR = {"executive_order": "EO", "memorandum": "Memo", "proclamation": "Proc."}


def badge(text: str, key: str = "", extra_style: str = "") -> str:
    bg, fg = BADGE_COLORS.get(key or text, ("#888", "white"))
    label = text.replace("_", " ")
    return (f'<span class="badge" style="background:{bg};color:{fg};{extra_style}">'
            f'{escape(label)}</span>')


def build_html(rows: list, agree_stats: dict) -> str:
    # ---- Summary tables ----
    headline = crosstab(rows, "self_executing", "vesting_category")
    per_type = {dt: crosstab([r for r in rows if r["doc_type"] == dt],
                              "self_executing", "vesting_category")
                for dt in DT_VALS}

    # scope clustering
    scope_table = crosstab(rows, "vesting_category", "scope")
    generic_rows = [r for r in rows if r["vesting_category"] == "generic"]
    generic_se_table = crosstab(generic_rows, "self_executing", "scope")

    # OLC counterexamples: self_executing + generic
    counterexamples = [r for r in rows
                       if r["self_executing"] == "self_executing"
                       and r["vesting_category"] == "generic"]

    disagree_labels = {r["sample_label"] for r in agree_stats["disagree"]}

    # ---- Card data ----
    cards_html = []
    for r in rows:
        label = r["sample_label"]
        se = r["self_executing"]
        ex_se = r["existing_se"]
        vc = r["vesting_category"]
        scope = r["scope"]
        is_mixed = r["mixed_flag"].lower() in ("true", "1", "yes")
        is_disagree = label in disagree_labels
        is_tie = r.get("scope_tie") == "tie"

        # Extract vesting clause text for display
        try:
            clauses = json.loads(r["vesting_clauses"])
        except Exception:
            clauses = []
        clause_text = " | ".join(clauses) if clauses else ""

        try:
            gen_matches = json.loads(r["generic_matches"])
        except Exception:
            gen_matches = []
        try:
            spec_matches = json.loads(r["specific_matches"])
        except Exception:
            spec_matches = []

        def highlight_clause(text: str) -> str:
            """Highlight matched terms in vesting clause."""
            if not text:
                return "<em>(none extracted)</em>"
            highlighted = escape(text)
            for m in gen_matches:
                term = escape(m.get("text", ""))
                if term:
                    highlighted = highlighted.replace(term, f'<mark class="gen-mark">{term}</mark>', 1)
            for m in spec_matches:
                term = escape(m.get("text", ""))
                if term:
                    highlighted = highlighted.replace(term, f'<mark class="spec-mark">{term}</mark>', 1)
            return highlighted

        # Tags for filter system (space-separated; JS reads data-tags)
        tags = [se, vc, r["doc_type"], scope]
        if is_mixed:
            tags.append("mixed")
        if is_disagree:
            tags.append("disagree")

        # Title from URL slug
        title = r.get("title", "")

        card = f"""
<div class="card" data-tags="{' '.join(tags)}" data-label="{label}">
  <div class="card-header">
    <div class="card-title-row">
      <span class="card-label">{escape(label)}</span>
      {badge(r["doc_type"], r["doc_type"])}
      {badge(vc, vc)}
      {badge(se, se)}
      {badge("mixed", "mixed") if is_mixed else ""}
      {badge("disagree", "disagree") if is_disagree else ""}
      <span style="flex:1"></span>
      <span class="card-meta">{escape(r['president'])} · {escape(r['date'][:4])}</span>
    </div>
    <div class="card-title">
      <a href="{escape(r['url'])}" target="_blank">{escape(title)}</a>
    </div>
  </div>

  <div class="card-body">
    <!-- Vesting clause -->
    <div class="section-label">Vesting clause <span class="vc-badge">{escape(vc)}</span></div>
    <div class="vesting-text">{highlight_clause(clause_text)}</div>
    {'<div class="match-legend"><span class="gen-mark">generic</span> <span class="spec-mark">specific</span></div>' if gen_matches or spec_matches else ""}

    <!-- My coding -->
    <div class="coding-row">
      <div class="coding-block my-coding">
        <div class="coding-header">Claude coding</div>
        {badge(se, se)}
        {badge("mixed", "mixed") if is_mixed else ""}
        <div class="rationale">{escape(r['rationale'])}</div>
      </div>
      <div class="coding-block existing-coding">
        <div class="coding-header">Existing coding {"⚠ DISAGREES" if is_disagree else ""}</div>
        {badge(ex_se, ex_se)}
        {badge("mixed", "mixed") if r.get("existing_mixed", "").lower() in ("true","1","yes") else ""}
        <div class="rationale">{escape(r.get("existing_rationale",""))}</div>
      </div>
    </div>

    <!-- Scope -->
    <div class="scope-row">
      <span class="section-label">Scope</span>
      {badge(scope, scope)}
      {badge("tie (KyleM break)", "tie") if is_tie else ""}
    </div>

    <!-- Override controls -->
    <div class="override-row">
      <label class="override-label">Your review:
        <select class="override-select" data-label="{label}">
          <option value="">-- confirm or override --</option>
          <option value="agree_claude">Agree with Claude ({escape(se)})</option>
          <option value="agree_existing">Agree with existing ({escape(ex_se)})</option>
          <option value="self_executing">Override → self_executing</option>
          <option value="not_self_executing">Override → not_self_executing</option>
          <option value="undecided">Mark undecided</option>
        </select>
      </label>
      <input class="override-notes" placeholder="Notes..." data-label="{label}" type="text">
    </div>

    <!-- Full text (collapsible) -->
    <details class="fulltext-details">
      <summary>Full text</summary>
      <pre class="fulltext">{escape(r['full_text'][:8000])}{"..." if len(r['full_text']) > 8000 else ""}</pre>
    </details>
  </div>
</div>
"""
        cards_html.append(card)

    # ---- Summary HTML ----
    agree_pct = f"{agree_stats['pct']:.1%}"
    kappa = f"{agree_stats['kappa']:.3f}"
    disagree_list = "<br>".join(
        f"{r['sample_label']}: Claude={r['self_executing']} | Existing={r['existing_se']}"
        for r in agree_stats["disagree"]
    )

    # Count generic+SE (OLC counterexamples)
    n_counter = len(counterexamples)
    counter_list = ", ".join(f"{r['sample_label']} ({r['president'][:10]}, {r['date'][:4]})"
                              for r in counterexamples)

    # Scope breakdown for generic docs
    g_dom = sum(1 for r in generic_rows if r["scope"] == "domestic")
    g_for = sum(1 for r in generic_rows if r["scope"] == "foreign")

    summary_html = f"""
<div class="summary-section">
  <h2>Summary</h2>
  <div class="summary-grid">

    <div class="summary-box">
      <h3>Headline cross-tab (n=75, Claude coding)</h3>
      <pre>{fmt_table(SE_VALS, VC_VALS, headline)}</pre>
      <p class="note">Generic+specific columns exclude the no_vesting_clause bucket (n=20).</p>
    </div>

    <div class="summary-box">
      <h3>Executive Orders (n=25)</h3>
      <pre>{fmt_table(SE_VALS, VC_VALS, per_type["executive_order"])}</pre>
    </div>

    <div class="summary-box">
      <h3>Memoranda (n=25)</h3>
      <pre>{fmt_table(SE_VALS, VC_VALS, per_type["memorandum"])}</pre>
    </div>

    <div class="summary-box">
      <h3>Proclamations (n=25)</h3>
      <pre>{fmt_table(SE_VALS, VC_VALS, per_type["proclamation"])}</pre>
    </div>

    <div class="summary-box">
      <h3>Agreement with existing coding</h3>
      <p>Agreement: <strong>{agree_stats['agree']}/{agree_stats['n']} ({agree_pct})</strong> &nbsp;|&nbsp; Cohen's κ = <strong>{kappa}</strong></p>
      <p>Disagreements ({len(agree_stats['disagree'])}):</p>
      <pre style="font-size:12px">{disagree_list}</pre>
    </div>

    <div class="summary-box">
      <h3>OLC convention test: self-executing + generic authority</h3>
      <p>Self-executing with generic-only vesting: <strong>{n_counter} / 75</strong></p>
      <p>These directly contradict a simple "specific cite required when self-executing" rule:</p>
      <p style="font-size:12px">{escape(counter_list)}</p>
      <p class="note">Not-self-executing with generic authority: <strong>{sum(1 for r in rows if r["self_executing"]=="not_self_executing" and r["vesting_category"]=="generic")}</strong></p>
    </div>

    <div class="summary-box">
      <h3>Boilerplate clustering — does generic authority cluster in foreign directives?</h3>
      <pre>{fmt_table(VC_VALS, ["domestic","foreign"], scope_table)}</pre>
      <p>Among the {len(generic_rows)} generic-authority docs: {g_dom} domestic, {g_for} foreign.</p>
      <p>Self-exec × scope for generic docs (n={len(generic_rows)}):</p>
      <pre>{fmt_table(SE_VALS, ["domestic","foreign"], generic_se_table)}</pre>
      <p class="note">6 tie cases broken by KyleM tiebreak: {escape(', '.join(SCOPE_TIE_BREAK.keys()))}</p>
    </div>

  </div>
</div>
"""

    # ---- Export JS ----
    export_js = """
function exportCSV() {
  const selects = document.querySelectorAll('.override-select');
  const notes_els = document.querySelectorAll('.override-notes');
  const rows = [['sample_label','claude_se','existing_se','review_decision','notes']];
  selects.forEach(sel => {
    const label = sel.dataset.label;
    const note_el = document.querySelector('.override-notes[data-label="' + label + '"]');
    const card = document.querySelector('.card[data-label="' + label + '"]');
    const tags = (card ? card.dataset.tags : '').split(' ');
    const claude_se = tags.find(t => t === 'self_executing' || t === 'not_self_executing') || '';
    // existing from select option text
    const existing = sel.options[2] ? sel.options[2].text.replace('Agree with existing (','').replace(')','') : '';
    rows.push([label, claude_se, existing, sel.value, note_el ? note_el.value : '']);
  });
  const csv = rows.map(r => r.map(v => '"' + String(v).replace(/"/g, '""') + '"').join(',')).join('\\n');
  const a = document.createElement('a');
  a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv);
  a.download = 'self_executing_adjudications.csv';
  a.click();
}
"""

    # ---- Filter JS ----
    filter_js = """
function setFilter(tag) {
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.toggle('active', b.dataset.tag === tag));
  document.querySelectorAll('.card').forEach(card => {
    const tags = card.dataset.tags.split(' ');
    card.style.display = (tag === 'all' || tags.includes(tag)) ? '' : 'none';
  });
  document.getElementById('filter-label').textContent = tag === 'all' ? 'Showing all 75 documents' : 'Filter: ' + tag.replace(/_/g,' ');
}
"""

    filter_buttons = [
        ("all", "All (75)", ""),
        ("disagree", "⚠ Disagrees", "disagree"),
        ("mixed", "Mixed", "mixed"),
        ("self_executing", "Self-executing", "self_executing"),
        ("not_self_executing", "Not self-executing", "not_self_executing"),
        ("generic", "Generic vesting", "generic"),
        ("specific", "Specific vesting", "specific"),
        ("no_vesting_clause", "No vesting", "no_vesting_clause"),
        ("executive_order", "EO", "executive_order"),
        ("memorandum", "Memo", "memorandum"),
        ("proclamation", "Proclamation", "proclamation"),
        ("foreign", "Foreign", "foreign"),
        ("domestic", "Domestic", "domestic"),
    ]

    filter_btns_html = " ".join(
        f'<button class="filter-btn{" active" if tag == "all" else ""}" data-tag="{tag}" onclick="setFilter(\'{tag}\')">{escape(label)}</button>'
        for tag, label, _ in filter_buttons
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Self-Executing × Vesting Authority — Review</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; font-size: 14px; color: #222; background: #f6f8fa; }}
h1 {{ padding: 20px 24px 8px; font-size: 22px; }}
h2 {{ font-size: 16px; margin-bottom: 12px; }}
h3 {{ font-size: 13px; margin-bottom: 8px; color: #555; text-transform: uppercase; letter-spacing: .03em; }}
.summary-section {{ background: white; border-bottom: 1px solid #d0d7de; padding: 20px 24px; }}
.summary-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(340px,1fr)); gap: 16px; }}
.summary-box {{ background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 6px; padding: 14px; }}
.summary-box pre {{ font-size: 11px; font-family: "SF Mono", "Consolas", monospace; overflow-x: auto; background: white; border: 1px solid #d0d7de; padding: 8px; border-radius: 4px; margin: 8px 0; }}
.note {{ font-size: 11px; color: #666; margin-top: 6px; }}
.filter-bar {{ background: white; border-bottom: 1px solid #d0d7de; padding: 10px 24px; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; position: sticky; top: 0; z-index: 10; }}
.filter-btn {{ border: 1px solid #d0d7de; background: white; padding: 4px 10px; border-radius: 20px; cursor: pointer; font-size: 12px; }}
.filter-btn.active {{ background: #0550ae; color: white; border-color: #0550ae; }}
.export-btn {{ margin-left: auto; background: #1a7f37; color: white; border: none; padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 12px; }}
#filter-label {{ font-size: 12px; color: #666; margin-left: 8px; }}
.cards-container {{ padding: 16px 24px; display: grid; gap: 14px; }}
.card {{ background: white; border: 1px solid #d0d7de; border-radius: 8px; overflow: hidden; }}
.card-header {{ padding: 12px 14px 8px; background: #f6f8fa; border-bottom: 1px solid #d0d7de; }}
.card-title-row {{ display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 4px; }}
.card-label {{ font-weight: 700; font-size: 15px; }}
.card-meta {{ font-size: 12px; color: #666; }}
.card-title {{ font-size: 13px; color: #0550ae; }}
.card-title a {{ color: inherit; text-decoration: none; }}
.card-title a:hover {{ text-decoration: underline; }}
.card-body {{ padding: 12px 14px; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; margin: 1px; }}
.section-label {{ font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: #666; margin-top: 10px; margin-bottom: 4px; }}
.vc-badge {{ display: inline; background: #f0f0f0; border: 1px solid #ccc; padding: 1px 6px; border-radius: 4px; font-size: 11px; margin-left: 4px; }}
.vesting-text {{ font-size: 12px; background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 4px; padding: 8px; margin-bottom: 4px; line-height: 1.5; }}
mark.gen-mark {{ background: #cae8ff; color: #0550ae; border-radius: 2px; padding: 0 1px; }}
mark.spec-mark {{ background: #e8d5ff; color: #8250df; border-radius: 2px; padding: 0 1px; }}
.match-legend {{ font-size: 11px; color: #666; margin-bottom: 8px; }}
.match-legend mark {{ padding: 1px 4px; border-radius: 2px; }}
.coding-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; }}
.coding-block {{ background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 6px; padding: 8px; }}
.coding-block.existing-coding {{ border-left-color: #666; }}
.coding-header {{ font-size: 11px; font-weight: 700; text-transform: uppercase; color: #666; margin-bottom: 4px; }}
.rationale {{ font-size: 12px; color: #444; margin-top: 6px; line-height: 1.5; font-style: italic; }}
.scope-row {{ margin-top: 10px; display: flex; align-items: center; gap: 6px; }}
.override-row {{ margin-top: 10px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
.override-label {{ font-size: 12px; color: #555; }}
.override-select {{ font-size: 12px; padding: 3px 6px; border: 1px solid #d0d7de; border-radius: 4px; }}
.override-notes {{ font-size: 12px; padding: 3px 8px; border: 1px solid #d0d7de; border-radius: 4px; flex: 1; min-width: 160px; }}
.fulltext-details {{ margin-top: 10px; }}
.fulltext-details summary {{ font-size: 12px; color: #0550ae; cursor: pointer; padding: 4px 0; }}
.fulltext {{ font-size: 11px; font-family: "SF Mono", "Consolas", monospace; background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 4px; padding: 10px; max-height: 400px; overflow-y: auto; white-space: pre-wrap; word-wrap: break-word; margin-top: 6px; line-height: 1.5; }}
/* Disagreement highlight */
.card[data-tags*="disagree"] {{ border-left: 4px solid #c93f3f; }}
/* Mixed highlight */
.card[data-tags*="mixed"]:not([data-tags*="disagree"]) {{ border-left: 4px solid #e16812; }}
</style>
</head>
<body>
<h1>Self-Executing × Vesting Authority — Review (sample-100, n=75)</h1>
{summary_html}
<div class="filter-bar">
  {filter_btns_html}
  <button class="export-btn" onclick="exportCSV()">⬇ Export adjudications CSV</button>
  <span id="filter-label">Showing all 75 documents</span>
</div>
<div class="cards-container">
{"".join(cards_html)}
</div>
<script>
{filter_js}
{export_js}
</script>
</body>
</html>
"""
    return html


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Loading data…")
    existing = load_existing()
    annotators = load_annotators()

    print("Building recode CSV…")
    rows = build_recode(existing, annotators)

    # Reload with extra columns (scope etc.) that build_recode attaches to rows
    agree_stats = compute_agreement(rows)
    print(f"\nAgreement: {agree_stats['agree']}/{agree_stats['n']} ({agree_stats['pct']:.1%})  κ={agree_stats['kappa']:.3f}")
    if agree_stats["disagree"]:
        print("Disagreements:")
        for r in agree_stats["disagree"]:
            print(f"  {r['sample_label']}: Claude={r['self_executing']} | Existing={r['existing_se']}")

    # Cross-tabs (using my codes)
    headline = crosstab(rows, "self_executing", "vesting_category")
    print("\nHeadline cross-tab (Claude coding):")
    print(fmt_table(SE_VALS, VC_VALS, headline))

    print("\nBuilding HTML…")
    html = build_html(rows, agree_stats)
    HTML_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote review HTML to {HTML_PATH}")
    print(f"Open in browser: open {HTML_PATH}")


if __name__ == "__main__":
    main()
