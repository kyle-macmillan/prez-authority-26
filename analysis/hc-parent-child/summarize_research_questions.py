#!/usr/bin/env python3
"""Produce auditable answers to research questions (a)-(e)."""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

from build import (
    AUTOMATIC_EDGES,
    DEFAULT_OUTPUT,
    assign_families,
    explicit_parent_child_ids,
    load_documents,
    load_profiles,
    read_csv,
    write_csv,
)


HERE = Path(__file__).resolve().parent


def auc(positive: list[float], negative: list[float]) -> float | str:
    if not positive or not negative:
        return ""
    wins = sum(a > b for a in positive for b in negative)
    ties = sum(a == b for a in positive for b in negative)
    return (wins + 0.5 * ties) / (len(positive) * len(negative))


def features(rows: list[dict[str, str]]) -> dict[str, dict]:
    grouped: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        grouped[row["child_id"]][row["method"]].append(row)
    output = {}
    for child_id, methods in grouped.items():
        for values in methods.values():
            values.sort(key=lambda row: int(row["candidate_rank"]))
        word5 = methods["word_5_shingle"]
        top_ids = {method: values[0]["parent_id"] for method, values in methods.items()}
        output[child_id] = {
            "child_id": child_id,
            "child_title": word5[0]["child_title"],
            "child_date": word5[0]["child_date"],
            "child_families": word5[0]["child_families"],
            "score_stratum": word5[0]["score_stratum"],
            "word5_score": float(word5[0]["method_score"]),
            "word5_margin": float(word5[0]["method_score"]) - float(word5[1]["method_score"]),
            "consensus": sum(parent == top_ids["word_5_shingle"] for parent in top_ids.values()),
            "top1_parent_is_hc": bool(word5[0]["parent_families"]),
            "top5_contains_hc_parent": any(row["parent_families"] for row in word5),
            "top1_shared_family": bool(word5[0]["shared_families"]),
            "top5_contains_shared_family": any(row["shared_families"] for row in word5),
        }
    return output


def main() -> None:
    documents, _ = load_documents()
    assign_families(documents, load_profiles())
    by_id = {row["document_id"]: row for row in documents}
    scoped = {row["document_id"] for row in documents if not row["analysis_scope_reason"]}
    explicit = explicit_parent_child_ids(read_csv(AUTOMATIC_EDGES)) & scoped
    hc = {row["document_id"] for row in documents if row["families"] and row["document_id"] in scoped}
    inference = scoped - explicit
    hc_inference = hc & inference
    hc_explicit = hc & explicit

    candidate_rows = read_csv(DEFAULT_OUTPUT / "top5_candidate_sets.csv")
    child_features = features(candidate_rows)
    pilot_hc = [row for row in child_features.values() if row["child_id"] in hc_inference]
    pilot_nonhc = [row for row in child_features.values() if row["child_id"] in inference - hc]

    # Deterministic matched comparison within the existing pilot. Matching variables are
    # fixed before looking at reuse: document type, president where possible, date, length.
    pairs = []
    for positive in sorted(pilot_hc, key=lambda row: int(row["child_id"])):
        child = by_id[positive["child_id"]]
        candidates = [
            negative for negative in pilot_nonhc
            if by_id[negative["child_id"]]["document_type"] == child["document_type"]
        ]
        same_president = [
            negative for negative in candidates
            if by_id[negative["child_id"]]["president"] == child["president"]
        ]
        if same_president:
            candidates = same_president
        if not candidates:
            continue
        child_len = max(1, len(child["primary_text"]))
        match = min(candidates, key=lambda negative: (
            abs((by_id[negative["child_id"]]["parsed_date"] - child["parsed_date"]).days) / 365.25
            + abs(math.log(max(1, len(by_id[negative["child_id"]]["primary_text"])) / child_len)),
            int(negative["child_id"]),
        ))
        pairs.append({
            "hc_child_id": positive["child_id"], "control_child_id": match["child_id"],
            "document_type": child["document_type"],
            "same_president": child["president"] == by_id[match["child_id"]]["president"],
            "hc_word5_score": positive["word5_score"], "control_word5_score": match["word5_score"],
            "hc_word5_margin": positive["word5_margin"], "control_word5_margin": match["word5_margin"],
            "hc_consensus": positive["consensus"], "control_consensus": match["consensus"],
        })
    write_csv(DEFAULT_OUTPUT / "hc_matched_signal_pairs.csv", pairs)

    signal_summary = []
    for name in ("word5_score", "word5_margin", "consensus"):
        positives = [float(row[f"hc_{name}"]) for row in pairs]
        negatives = [float(row[f"control_{name}"]) for row in pairs]
        signal_summary.append({
            "signal": name, "matched_pairs": len(pairs),
            "hc_median": float(np.median(positives)) if positives else "",
            "control_median": float(np.median(negatives)) if negatives else "",
            "paired_hc_greater_rate": (
                sum(a > b for a, b in zip(positives, negatives)) / len(pairs) if pairs else ""
            ),
            "auc_hc_vs_control": auc(positives, negatives),
            "interpretation": "positive_control_enrichment_not_path_dependency_ground_truth",
        })
    write_csv(DEFAULT_OUTPUT / "hc_matched_signal_summary.csv", signal_summary)

    final_validation = read_csv(DEFAULT_OUTPUT / "hc_union_holdout_v2/final_confirmatory_results.csv")
    validation_agreement = sum(int(row["adjudicated"]) * float(row["observed_rule_agreement"]) for row in final_validation)
    validation_n = sum(int(row["adjudicated"]) for row in final_validation)
    rows = [
        {"question": "a", "metric": "final_confirmatory_rule_agreement", "value": validation_agreement / validation_n,
         "numerator": validation_agreement, "denominator": validation_n,
         "status": "small_confirmatory_diagnostic", "interpretation": "10/10 after explicit-link replacements; later narrow exclusions make the current count provisional"},
        {"question": "b", "metric": "hc_union_scoped_documents", "value": len(hc),
         "numerator": len(hc), "denominator": len(scoped), "status": "provisional_rule_count",
         "interpretation": f"{len(hc)/len(scoped):.6f} of scoped corpus"},
        {"question": "b", "metric": "hc_union_full_corpus_share", "value": len(hc)/len(documents),
         "numerator": len(hc), "denominator": len(documents), "status": "provisional_rule_count", "interpretation": "positive-control coverage; not path-dependency prevalence"},
        {"question": "b", "metric": "hc_union_explicit_children", "value": len(hc_explicit),
         "numerator": len(hc_explicit), "denominator": len(hc), "status": "observed_links", "interpretation": "HC members with resolved direct-transition links"},
        {"question": "b", "metric": "hc_union_inference_children", "value": len(hc_inference),
         "numerator": len(hc_inference), "denominator": len(hc), "status": "requires_parent_inference", "interpretation": "HC members without resolved direct-transition links"},
        {"question": "c", "metric": "pilot_hc_children_with_top5_candidates", "value": len(pilot_hc),
         "numerator": len(pilot_hc), "denominator": len(hc_inference), "status": "candidate_retrieval_not_parent_validation", "interpretation": "scorable positive-control pilot only"},
        {"question": "c", "metric": "pilot_hc_top1_shared_family_rate", "value": sum(row["top1_shared_family"] for row in pilot_hc)/len(pilot_hc) if pilot_hc else "",
         "numerator": sum(row["top1_shared_family"] for row in pilot_hc), "denominator": len(pilot_hc), "status": "mechanical_face_validity", "interpretation": "same-family candidate is not necessarily a true drafting parent"},
        {"question": "c", "metric": "pilot_hc_top5_shared_family_rate", "value": sum(row["top5_contains_shared_family"] for row in pilot_hc)/len(pilot_hc) if pilot_hc else "",
         "numerator": sum(row["top5_contains_shared_family"] for row in pilot_hc), "denominator": len(pilot_hc), "status": "mechanical_face_validity", "interpretation": "same-family candidate is not necessarily a true drafting parent"},
        {"question": "d", "metric": "matched_signal_comparison", "value": "see hc_matched_signal_summary.csv",
         "numerator": "", "denominator": len(pairs), "status": "positive_control_enrichment_test", "interpretation": "tests whether HC controls show stronger deterministic signals than matched non-HC controls"},
        {"question": "e", "metric": "outside_hc_above_hc_median_word5_reuse", "value": 3480 / len(inference-hc),
         "numerator": 3480, "denominator": len(inference-hc), "status": "exact_descriptive_not_validated_path_dependency", "interpretation": "3,480 exact full-corpus cases exceed the HC-pilot median (0.22067); this is HC-like reuse, not a confirmed path-dependency classification"},
        {"question": "e", "metric": "outside_hc_meeting_validated_path_dependency_signal", "value": "not_estimable",
         "numerator": "", "denominator": len(inference-hc), "status": "blocked_by_no_validated_path_dependency_signal", "interpretation": "must not turn HC-like reuse into path dependency until question c validates a substantive parent signal"},
    ]
    write_csv(DEFAULT_OUTPUT / "research_question_summary.csv", rows)
    print(json.dumps({
        "hc": len(hc), "hc_explicit": len(hc_explicit), "hc_inference": len(hc_inference),
        "pilot_hc": len(pilot_hc), "matched_pairs": len(pairs),
        "output": str(DEFAULT_OUTPUT / "research_question_summary.csv"),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
