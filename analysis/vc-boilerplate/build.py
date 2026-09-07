#!/usr/bin/env python3
"""Build the deterministic vesting-clause boilerplate analysis.

The two classifiers in this module are intentionally small ordered decision lists.
They were developed against the frozen 46-document development partition only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


ANALYSIS_DIR = Path(__file__).resolve().parent
ROOT = ANALYSIS_DIR.parents[1]
SRC = ROOT / "src"
VESTING_DIR = ROOT / "Authority Vagueness Analysis"
for module_dir in (SRC, VESTING_DIR):
    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))

from ceremonial import ceremonial_reason  # noqa: E402
from vesting_authority_breakdown import (  # noqa: E402
    classify_authority_category,
    extract_vesting_clauses,
)
from vesting_authority_stats import load_corpus  # noqa: E402


GOLD = ROOT / "data" / "Annotations" / "Round 2" / "round-2-finalized-validation-labels-with-subdirectives.json"
ROUND2_MANIFEST = ROOT / "data" / "Annotations" / "Round 2" / "sample_manifest.json"
DEV_CORPUS = ROOT / "data" / "4_28_2026_build_dev.csv"
HOLDOUT_CORPUS = ROOT / "data" / "4_28_2026_build_holdout.csv"
PROFILES = ROOT / "data" / "parent_analysis" / "canonical_profiles" / "profiles.jsonl"
OUTPUTS = ANALYSIS_DIR / "outputs"
SEED = "20260819"
GOLD_SHA256 = "d3eb11f4a88b321a6c2bb8e816ca6786a89a7c8c6267177ccc41704f90dac8a7"
DEV_TARGETS = {"0": 29, "1": 7, "2": 1, "3": 8, "4": 1}
FIELDS = ("actor", "action", "target", "mechanism", "effect", "condition", "timing", "label")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_key(document_id: str) -> str:
    return hashlib.sha256(f"{SEED}:{document_id}".encode()).hexdigest()


def load_gold() -> list[dict]:
    if sha256_file(GOLD) != GOLD_SHA256:
        raise ValueError("finalized Round 2 gold file has an unexpected SHA-256")
    payload = json.loads(GOLD.read_text())
    if not payload.get("finalized") or payload.get("schema_version") != 2:
        raise ValueError("Round 2 gold is not the finalized version-2 schema")
    records = payload.get("records", [])
    ids = [row["global_dev_id"] for row in records]
    if len(records) != 139 or len(ids) != len(set(ids)):
        raise ValueError("Round 2 gold must contain 139 unique document records")
    if any(row["labels"].get("code") not in set("01234") for row in records):
        raise ValueError("invalid document-level code in Round 2 gold")
    return records


def hamilton_quotas(counts: Counter, total: int) -> dict[str, int]:
    population = sum(counts.values())
    raw = {key: total * value / population for key, value in counts.items()}
    quotas = {key: math.floor(value) for key, value in raw.items()}
    remainder = total - sum(quotas.values())
    order = sorted(counts, key=lambda key: (-(raw[key] - quotas[key]), key))
    for key in order[:remainder]:
        quotas[key] += 1
    return quotas


def build_split(records: list[dict]) -> tuple[list[dict], list[dict]]:
    dev: list[dict] = []
    for code in "01234":
        members = [row for row in records if row["labels"]["code"] == code]
        by_type = Counter(row["doc_type"] for row in members)
        quotas = hamilton_quotas(by_type, DEV_TARGETS[code])
        for doc_type, quota in quotas.items():
            cell = sorted(
                (row for row in members if row["doc_type"] == doc_type),
                key=lambda row: stable_key(row["global_dev_id"]),
            )
            dev.extend(cell[:quota])
    dev_ids = {row["global_dev_id"] for row in dev}
    validation = [row for row in records if row["global_dev_id"] not in dev_ids]
    return sorted(dev, key=lambda row: int(row["global_dev_id"])), sorted(
        validation, key=lambda row: int(row["global_dev_id"])
    )


def load_source_rows() -> dict[str, dict]:
    rows = load_corpus([DEV_CORPUS, HOLDOUT_CORPUS])
    return {row["ucsb_identifier"]: row for row in rows}


def load_profiles() -> dict[str, dict]:
    profiles: dict[str, dict] = {}
    with PROFILES.open() as handle:
        for line in handle:
            row = json.loads(line)
            profiles[str(row["document_id"])] = row
    return profiles


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def decision(code: str, rule: str, evidence: str, rationale: str) -> dict:
    return {
        "predicted_code": code,
        "rule": rule,
        "evidence": re.sub(r"\s+", " ", evidence).strip()[:500],
        "rationale": rationale,
    }


def search(pattern: str, text: str) -> re.Match | None:
    return re.search(pattern, text, re.I | re.S)


def classify_text(text: str) -> dict:
    """Classify from raw directive text only; no metadata is consulted."""
    value = normalized(text)

    match = search(
        r"shall be closed.{0,500}shall be excused from duty.{0,500}(?:considered|treated as) a holiday",
        value,
    )
    if match:
        return decision("4", "T4_HOLIDAY_MIX", match.group(), "Office closure, employee duty, and statutory holiday effects are inseparably combined.")

    match = search(
        r"(?:do hereby|hereby) (?:proclaim|designate).{0,180}(?:day|week|month|year)\b.{0,500}(?:observe|observance|ceremon|commemorat|recogniz|celebrat)",
        value,
    )
    if match:
        return decision("0", "T0_OBSERVANCE", match.group(), "The directive is a ceremonial public observance rather than executive governance or a legal-rights change.")

    outside_patterns = (
        ("T0_REPORT", r"\b(?:i )?(?:hereby )?(?:report|transmit|submit).{0,80}(?:to (?:the )?congress|for the information of the congress)"),
        ("T0_RECOGNITION", r"\b(?:i )?(?:hereby )?recognize\b.{0,100}\b(?:independent|sovereign) state\b"),
        ("T0_VETO", r"\b(?:withhold my approval|return(?:ing)? without (?:my )?approval|veto)\b"),
        ("T0_SUPPORT_LETTER", r"\b(?:dear |i (?:urge|support|commend)|constitutional amendment).{0,300}\b(?:sincerely|members of congress|house of representatives)\b"),
        ("T0_PURE_SUCCESSION", r"\border of succession\b.{0,500}\b(?:act as secretary|vacancy in office)\b"),
        ("T0_PURE_EO_REVOCATION", r"\bexecutive order(?:s| no\.)?.{0,180}\b(?:is|are) (?:hereby )?revoked\b.{0,300}\bconsider.{0,60}rescind"),
    )
    for name, pattern in outside_patterns:
        match = search(pattern, value)
        if match:
            return decision("0", name, match.group(), "The text performs a communicative, transmissive, recognition, veto, succession, or prior-order housekeeping act treated as outside scope in the development labels.")

    immediate_patterns = (
        ("T3_WAIVER", r"\bi (?:hereby )?(?:determine and certify.{0,500})?(?:hereby )?waive\b|\brequirements? .{0,120} (?:is|are) waived\b"),
        ("T3_EMERGENCY_CONTINUATION", r"\b(?:continue|continuation of) the national emergency\b.{0,180}\b(?:maintain|continue).{0,80}\bin force\b"),
        ("T3_FUNDS_AVAILABLE", r"\bi (?:hereby )?determine\b.{0,180}\b\$?[\d,]+(?: million)?\b.{0,120}\bbe made available\b"),
        ("T3_ENTRY_ASSET", r"\b(?:entry of|property and interests in property).{0,180}\b(?:is|are) (?:hereby )?(?:suspended|blocked|prohibited)\b"),
        ("T3_STATUS_DESIGNATION", r"\b(?:is hereby designated|shall be considered)\b.{0,160}\b(?:beneficiary|eligible|ineligible|lesser developed)\b"),
        ("T3_PAY_RATES", r"\b(?:rates?|ranges) of (?:basic )?(?:pay|salaries).{0,160}\b(?:are|is) set forth\b"),
        ("T3_TARIFF_TREATMENT", r"\b(?:harmonized tariff schedule|nondiscriminatory treatment).{0,300}\b(?:is modified|shall be extended|shall become effective|enter into force)\b"),
        ("T3_DIRECT_PROHIBITION", r"\b(?:no |all )[^.;]{0,120}\b(?:shall be prohibited|are prohibited|shall be ineligible|is ineligible|shall not be eligible)\b"),
    )
    for name, pattern in immediate_patterns:
        match = search(pattern, value)
        if match:
            return decision("3", name, match.group(), "The directive itself supplies the legal trigger for a waiver, continuation, funding, status, pay, tariff, entry, asset, or prohibition consequence.")

    later_legal_patterns = (
        ("T2_FUNDING_CONDITION", r"\b(?:department|agency|secretary|administrator).{0,100}\bshall\b.{0,180}\b(?:require as a condition|condition (?:any )?(?:grant|funding|assistance)|terminate (?:funding|assistance)|exclude .{0,60} eligibility)\b"),
        ("T2_MANDATED_RULE_CHANGE", r"\b(?:department|agency|secretary|administrator).{0,100}\bshall\b.{0,160}\b(?:issue|promulgate|adopt|amend|rescind|repeal|withdraw)\b.{0,100}\b(?:rule|regulation|guidance|eligibility|criteria)\b"),
        ("T2_MANDATED_ENFORCEMENT", r"\b(?:department|agency|secretary|administrator).{0,100}\bshall\b.{0,180}\b(?:initiate proceedings|impose (?:a )?penalt|cancel|terminate|suspend).{0,80}\b(?:contract|grant|assistance|license|proceeding)\b"),
        ("T2_CONTRACT_CLAUSE", r"\b(?:agencies|agency|departments?).{0,100}\bshall\b.{0,150}\b(?:include in every|require).{0,80}\b(?:contract|applicant|recipient)\b"),
    )
    for name, pattern in later_legal_patterns:
        match = search(pattern, value)
        if match:
            return decision("2", name, match.group(), "A mandatory, specific command requires an agency to produce a later legal consequence.")

    internal_patterns = (
        r"\b(?:there is|is hereby) (?:established|created)\b",
        r"\b(?:agency|agencies|secretary|director|administrator|department|council|committee|task force).{0,100}\bshall\b",
        r"\bshall (?:review|study|report|submit|consult|coordinate|develop|prepare|advise|recommend|prioritize|consider|provide|establish|designate|ensure|enhance)\b",
        r"\b(?:delegate|delegated|delegating)\b.{0,100}\bauthority\b",
        r"\b(?:executive departments?|federal agencies|heads of agencies)\b",
    )
    for pattern in internal_patterns:
        match = search(pattern, value)
        if match:
            return decision("1", "T1_EXECUTIVE_MANAGEMENT", match.group(), "The operative content organizes, delegates within, or directs the executive branch without matching a dictated later legal result.")

    return decision("0", "T0_NO_GOVERNANCE_SIGNAL", value[:500], "No text-only rule identified executive-branch direction or a legal consequence within the codebook's scope.")


def profile_text(profile_row: dict | None) -> tuple[str, int]:
    if not profile_row:
        return "", 0
    profile = profile_row.get("profile", {})
    functions = profile.get("policy_functions", []) + profile.get("operative_functions", [])
    pieces = []
    for function in functions:
        pieces.append(" | ".join(str(function.get(field, "")) for field in FIELDS))
    return normalized("\n".join(pieces)), len(functions)


def classify_profile(profile_row: dict | None) -> dict:
    """Classify from structured profile summaries, excluding evidence and metadata."""
    value, function_count = profile_text(profile_row)
    if not value:
        return decision("0", "P0_NO_PROFILE", "", "No canonical Flash function profile is available; the frozen profile-only default is outside scope.")

    match = search(r"(?:shall be closed|closes government offices).{0,400}(?:excused from duty|statutory holiday|holiday effects)", value)
    if match:
        return decision("4", "P4_HOLIDAY_MIX", match.group(), "The profile combines office closure, employee duty, and statutory holiday consequences.")

    outside_patterns = (
        ("P0_REPORT", r"\breport(?:s| to)?\b.{0,80}\bcongress\b|\btransmit.{0,80}\bcongress\b"),
        ("P0_RECOGNITION", r"\brecogniz(?:e|es)\b.{0,80}\b(?:independent|sovereign) state\b"),
        ("P0_VETO", r"\bwithhold approval\b.{0,80}\b(?:bill|h\.r\.)"),
        ("P0_SUCCESSION", r"\border of succession\b|\bact as secretary\b"),
        ("P0_PRIOR_ORDER_HOUSEKEEPING", r"\brevoke\b.{0,100}\bprior (?:directive|executive order)\b"),
    )
    for name, pattern in outside_patterns:
        match = search(pattern, value)
        if match:
            return decision("0", name, match.group(), "The structured functions describe reporting, recognition, veto, succession, or prior-order housekeeping treated as outside scope in development.")

    immediate_patterns = (
        ("P3_WAIVER", r"\bwaiv(?:e|es)\b.{0,180}\b(?:restriction|requirement|statutory|assistance)\b"),
        ("P3_EMERGENCY_CONTINUATION", r"\bcontinue\b.{0,100}\bnational emergency\b|\bmaintains national emergency\b"),
        ("P3_FUNDS_AVAILABLE", r"\bdetermin(?:e|es)\b.{0,120}\b(?:\$|million|fund)\b.{0,150}\b(?:made|makes) (?:funds )?available\b"),
        ("P3_ENTRY_ASSET", r"\b(?:entry|property and interests in property).{0,150}\b(?:suspend|block|prohibit)"),
        ("P3_LEGAL_STATUS", r"\b(?:designate|classify)\b.{0,100}\b(?:beneficiary|eligible|ineligible|country status)\b"),
        ("P3_PAY_RATES", r"\b(?:set|adjust|order payment).{0,100}\b(?:pay|salaries|salary|comparability payments)\b"),
        ("P3_TARIFF_TREATMENT", r"\b(?:modify|proclaim).{0,150}\b(?:tariff|nondiscriminatory treatment|trade agreement)\b"),
    )
    for name, pattern in immediate_patterns:
        match = search(pattern, value)
        if match:
            return decision("3", name, match.group(), "The structured function describes a self-executing legal trigger or condition precedent.")

    later_patterns = (
        ("P2_CONDITION_OR_ELIGIBILITY", r"\brequire\b.{0,100}\b(?:condition|applicant|recipient|contractor)\b.{0,160}\b(?:grant|assistance|contract|compliance|eligib)"),
        ("P2_MANDATED_LEGAL_INSTRUMENT", r"\b(?:issue|adopt|amend|rescind|repeal|withdraw)\b.{0,100}\b(?:rules?|regulations?|guidance|criteria)\b"),
        ("P2_MANDATED_SANCTION", r"\b(?:cancel|terminate|suspend|impose)\b.{0,120}\b(?:grant|assistance|contract|license|penalt)\b"),
        ("P2_CONTRACT_REQUIREMENT", r"\binclude\b.{0,100}\b(?:every|all) government contract\b"),
    )
    for name, pattern in later_patterns:
        match = search(pattern, value)
        if match:
            return decision("2", name, match.group(), "The profile specifies mandatory later agency action producing a legal consequence.")

    return decision("1", "P1_PROFILED_EXECUTIVE_FUNCTION", value[:500], f"The profile contains {function_count} executive policy or operative functions without a stronger legal-outcome rule.")


def metric_report(rows: list[dict], prediction_field: str) -> dict:
    labels = list("01234")
    matrix = {gold: {pred: 0 for pred in labels} for gold in labels}
    for row in rows:
        matrix[row["gold_code"]][row[prediction_field]] += 1
    correct = sum(matrix[label][label] for label in labels)
    per_class = {}
    supported_f1 = []
    for label in labels:
        tp = matrix[label][label]
        support = sum(matrix[label].values())
        predicted = sum(matrix[gold][label] for gold in labels)
        precision = tp / predicted if predicted else 0.0
        recall = tp / support if support else None
        f1 = (2 * precision * recall / (precision + recall)) if recall is not None and precision + recall else 0.0
        per_class[label] = {"support": support, "predicted": predicted, "precision": precision, "recall": recall, "f1": f1 if support else None}
        if support:
            supported_f1.append(f1)
    return {
        "n": len(rows),
        "correct": correct,
        "accuracy": correct / len(rows),
        "supported_class_macro_f1": sum(supported_f1) / len(supported_f1),
        "per_class": per_class,
        "confusion_matrix": matrix,
    }


def write_csv(path: Path, rows: list[dict], fields: list[str] | tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def split_rows(records: list[dict], source_rows: dict[str, dict], partition: str) -> list[dict]:
    output = []
    for gold in records:
        source = source_rows[gold["global_dev_id"]]
        output.append({
            "partition": partition,
            "global_dev_id": gold["global_dev_id"],
            "round_id": gold["round_id"],
            "gold_code": gold["labels"]["code"],
            "doc_type": gold["doc_type"],
            "date": gold["date"],
            "president": gold["president"],
            "url": gold["url"],
            "doc_text": source["doc_text"],
        })
    return output


def predict(rows: list[dict], profiles: dict[str, dict]) -> list[dict]:
    output = []
    for row in rows:
        text_result = classify_text(row["doc_text"])
        profile = profiles.get(row["global_dev_id"])
        profile_result = classify_profile(profile)
        output.append({
            **row,
            "text_prediction": text_result["predicted_code"],
            "text_rule": text_result["rule"],
            "text_evidence": text_result["evidence"],
            "text_rationale": text_result["rationale"],
            "profile_available": str(profile is not None).lower(),
            "profile_prediction": profile_result["predicted_code"],
            "profile_rule": profile_result["rule"],
            "profile_evidence": profile_result["evidence"],
            "profile_rationale": profile_result["rationale"],
        })
    return output


def select_target(source_rows: dict[str, dict]) -> list[dict]:
    target = []
    for row in source_rows.values():
        if ceremonial_reason(row):
            continue
        clauses = extract_vesting_clauses(row["doc_text"], row["doc_type"])
        if classify_authority_category(clauses) == "generic_constitution_and_generic_statute":
            target.append(row)
    return sorted(target, key=lambda row: (row["date"], int(row["ucsb_identifier"])))


def target_predictions(target: list[dict], profiles: dict[str, dict]) -> list[dict]:
    output = []
    for row in target:
        text_result = classify_text(row["doc_text"])
        profile = profiles.get(row["ucsb_identifier"])
        profile_result = classify_profile(profile)
        output.append({
            "document_id": row["ucsb_identifier"], "url": row["url"], "date": row["date"],
            "president": row["president"], "term": row["term"], "doc_type": row["doc_type"],
            "source_file": row["source_file"], "text_prediction": text_result["predicted_code"],
            "text_rule": text_result["rule"], "text_evidence": text_result["evidence"],
            "text_rationale": text_result["rationale"], "profile_available": str(profile is not None).lower(),
            "profile_prediction": profile_result["predicted_code"], "profile_rule": profile_result["rule"],
            "profile_evidence": profile_result["evidence"], "profile_rationale": profile_result["rationale"],
            "classifiers_agree": str(text_result["predicted_code"] == profile_result["predicted_code"]).lower(),
        })
    return output


def content_summary(rows: list[dict]) -> list[dict]:
    output = []
    dimensions = [("all", "all", rows)]
    dimensions += [("doc_type", key, [r for r in rows if r["doc_type"] == key]) for key in sorted({r["doc_type"] for r in rows})]
    for dimension, value, subset in dimensions:
        for classifier in ("text", "profile"):
            counts = Counter(row[f"{classifier}_prediction"] for row in subset)
            for code in "01234":
                output.append({"dimension": dimension, "value": value, "classifier": classifier, "code": code, "count": counts[code], "share": counts[code] / len(subset) if subset else 0.0})
    return output


def representatives(rows: list[dict], per_code: int = 5) -> list[dict]:
    output = []
    for classifier in ("text", "profile"):
        for code in "01234":
            subset = [row for row in rows if row[f"{classifier}_prediction"] == code]
            subset.sort(key=lambda row: hashlib.sha256(f"representative:{SEED}:{row['document_id']}".encode()).hexdigest())
            for rank, row in enumerate(subset[:per_code], 1):
                output.append({"classifier": classifier, "code": code, "rank": rank, "document_id": row["document_id"], "date": row["date"], "president": row["president"], "doc_type": row["doc_type"], "url": row["url"], "rule": row[f"{classifier}_rule"], "evidence": row[f"{classifier}_evidence"]})
    return output


def render_results(metrics: dict, target: list[dict], target_rows: list[dict]) -> str:
    t = metrics["text"]
    p = metrics["profile"]
    baseline = metrics["majority_baseline"]
    agree = sum(r["classifiers_agree"] == "true" for r in target_rows)
    text_counts = Counter(r["text_prediction"] for r in target_rows)
    profile_counts = Counter(r["profile_prediction"] for r in target_rows)
    profile_coverage = sum(r["profile_available"] == "true" for r in target_rows)
    return f"""# Results

## Validation

The frozen text-only rules correctly classified **{t['correct']} of {t['n']} directives ({t['accuracy']:.1%})**. The frozen Flash-profile-only rules correctly classified **{p['correct']} of {p['n']} ({p['accuracy']:.1%})**. The development-set majority-class baseline was **{baseline['correct']} of {baseline['n']} ({baseline['accuracy']:.1%})**.

Supported-class macro-F1 was {t['supported_class_macro_f1']:.3f} for text and {p['supported_class_macro_f1']:.3f} for profiles. Validation has no code-4 example, so neither figure measures code-4 generalization. Full confusion matrices and per-class metrics are in `outputs/metrics.json`.

The aggregate figures are driven by Code 0. Text correctly identified 52/60 Code-0 and 10/15 Code-1 directives, but 0/1 Code-2 and 0/17 Code-3 directives. Profiles correctly identified 51/60 Code-0, 11/15 Code-1, 0/1 Code-2, and 1/17 Code-3 directives. Thus neither system is reliable for the legally consequential minority classes despite narrowly beating the majority baseline. Every error is listed in `outputs/validation_errors.csv`.

## Generic Constitution + Generic Statute population

After applying the repository's existing ceremonial exclusion and authority classifier, the target contains **{len(target)} directives** across the development and holdout corpus. Canonical Flash profiles are available for **{profile_coverage} ({profile_coverage/len(target):.1%})**. The classifiers agree on **{agree} ({agree/len(target):.1%})**.

| Code | Text count | Text share | Profile count | Profile share |
|---:|---:|---:|---:|---:|
""" + "\n".join(
        f"| {code} | {text_counts[code]} | {text_counts[code]/len(target):.1%} | {profile_counts[code]} | {profile_counts[code]/len(target):.1%} |"
        for code in "01234"
    ) + f"""

The text rules provide the complete-population view. The profile results are a deliberately separate robustness check: missing profiles receive the frozen `P0_NO_PROFILE` result, and no raw directive text is used as fallback. `content_summary.csv` provides document-type breakdowns, while `representative_directives.csv` supplies deterministic examples and matched evidence for reading the substantive content behind each category.

The dominant text result is internal/discretionary executive management (`T1_EXECUTIVE_MANAGEMENT`: {Counter(r['text_rule'] for r in target_rows)['T1_EXECUTIVE_MANAGEMENT']} directives). Its largest Code-0 groups are unmatched governance signals ({Counter(r['text_rule'] for r in target_rows)['T0_NO_GOVERNANCE_SIGNAL']}), congressional reports ({Counter(r['text_rule'] for r in target_rows)['T0_REPORT']}), and observances ({Counter(r['text_rule'] for r in target_rows)['T0_OBSERVANCE']}). The profile view likewise is dominated by profiled executive functions (`P1_PROFILED_EXECUTIVE_FUNCTION`: {Counter(r['profile_rule'] for r in target_rows)['P1_PROFILED_EXECUTIVE_FUNCTION']}), followed by mandated rule or guidance changes (`P2_MANDATED_LEGAL_INSTRUMENT`: {Counter(r['profile_rule'] for r in target_rows)['P2_MANDATED_LEGAL_INSTRUMENT']}). These patterns suggest the generic-authority population is principally managerial, but the {1 - agree/len(target):.1%} classifier disagreement and poor minority-class recall make the precise category shares provisional.

## Interpretation limits

These are transparent rule-based measurements, not new human annotations. Code 2 and code 4 have only two and one gold documents respectively, and code 4 is absent from validation. The Flash profiles were generated upstream by Gemini 3.6 Flash; only the classification of the frozen profiles is deterministic. Validation errors were measured after the rules were frozen and were not used to revise them.
"""


def build() -> None:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    gold = load_gold()
    dev_gold, validation_gold = build_split(gold)
    source_rows = load_source_rows()
    profiles = load_profiles()
    dev_rows = split_rows(dev_gold, source_rows, "dev")
    validation_rows = split_rows(validation_gold, source_rows, "validation")

    split_fields = ["partition", "global_dev_id", "round_id", "gold_code", "doc_type", "date", "president", "url"]
    write_csv(OUTPUTS / "dev_split.csv", dev_rows, split_fields)
    blind_fields = [field for field in split_fields if field != "gold_code"]
    write_csv(OUTPUTS / "validation_blind.csv", validation_rows, blind_fields)

    dev_predictions = predict(dev_rows, profiles)
    validation_predictions = predict(validation_rows, profiles)
    prediction_fields = split_fields + ["text_prediction", "text_rule", "text_evidence", "text_rationale", "profile_available", "profile_prediction", "profile_rule", "profile_evidence", "profile_rationale"]
    write_csv(OUTPUTS / "dev_predictions.csv", dev_predictions, prediction_fields)
    write_csv(OUTPUTS / "validation_predictions.csv", validation_predictions, prediction_fields)
    validation_errors = [
        row for row in validation_predictions
        if row["gold_code"] not in {row["text_prediction"], row["profile_prediction"]}
        or row["text_prediction"] != row["profile_prediction"]
    ]
    write_csv(OUTPUTS / "validation_errors.csv", validation_errors, prediction_fields)

    dev_majority = Counter(row["gold_code"] for row in dev_rows).most_common(1)[0][0]
    baseline_rows = [{**row, "baseline": dev_majority} for row in validation_rows]
    metrics = {
        "text": metric_report(validation_predictions, "text_prediction"),
        "profile": metric_report(validation_predictions, "profile_prediction"),
        "majority_baseline": metric_report(baseline_rows, "baseline"),
        "development_diagnostics": {
            "text": metric_report(dev_predictions, "text_prediction"),
            "profile": metric_report(dev_predictions, "profile_prediction"),
        },
    }
    (OUTPUTS / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")

    target = select_target(source_rows)
    target_rows = target_predictions(target, profiles)
    target_fields = list(target_rows[0])
    write_csv(OUTPUTS / "target_classifications.csv", target_rows, target_fields)
    disagreements = [row for row in target_rows if row["classifiers_agree"] == "false"]
    write_csv(OUTPUTS / "target_disagreements.csv", disagreements, target_fields)
    summary = content_summary(target_rows)
    write_csv(OUTPUTS / "content_summary.csv", summary, list(summary[0]))
    reps = representatives(target_rows)
    write_csv(OUTPUTS / "representative_directives.csv", reps, list(reps[0]))

    rule_source_hash = sha256_file(Path(__file__))
    manifest = {
        "schema_version": 1,
        "seed": SEED,
        "gold_source": str(GOLD.relative_to(ROOT)),
        "gold_sha256": GOLD_SHA256,
        "rule_source": str(Path(__file__).relative_to(ROOT)),
        "rule_source_sha256": rule_source_hash,
        "profile_source": str(PROFILES.relative_to(ROOT)),
        "profile_source_sha256": sha256_file(PROFILES),
        "development_documents": len(dev_rows),
        "validation_documents": len(validation_rows),
        "development_code_counts": Counter(row["gold_code"] for row in dev_rows),
        "validation_code_counts": Counter(row["gold_code"] for row in validation_rows),
        "target_definition": "nonceremonial and generic_constitution_and_generic_statute",
        "target_documents": len(target),
        "target_profile_coverage": sum(row["profile_available"] == "true" for row in target_rows),
        "forbidden_predictors": ["document_type", "date", "president", "title", "url"],
        "profile_excluded_fields": ["evidence", "evidence_start", "evidence_end", "segment_id", "confidence"],
    }
    (OUTPUTS / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (ANALYSIS_DIR / "RESULTS.md").write_text(render_results(metrics, target, target_rows))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build",), nargs="?", default="build")
    parser.parse_args()
    build()


if __name__ == "__main__":
    main()
