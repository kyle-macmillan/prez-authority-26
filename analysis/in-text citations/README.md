# In-text citations

This analysis compares authorities in presidential-directive vesting clauses with legal
sources cited elsewhere in the substantive text. It is locked to the canonical 18,418-row
development partition and fails if any protected holdout ID is present.

## Definitions

- **Vesting** uses the project's existing structural vesting-clause segmentation.
- **Body** includes recitals, preambles, operative provisions, and general provisions;
  structural metadata is excluded.
- The authority universe includes identifiable operative legal instruments from any
  jurisdiction. Citation role does not matter. Proposed measures, reports, internal
  references, and vague legal phrases are excluded.
- Identity links are text-grounded. Plausible external crosswalks remain unresolved.

## Benchmark workflow

Build the deterministic 200-document sample and regex baseline:

```bash
python3 "analysis/in-text citations/pipeline.py" build-benchmark
```

Open `outputs/benchmark/review.html`, inspect every substantive segment, edit the JSON
records, certify documents, and export `gold.jsonl`. One hundred records are calibration
documents and 100 are the locked evaluation set.

Prepare direct model requests without submitting them:

```bash
python3 "analysis/in-text citations/pipeline.py" build-requests \
  --documents "analysis/in-text citations/outputs/benchmark/documents.jsonl" \
  --method terra --output "analysis/in-text citations/outputs/benchmark/terra_requests.jsonl"
python3 "analysis/in-text citations/pipeline.py" build-requests \
  --documents "analysis/in-text citations/outputs/benchmark/documents.jsonl" \
  --method sol --output "analysis/in-text citations/outputs/benchmark/sol_requests.jsonl"
```

`run_models.py` only prints a dry-run summary by default. It cannot submit requests unless
both `--execute` and `--confirm-model-run` are supplied. Do not run models until the human
gold set and request package have been reviewed. A started request without a durable response
is held as spent/unknown and is not retried unless `--retry-unknown` is explicitly supplied.

Validate the exported gold file and direct responses before scoring:

```bash
python3 "analysis/in-text citations/pipeline.py" validate-gold \
  --documents "analysis/in-text citations/outputs/benchmark/documents.jsonl" \
  --gold gold.jsonl --output "analysis/in-text citations/outputs/benchmark/gold_validated.jsonl"
python3 "analysis/in-text citations/pipeline.py" validate-responses \
  --requests "analysis/in-text citations/outputs/benchmark/terra_requests.jsonl" \
  --responses terra_raw_responses.jsonl --method terra --output terra_validated.jsonl
```

After direct responses are validated, use `build-hybrid-requests` to prepare high-reasoning
Sol adjudication only for regex/Terra disagreements, then use `combine-hybrid`. Score the four
prediction files with repeated `--prediction NAME=PATH` arguments. Production is blocked
unless instrument- and provision-level precision and recall are each at least 90 percent.

The production corpus package can be materialized without model calls using
`pipeline.py build-corpus`. It records the corpus hash and its `inputs_only` status; request
execution and final summaries remain gated by the locked benchmark. Production request
generation additionally requires the passing score file through `--benchmark-score`.

## Outputs

All benchmark, request, response, audit, document-level, and summary artifacts remain below
`analysis/in-text citations/outputs/`. The protected holdout corpus is never an analysis
input or model-request source.
