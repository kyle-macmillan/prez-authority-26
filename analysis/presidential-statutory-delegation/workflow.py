#!/usr/bin/env python3
"""Prepare the blind pilot, freeze a reviewed prompt, and compile final metrics."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"
PILOT_FIELDS = (
    "pilot_id", "canonical_authority_id", "citation_kind", "is_broad",
    "occurrence_count", "observed_dates", "citation_aliases", "sample_vesting_clauses",
    "supplied_current_heading", "supplied_current_text", "supplied_amendment_notes",
    "supplied_official_url", "human_classifications_json", "human_notes",
)
CLASS_FIELDS = (
    "canonical_authority_id", "version_start", "version_end",
    "presidential_authorization", "presidential_required_duty",
    "presidential_condition_precedent", "standalone_presidential_constraint",
    "classification", "confidence", "operative_excerpt", "rationale", "official_sources",
)
RESOLVED_CLASSES = {"delegation", "nondelegation"}


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict], fields) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def select_pilot(packets: list[dict], size: int = 30) -> list[dict]:
    if len(packets) < size:
        raise ValueError(f"need {size} authority packets; found {len(packets)}")
    selected = []
    seen = set()

    def take(rows, count):
        for row in rows:
            key = row["canonical_authority_id"]
            if key not in seen:
                selected.append(row); seen.add(key)
                if len(selected) >= count:
                    return

    # Ten high-frequency authorities test the occurrence-weighted result.
    take(sorted(packets, key=lambda row: (-row["occurrence_count"], row["canonical_authority_id"])), 10)
    # Ten broad and non-U.S.C. authorities exercise the retained legacy scope.
    diverse = sorted(
        (row for row in packets if row["is_broad"] or row["citation_kind"] != "usc"),
        key=lambda row: (row["citation_kind"], hashlib.sha256(row["canonical_authority_id"].encode()).hexdigest()),
    )
    take(diverse, 20)
    # Deterministic hash sample supplies rare forms and eras without model labels.
    remainder = sorted(
        packets,
        key=lambda row: hashlib.sha256(("pilot-20260820:" + row["canonical_authority_id"]).encode()).hexdigest(),
    )
    take(remainder, size)
    return selected[:size]


def prepare_pilot(args) -> None:
    packets = read_jsonl(args.packets)
    selected = select_pilot(packets, args.size)
    rows = []
    for index, packet in enumerate(selected, 1):
        rows.append({
            "pilot_id": f"PSD{index:03d}",
            "canonical_authority_id": packet["canonical_authority_id"],
            "citation_kind": packet["citation_kind"],
            "is_broad": str(packet["is_broad"]).lower(),
            "occurrence_count": packet["occurrence_count"],
            "observed_dates": json.dumps(packet["observed_dates"]),
            "citation_aliases": json.dumps(packet["citation_aliases"], ensure_ascii=False),
            "sample_vesting_clauses": json.dumps(packet["sample_vesting_clauses"], ensure_ascii=False),
            "supplied_current_heading": packet["supplied_current_heading"],
            "supplied_current_text": packet["supplied_current_text"],
            "supplied_amendment_notes": packet["supplied_amendment_notes"],
            "supplied_official_url": packet["supplied_official_url"],
            "human_classifications_json": "",
            "human_notes": "",
        })
    write_csv(args.output, rows, PILOT_FIELDS)
    write_json(args.output.with_suffix(".manifest.json"), {
        "schema_version": 1, "pilot_size": len(rows),
        "selection": "10 highest-frequency, 10 broad/non-USC, 10 deterministic hash sample",
        "model_outputs_excluded": True,
        "authority_ids": [row["canonical_authority_id"] for row in rows],
        "packets_sha256": hashlib.sha256(args.packets.read_bytes()).hexdigest(),
    })
    print(json.dumps({"pilot": str(args.output), "rows": len(rows)}, indent=2))


def parse_human_gold(path: Path) -> dict[str, list[dict]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    gold = {}
    for row in rows:
        raw = row["human_classifications_json"].strip()
        if not raw:
            continue
        values = json.loads(raw)
        if not isinstance(values, list) or not values:
            raise ValueError(f"{row['pilot_id']} human_classifications_json must be a nonempty JSON list")
        gold[row["canonical_authority_id"]] = values
    return gold


def freeze_prompt(args) -> None:
    gold = parse_human_gold(args.human_gold)
    with args.human_gold.open(newline="", encoding="utf-8") as handle:
        expected = len(list(csv.DictReader(handle)))
    if len(gold) != expected:
        raise SystemExit(f"human gold incomplete: {len(gold)}/{expected} rows coded")
    responses = {row["canonical_authority_id"]: row for row in read_jsonl(args.pilot_responses) if row.get("ok")}
    if len(responses) != expected:
        raise SystemExit(f"pilot responses incomplete: {len(responses)}/{expected} valid")
    prompt = args.prompt.read_text(encoding="utf-8")
    artifact = {
        "schema_version": 1,
        "prompt": prompt,
        "sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "human_gold_sha256": hashlib.sha256(args.human_gold.read_bytes()).hexdigest(),
        "pilot_responses_sha256": hashlib.sha256(args.pilot_responses.read_bytes()).hexdigest(),
        "pilot_authorities": sorted(gold),
        "frozen_at": datetime.now().astimezone().isoformat(),
    }
    write_json(args.output, artifact)
    print(json.dumps({key: artifact[key] for key in ("sha256", "frozen_at")}, indent=2))


def evaluate_pilot(args) -> None:
    gold = parse_human_gold(args.human_gold)
    responses = {
        row["canonical_authority_id"]: row["answer"]["classifications"]
        for row in read_jsonl(args.pilot_responses) if row.get("ok")
    }
    rows = []
    for authority_id in sorted(set(gold) | set(responses)):
        human = gold.get(authority_id)
        model = responses.get(authority_id)
        human_compact = json.dumps(human, sort_keys=True, ensure_ascii=False) if human else ""
        model_compact = json.dumps(model, sort_keys=True, ensure_ascii=False) if model else ""
        rows.append({
            "canonical_authority_id": authority_id,
            "human_classifications_json": human_compact,
            "model_classifications_json": model_compact,
            "exact_agreement": str(bool(human and model and human_compact == model_compact)).lower(),
            "review_disposition": "",
            "review_notes": "",
        })
    write_csv(args.output, rows, rows[0].keys())
    write_json(args.output.with_suffix(".summary.json"), {
        "pilot_authorities": len(rows),
        "human_complete": len(gold),
        "model_complete": len(responses),
        "exact_agreements": sum(row["exact_agreement"] == "true" for row in rows),
        "note": "Exact agreement is intentionally strict; review type/date/source differences in the CSV before freezing.",
    })
    print(json.dumps({"comparison": str(args.output), "rows": len(rows)}, indent=2))


def compare_reruns(args) -> None:
    primary = {row["canonical_authority_id"]: row["answer"] for row in read_jsonl(args.primary) if row.get("ok")}
    targeted = {row["canonical_authority_id"]: row["answer"] for row in read_jsonl(args.targeted) if row.get("ok")}
    rows = []
    for authority_id, second in sorted(targeted.items()):
        first = primary.get(authority_id)
        first_json = json.dumps(first, sort_keys=True, ensure_ascii=False) if first else ""
        second_json = json.dumps(second, sort_keys=True, ensure_ascii=False)
        substantive_fields = (
            "version_start", "version_end", "presidential_authorization",
            "presidential_required_duty", "presidential_condition_precedent",
            "standalone_presidential_constraint", "classification",
        )
        signature = lambda answer: [
            {field: item.get(field) for field in substantive_fields}
            for item in answer.get("classifications", [])
        ] if answer else []
        rows.append({
            "canonical_authority_id": authority_id,
            "primary_answer_json": first_json,
            "targeted_answer_json": second_json,
            "substantive_agreement": str(signature(first) == signature(second)).lower(),
            "adjudicated_answer_json": "",
            "review_notes": "",
        })
    if rows:
        write_csv(args.output, rows, rows[0].keys())
    else:
        write_csv(args.output, [], ("canonical_authority_id", "primary_answer_json", "targeted_answer_json",
                                    "substantive_agreement", "adjudicated_answer_json", "review_notes"))
    print(json.dumps({"review_queue": str(args.output), "rows": len(rows)}, indent=2))


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).casefold() == "true"


def flatten_responses(path: Path, prompt_hash: str | None = None) -> list[dict]:
    answers = {}
    for response in read_jsonl(path):
        if not response.get("ok") or (prompt_hash and response.get("prompt_hash") != prompt_hash):
            continue
        answer = response["answer"]
        answers[answer["canonical_authority_id"]] = answer
    return [
        {"canonical_authority_id": authority_id, **item}
        for authority_id, answer in sorted(answers.items())
        for item in answer["classifications"]
    ]


def _date_match(rows: list[dict], date_text: str) -> dict | None:
    target = datetime.strptime(date_text, "%B %d, %Y").date()
    matches = []
    for row in rows:
        start = date.fromisoformat(row["version_start"])
        end = date.fromisoformat(row["version_end"]) if row.get("version_end") else None
        if start <= target and (end is None or target <= end):
            matches.append(row)
    if len(matches) > 1:
        raise ValueError(f"overlapping versions on {date_text}")
    return matches[0] if matches else None


def compile_results(args) -> None:
    with args.occurrences.open(newline="", encoding="utf-8") as handle:
        occurrences = list(csv.DictReader(handle))
    prompt_hash = None
    frozen_prompt = getattr(args, "frozen_prompt", None)
    if frozen_prompt and frozen_prompt.exists():
        prompt_hash = json.loads(frozen_prompt.read_text(encoding="utf-8"))["sha256"]
    classifications = flatten_responses(args.responses, prompt_hash)
    occurrence_authorities = {row["canonical_authority_id"] for row in occurrences}
    response_authorities = {row["canonical_authority_id"] for row in classifications}
    missing_authorities = occurrence_authorities - response_authorities
    if missing_authorities and not getattr(args, "allow_incomplete", False):
        raise SystemExit(
            f"full run incomplete for {len(missing_authorities)} unique authorities; "
            "use --allow-incomplete only for a provisional coverage report"
        )
    review_queue = getattr(args, "review_queue", None)
    if review_queue and review_queue.exists():
        by_id = defaultdict(list)
        for row in classifications:
            by_id[row["canonical_authority_id"]].append(row)
        with review_queue.open(newline="", encoding="utf-8") as handle:
            review_rows = list(csv.DictReader(handle))
        for row in review_rows:
            authority_id = row["canonical_authority_id"]
            adjudicated = row.get("adjudicated_answer_json", "").strip()
            if adjudicated:
                answer = json.loads(adjudicated)
                if answer.get("canonical_authority_id") != authority_id:
                    raise ValueError(f"adjudication ID mismatch for {authority_id}")
                by_id[authority_id] = [
                    {"canonical_authority_id": authority_id, **item}
                    for item in answer["classifications"]
                ]
            elif row.get("substantive_agreement") != "true":
                raise SystemExit(f"unadjudicated targeted disagreement: {authority_id}")
        classifications = [item for authority_id in sorted(by_id) for item in by_id[authority_id]]
    by_authority = defaultdict(list)
    for row in classifications:
        by_authority[row["canonical_authority_id"]].append(row)
    mapped = []
    for occurrence in occurrences:
        match = _date_match(by_authority[occurrence["canonical_authority_id"]], occurrence["date"])
        if match is None:
            mapped.append({**occurrence, "classification": "cannot_verify", "mapping_status": "missing_date_version"})
        else:
            mapped.append({**occurrence, **match, "mapping_status": "mapped"})

    citation_counts = Counter(row["classification"] for row in mapped)
    resolved = citation_counts["delegation"] + citation_counts["nondelegation"]
    total = len(mapped)
    percent = lambda n, d: 100 * n / d if d else None
    citation_metrics = {
        "total_occurrences": total,
        "counts": dict(sorted(citation_counts.items())),
        "resolved_coverage_percent": percent(resolved, total),
        "delegation_percent_resolved": percent(citation_counts["delegation"], resolved),
        "nondelegation_percent_resolved": percent(citation_counts["nondelegation"], resolved),
        "delegation_share_all_occurrences_percent": percent(citation_counts["delegation"], total),
        "delegation_lower_bound_percent": percent(citation_counts["delegation"], total),
        "delegation_upper_bound_percent": percent(total - citation_counts["nondelegation"], total),
        "authorization_occurrences": sum(_as_bool(row.get("presidential_authorization")) for row in mapped),
        "required_duty_occurrences": sum(_as_bool(row.get("presidential_required_duty")) for row in mapped),
        "condition_precedent_occurrences": sum(_as_bool(row.get("presidential_condition_precedent")) for row in mapped),
        "constraint_occurrences": sum(_as_bool(row.get("standalone_presidential_constraint")) for row in mapped),
    }

    by_document = defaultdict(list)
    for row in mapped:
        by_document[row["document_id"]].append(row)
    directives = []
    for document_id, rows in sorted(by_document.items(), key=lambda item: int(item[0])):
        labels = {row["classification"] for row in rows}
        if "delegation" in labels and "nondelegation" in labels:
            rollup = "mixed"
        elif labels <= {"delegation"}:
            rollup = "all_delegating"
        elif labels <= {"nondelegation"}:
            rollup = "none_delegating"
        else:
            rollup = "partially_unresolved"
        directives.append({
            "document_id": document_id, "date": rows[0]["date"], "president": rows[0]["president"],
            "term": rows[0]["term"], "doc_type": rows[0]["doc_type"], "url": rows[0]["url"],
            "citation_count": len(rows), "delegation_count": sum(row["classification"] == "delegation" for row in rows),
            "nondelegation_count": sum(row["classification"] == "nondelegation" for row in rows),
            "unresolved_count": sum(row["classification"] not in RESOLVED_CLASSES for row in rows),
            "directive_classification": rollup,
        })
    directive_counts = Counter(row["directive_classification"] for row in directives)
    summary = {
        "citation_metrics": citation_metrics,
        "directive_metrics": {
            "directives": len(directives), "counts": dict(sorted(directive_counts.items())),
            "shares_percent": {key: percent(value, len(directives)) for key, value in sorted(directive_counts.items())},
        },
    }
    occurrence_fields = list(occurrences[0]) + [field for field in CLASS_FIELDS if field != "canonical_authority_id"] + ["mapping_status"]
    write_csv(args.output / "classified_occurrences.csv", mapped, occurrence_fields)
    write_csv(args.output / "classified_directives.csv", directives, directives[0].keys())
    write_csv(args.output / "authority_classifications.csv", classifications, CLASS_FIELDS)
    write_json(args.output / "results.json", summary)
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(required=True)
    prepare = sub.add_parser("prepare-pilot")
    prepare.add_argument("--packets", type=Path, default=OUTPUTS / "authority_packets.jsonl")
    prepare.add_argument("--output", type=Path, default=OUTPUTS / "pilot_human_gold.csv")
    prepare.add_argument("--size", type=int, default=30)
    prepare.set_defaults(func=prepare_pilot)
    freeze = sub.add_parser("freeze-prompt")
    freeze.add_argument("--human-gold", type=Path, default=OUTPUTS / "pilot_human_gold.csv")
    freeze.add_argument("--pilot-responses", type=Path, default=OUTPUTS / "pilot_responses.jsonl")
    freeze.add_argument("--prompt", type=Path, default=HERE / "prompt_candidate.md")
    freeze.add_argument("--output", type=Path, default=OUTPUTS / "frozen_prompt.json")
    freeze.set_defaults(func=freeze_prompt)
    evaluate = sub.add_parser("evaluate-pilot")
    evaluate.add_argument("--human-gold", type=Path, default=OUTPUTS / "pilot_human_gold.csv")
    evaluate.add_argument("--pilot-responses", type=Path, default=OUTPUTS / "pilot_responses.jsonl")
    evaluate.add_argument("--output", type=Path, default=OUTPUTS / "pilot_comparison.csv")
    evaluate.set_defaults(func=evaluate_pilot)
    compare = sub.add_parser("compare-reruns")
    compare.add_argument("--primary", type=Path, default=OUTPUTS / "full_responses.jsonl")
    compare.add_argument("--targeted", type=Path, default=OUTPUTS / "targeted_responses.jsonl")
    compare.add_argument("--output", type=Path, default=OUTPUTS / "targeted_review_queue.csv")
    compare.set_defaults(func=compare_reruns)
    compile_parser = sub.add_parser("compile-results")
    compile_parser.add_argument("--occurrences", type=Path, default=OUTPUTS / "citation_occurrences.csv")
    compile_parser.add_argument("--responses", type=Path, default=OUTPUTS / "full_responses.jsonl")
    compile_parser.add_argument("--review-queue", type=Path, default=OUTPUTS / "targeted_review_queue.csv")
    compile_parser.add_argument("--frozen-prompt", type=Path, default=OUTPUTS / "frozen_prompt.json")
    compile_parser.add_argument("--allow-incomplete", action="store_true")
    compile_parser.add_argument("--output", type=Path, default=OUTPUTS)
    compile_parser.set_defaults(func=compile_results)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
