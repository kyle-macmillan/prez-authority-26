#!/usr/bin/env python3
"""Apply the documented source-exact evidence repair for the final EO response.

The frozen model repeatedly returned the same classifications for EO 742 but shortened
one evidence span by deleting an internal clause. This script changes no classification
or rationale. It replaces only that quotation with the corresponding contiguous source
span, validates the complete response, and records the repair provenance.
"""
from __future__ import annotations

import json
from pathlib import Path

import sol_eo_population as population
import sol_subdirective_benchmark as benchmark


DOCUMENT_ID = "742"
SEGMENT_ID = "742:oa:001"
RETURNED_EVIDENCE = (
    "Agencies with direct international development programs and investments shall work "
    "together with science and security agencies and entities"
)
REPAIRED_EVIDENCE = (
    "Agencies with direct international development programs and investments and those "
    "that participate in multilateral entities shall work together with science and "
    "security agencies and entities"
)


def main() -> None:
    output = population.OUTPUTS
    prompt_hash = json.loads((output / "prompt_frozen.json").read_text())["sha256"]
    requests = {str(row["document_id"]): row for row in json.loads((output / "requests.json").read_text())}
    request = requests[DOCUMENT_ID]
    text_by_id = {row["segment_id"]: row["text"] for row in request["segments"]}

    answer_path = output / "logs" / f"000742.{prompt_hash[:10]}.attempt2.answer.json"
    answer = json.loads(answer_path.read_text())
    item = next(row for row in answer["classifications"] if row["segment_id"] == SEGMENT_ID)
    if item["evidence"] != RETURNED_EVIDENCE:
        raise ValueError("the frozen response no longer has the expected rejected evidence")
    if benchmark.evidence_matches(RETURNED_EVIDENCE, text_by_id[SEGMENT_ID]):
        raise ValueError("the returned evidence unexpectedly passes source validation")
    if not benchmark.evidence_matches(REPAIRED_EVIDENCE, text_by_id[SEGMENT_ID]):
        raise ValueError("the repaired evidence is not a contiguous source span")
    item["evidence"] = REPAIRED_EVIDENCE

    validated, errors = population.parse_answer_from_value(answer, request)
    if errors:
        raise ValueError(f"repaired response is invalid: {errors}")

    responses = benchmark.read_jsonl(output / "responses.jsonl")
    prior = next(
        row for row in reversed(responses)
        if str(row.get("document_id")) == DOCUMENT_ID and row.get("prompt_hash") == prompt_hash
    )
    repair = {
        "type": "source_exact_evidence_repair",
        "document_id": DOCUMENT_ID,
        "segment_id": SEGMENT_ID,
        "prompt_hash": prompt_hash,
        "model_classification_changed": False,
        "rationale_changed": False,
        "returned_evidence": RETURNED_EVIDENCE,
        "repaired_evidence": REPAIRED_EVIDENCE,
        "reason": "The model deleted an internal source clause from an otherwise verbatim quotation.",
    }
    record = {**prior, "at": benchmark.utc_now(), "ok": True, "answer": validated,
              "validation_errors": [], "manual_evidence_repair": repair}
    benchmark.append_jsonl(output / "manual_repairs.jsonl", repair)
    benchmark.append_jsonl(output / "responses.jsonl", record)
    population.write_json(output / "status.json", {
        "processed_eos": population.EXPECTED_CALLS,
        "successful_eos": population.EXPECTED_CALLS,
        "failed_eos": 0,
        "total_called_eos": population.EXPECTED_CALLS,
        "current_document_id": DOCUMENT_ID,
        "updated_at": benchmark.utc_now(),
        "prompt_hash": prompt_hash,
    })
    print(json.dumps(repair, indent=2))


if __name__ == "__main__":
    main()
