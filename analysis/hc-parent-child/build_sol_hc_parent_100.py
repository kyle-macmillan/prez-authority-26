#!/usr/bin/env python3
"""Build a fresh 100-case, category-balanced HC parent-identification package."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from benchmark_deterministic_methods import masked
from build import (
    AUTOMATIC_EDGES,
    DEFAULT_OUTPUT,
    FAMILY_ORDER,
    FUNCTION_EMBEDDINGS,
    FunctionSimilarity,
    assign_families,
    balanced_sample,
    build_lexical_scores,
    explicit_parent_child_ids,
    load_documents,
    load_profiles,
    read_csv,
    sha256,
    stable_key,
    words,
    write_csv,
)


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUTPUT = DEFAULT_OUTPUT / "sol_hc_parent_100"
PER_FAMILY = 20
TOP_PER_CHANNEL = 5
SAME_FAMILY_RECENT = 2
CANDIDATE_LIMIT = 25
RRF_K = 60
SAMPLE_SALT = "sol-hc-parent-100-v1"


def prior_child_ids() -> set[str]:
    """Exclude children already used to develop metrics or parent judgments."""
    result: set[str] = set()
    top5 = DEFAULT_OUTPUT / "top5_candidate_sets.csv"
    if top5.is_file():
        result.update(row["child_id"] for row in read_csv(top5))
    for path in (ROOT / "data/parent_analysis/function_parent_pilot").glob("**/sampled_children.csv"):
        result.update(row["document_id"] for row in read_csv(path))
    for path in DEFAULT_OUTPUT.glob("**/*review_key.csv"):
        for row in read_csv(path):
            value = row.get("child_id") or row.get("document_id")
            if value:
                result.add(value)
    return result


def choose_children(documents: list[dict], profile_ids: set[str], excluded: set[str]) -> list[dict]:
    """Choose 20 unique children per family, favoring exclusive family members."""
    selected: list[dict] = []
    used: set[str] = set()
    earliest_family_date = {
        family: min(
            row["parsed_date"] for row in documents
            if family in row["families"] and not row["analysis_scope_reason"]
        )
        for family in FAMILY_ORDER
    }
    # Scarcer categories select first so overlapping cases cannot exhaust their pool.
    available_counts = {
        family: sum(
            family in row["families"] and row["document_id"] in profile_ids
            and row["document_id"] not in excluded and not row["analysis_scope_reason"]
            for row in documents
        )
        for family in FAMILY_ORDER
    }
    for family in sorted(FAMILY_ORDER, key=lambda item: (available_counts[item], item)):
        candidates = [
            row for row in documents
            if family in row["families"] and row["document_id"] in profile_ids
            and row["document_id"] not in excluded and row["document_id"] not in used
            and not row["analysis_scope_reason"]
            and earliest_family_date[family] < row["parsed_date"]
        ]
        # Prefer single-family cases, then use deterministic balancing within that ordering.
        exclusive = [row for row in candidates if len(row["families"]) == 1]
        chosen = balanced_sample(
            exclusive, min(PER_FAMILY, len(exclusive)), ("president", "document_type"),
            f"{SAMPLE_SALT}:{family}:exclusive",
        )
        if len(chosen) < PER_FAMILY:
            remaining = [row for row in candidates if row["document_id"] not in {x["document_id"] for x in chosen}]
            chosen.extend(balanced_sample(
                remaining, PER_FAMILY - len(chosen), ("president", "document_type"),
                f"{SAMPLE_SALT}:{family}:overlap",
            ))
        if len(chosen) != PER_FAMILY:
            raise ValueError(f"{family}: expected {PER_FAMILY} eligible children, found {len(chosen)}")
        for row in chosen:
            used.add(row["document_id"])
            selected.append({**row, "assigned_family": family})
    selected.sort(key=lambda row: (FAMILY_ORDER.index(row["assigned_family"]), stable_key(
        f"{SAMPLE_SALT}:case:{row['document_id']}"
    )))
    if len(selected) != PER_FAMILY * len(FAMILY_ORDER) or len(used) != len(selected):
        raise ValueError("balanced sample is not 100 unique children")
    return selected


def bm25_index(documents: list[dict], selected: list[dict]) -> tuple[dict, dict, dict]:
    wanted = {token for row in selected for token in words(row["primary_text"])}
    lengths: dict[str, int] = {}
    postings: dict[str, dict[str, int]] = defaultdict(dict)
    token_cache: dict[str, list[str]] = {}
    for row in documents:
        tokens = words(row["primary_text"])
        token_cache[row["document_id"]] = tokens
        lengths[row["document_id"]] = len(tokens)
        for token, count in Counter(tokens).items():
            if token in wanted:
                postings[token][row["document_id"]] = count
    return token_cache, lengths, postings


def bm25_scores(
    query: list[str], eligible: list[str], lengths: dict[str, int], postings: dict[str, dict[str, int]],
) -> dict[str, float]:
    eligible_set = set(eligible)
    n = len(eligible)
    average = sum(lengths[did] for did in eligible) / max(n, 1)
    output = {did: 0.0 for did in eligible}
    for token in set(query):
        matches = {did: tf for did, tf in postings.get(token, {}).items() if did in eligible_set}
        if not matches:
            continue
        document_frequency = len(matches)
        inverse_frequency = math.log(1 + (n - document_frequency + 0.5) / (document_frequency + 0.5))
        for did, frequency in matches.items():
            output[did] += inverse_frequency * frequency * 2.2 / (
                frequency + 1.2 * (0.25 + 0.75 * lengths[did] / average)
            )
    return output


def ranked(scores: dict[str, float]) -> tuple[list[str], dict[str, int]]:
    ordered = sorted(scores, key=lambda did: (-scores[did], int(did)))
    return ordered, {did: index for index, did in enumerate(ordered, 1)}


def compact_profile(profile: dict | None) -> dict:
    if not profile:
        return {"policy_functions": [], "operative_functions": []}
    fields = ("label", "actor", "action", "target", "mechanism", "effect", "condition", "timing", "confidence")
    return {
        kind: [{field: function.get(field, "") for field in fields} for function in profile.get(kind, [])]
        for kind in ("policy_functions", "operative_functions")
    }


def main() -> None:
    documents, _ = load_documents()
    profiles = load_profiles()
    assign_families(documents, profiles)
    by_id = {row["document_id"]: row for row in documents}
    explicit = explicit_parent_child_ids(read_csv(AUTOMATIC_EDGES))
    previously_seen = prior_child_ids()
    excluded = explicit | previously_seen
    selected = choose_children(documents, set(profiles), excluded)
    child_ids = [row["document_id"] for row in selected]

    lexical5 = build_lexical_scores(documents, child_ids, "primary_text", size=5)
    lexical10 = build_lexical_scores(documents, child_ids, "primary_text", size=10)
    function = FunctionSimilarity(FUNCTION_EMBEDDINGS)
    token_cache, lengths, postings = bm25_index(documents, selected)
    dates = np.asarray([row["parsed_date"].timestamp() for row in documents])
    ids = np.asarray([row["document_id"] for row in documents])
    scoped = np.asarray([not row["analysis_scope_reason"] for row in documents])
    position = {row["document_id"]: index for index, row in enumerate(documents)}

    sample_rows: list[dict] = []
    key_rows: list[dict] = []
    requests: list[dict] = []
    for number, child in enumerate(selected, 1):
        child_id = child["document_id"]
        case_id = f"SHC{number:03d}"
        eligible_mask = (dates < child["parsed_date"].timestamp()) & scoped
        eligible_positions = np.flatnonzero(eligible_mask)
        eligible_ids = ids[eligible_positions].astype(str).tolist()
        channel_scores: dict[str, dict[str, float]] = {
            "word5": {did: float(lexical5[child_id][position[did]]) for did in eligible_ids},
            "word10": {did: float(lexical10[child_id][position[did]]) for did in eligible_ids},
            "bm25": bm25_scores(token_cache[child_id], eligible_ids, lengths, postings),
        }
        function_result = function.scores(child_id)
        function_map = {}
        if function_result is not None:
            function_map = dict(zip(function_result[0], map(float, function_result[1]), strict=True))
        channel_scores["function"] = {did: function_map[did] for did in eligible_ids if did in function_map}
        channel_orders: dict[str, list[str]] = {}
        channel_ranks: dict[str, dict[str, int]] = {}
        for channel, scores in channel_scores.items():
            channel_orders[channel], channel_ranks[channel] = ranked(scores)

        candidate_ids: set[str] = set()
        retrieval_sources: dict[str, set[str]] = defaultdict(set)
        for channel, order in channel_orders.items():
            for did in order[:TOP_PER_CHANNEL]:
                candidate_ids.add(did)
                retrieval_sources[did].add(channel)
        same_family = sorted(
            (
                row for row in documents
                if child["assigned_family"] in row["families"]
                and row["parsed_date"] < child["parsed_date"] and not row["analysis_scope_reason"]
            ),
            key=lambda row: (-row["parsed_date"].timestamp(), int(row["document_id"])),
        )[:SAME_FAMILY_RECENT]
        for row in same_family:
            candidate_ids.add(row["document_id"])
            retrieval_sources[row["document_id"]].add("same_family_recent")

        # Preserve the diversified union, then fill it to a fixed 25 with the
        # strongest remaining reciprocal-rank-fusion candidates. This raises
        # candidate recall without letting any single retrieval channel define
        # the pool that Sol judges.
        fused_scores = {
            did: sum(
                1 / (RRF_K + ranks[did])
                for ranks in channel_ranks.values()
                if did in ranks
            )
            for did in eligible_ids
        }
        fused_order, fused_ranks = ranked(fused_scores)
        for did in fused_order:
            if len(candidate_ids) >= CANDIDATE_LIMIT:
                break
            if did not in candidate_ids:
                candidate_ids.add(did)
                retrieval_sources[did].add("rrf_fill")
        if len(candidate_ids) != CANDIDATE_LIMIT:
            raise ValueError(
                f"{case_id}: expected {CANDIDATE_LIMIT} candidates, found {len(candidate_ids)}"
            )

        displayed_ids = sorted(
            candidate_ids,
            key=lambda did: hashlib.sha256(f"{SAMPLE_SALT}:display:{case_id}:{did}".encode()).hexdigest(),
        )
        candidates = []
        for candidate_number, parent_id in enumerate(displayed_ids, 1):
            label = f"C{candidate_number:02d}"
            parent = by_id[parent_id]
            candidates.append({
                "candidate_label": label,
                "title": parent["title"],
                "date": parent["date"],
                "document_type": parent["document_type"],
                "non_vesting_text": masked(parent["primary_text"]),
                "function_profile": compact_profile(profiles.get(parent_id)),
            })
            key_rows.append({
                "case_id": case_id,
                "child_id": child_id,
                "assigned_family": child["assigned_family"],
                "all_child_families": "|".join(child["families"]),
                "candidate_label": label,
                "parent_id": parent_id,
                "retrieval_sources": "|".join(sorted(retrieval_sources[parent_id])),
                **{
                    f"{channel}_score": channel_scores[channel].get(parent_id, "")
                    for channel in channel_scores
                },
                **{
                    f"{channel}_rank": channel_ranks[channel].get(parent_id, "")
                    for channel in channel_scores
                },
                "rrf_score": fused_scores[parent_id],
                "rrf_rank": fused_ranks[parent_id],
            })
        requests.append({
            "case_id": case_id,
            "child": {
                "title": child["title"],
                "date": child["date"],
                "document_type": child["document_type"],
                "non_vesting_text": masked(child["primary_text"]),
                "function_profile": compact_profile(profiles.get(child_id)),
            },
            "candidates": candidates,
        })
        sample_rows.append({
            "case_id": case_id,
            "document_id": child_id,
            "assigned_family": child["assigned_family"],
            "all_families": "|".join(child["families"]),
            "document_type": child["document_type"],
            "president": child["president"],
            "date": child["date"],
            "title": child["title"],
            "candidate_count": len(candidates),
        })
        print(json.dumps({"built": number, "total": len(selected), "case_id": case_id}), flush=True)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    requests_dir = OUTPUT / "requests"
    requests_dir.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT / "sampled_children.csv", sample_rows)
    write_csv(OUTPUT / "candidate_pool_key.csv", key_rows)
    for request in requests:
        (requests_dir / f"{request['case_id']}.json").write_text(
            json.dumps(request, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
        )
    manifest = {
        "kind": "balanced_hc_silver_parent_identification",
        "sample_salt": SAMPLE_SALT,
        "rows": len(sample_rows),
        "per_assigned_family": dict(Counter(row["assigned_family"] for row in sample_rows)),
        "unique_children": len({row["document_id"] for row in sample_rows}),
        "child_scope": "scoped HC, no resolved explicit link, canonical operative profile available",
        "prior_metric_and_review_children_excluded": len(previously_seen),
        "explicit_link_children_excluded": len(explicit),
        "candidate_channels": {
            "word5": TOP_PER_CHANNEL,
            "word10": TOP_PER_CHANNEL,
            "bm25": TOP_PER_CHANNEL,
            "function": TOP_PER_CHANNEL,
            "same_family_recent": SAME_FAMILY_RECENT,
            "rrf_fill_to": CANDIDATE_LIMIT,
            "rrf_k": RRF_K,
        },
        "candidate_pool_size": CANDIDATE_LIMIT,
        "candidate_pool_design": "diversified channel union, deduplicated, then RRF-filled to 25",
        "blinding": "requests omit HC category, document IDs, retrieval methods, scores, and ranks",
        "text": "vesting clauses and generic boilerplate removed; directive-number references masked",
        "function_embedding_snapshot": function.snapshot_hash,
        "intended_model": "gpt-5.6-sol",
        "intended_reasoning_effort": "low",
        "inputs": {
            str(FUNCTION_EMBEDDINGS.relative_to(ROOT)): sha256(FUNCTION_EMBEDDINGS),
            str(AUTOMATIC_EDGES.relative_to(ROOT)): sha256(AUTOMATIC_EDGES),
        },
        "outputs": {
            "sampled_children.csv": sha256(OUTPUT / "sampled_children.csv"),
            "candidate_pool_key.csv": sha256(OUTPUT / "candidate_pool_key.csv"),
        },
    }
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output": str(OUTPUT), "manifest": manifest}, sort_keys=True))


if __name__ == "__main__":
    main()
