# In-text citation analysis handoff

## Current status

The network-free implementation and benchmark package are complete. No Terra or Sol request
has been submitted.

- The canonical local development CSV now has 18,418 unique directives.
- The tracked holdout CSV now has the correct 1,814 directives.
- Development and holdout are disjoint and reproduce all 20,232 rows in the historical master.
- The development and holdout ID hashes match `data/corpus_partition_manifest.json`.
- The analysis loader rejects a wrong development count/hash or any protected holdout ID.
- The 200-document benchmark, review page, regex predictions, and medium-reasoning Terra/Sol
  request files have been generated.
- Ten local analysis tests pass. Python compilation, request dry runs, the embedded review-page
  JavaScript syntax check, and a field-level corpus reconstruction check also pass.

The remaining work begins with human review. Production is intentionally blocked until the
locked benchmark passes the agreed 90% precision-and-recall gates.

## Important files

- `README.md`: definitions and command overview.
- `pipeline.py`: sampling, request preparation, validation, hybrid construction, scoring,
  corpus materialization, and final summaries.
- `citation_core.py`: corpus guard, region construction, regex baseline, normalization, and
  response validation.
- `model_prompt.md` and `model_response.schema.json`: shared direct-extraction contract.
- `run_models.py`: resumable runner; inert unless both execution confirmation flags are given.
  Started requests without durable responses are held as unknown unless an explicit
  `--retry-unknown` override is supplied, preventing accidental duplicate submissions.
- `outputs/benchmark/annotator_batch_1.html` and `annotator_batch_2.html`: standalone
  100-document human-review interfaces with explicit body-to-vesting authority links.
- `outputs/benchmark/review.html`: combined 200-document version of the same interface.
- `outputs/benchmark/documents.jsonl`: 200 review documents with substantive regions.
- `outputs/benchmark/regex_predictions.jsonl`: editable baseline annotations.
- `outputs/benchmark/terra_requests.jsonl` and `sol_requests.jsonl`: 200 prepared requests each.
- `outputs/benchmark/sample_manifest.json`: seed, corpus hash, split/type/stratum counts, and
  explicit zero-holdout assertion.

## Benchmark facts

- Seed: `260907`.
- Calibration: 100 vesting-clause documents (31 executive orders, 20 memoranda, 18
  letters, and 31 proclamations).
- Locked evaluation: the same 100-document type allocation.
- The sample covers nine decades.
- All 200 sampled documents contain structural vesting clauses.
- The current regex baseline proposes 477 citation records. These are starting
  annotations, not findings.

## Next step: human gold labels

Give the two `outputs/benchmark/annotator_batch_*.html` files to the annotators. For every document:

1. Inspect all displayed vesting and body segments.
2. Correct, add, merge, or delete citation records in the JSON editor.
3. For every included body authority, record the matching vesting authority key or `null`.
4. Keep evidence verbatim and use only text-grounded identity links.
5. Check the certification box and save.
6. Export each batch after its 100 documents are certified, concatenate the two JSONL
   exports, and place the result at `outputs/benchmark/gold.jsonl`.

The review page has separate editors for citations, body-to-vesting mappings, and unresolved
identity links, and refuses to export a partial certification set. Server-side validation
also checks body-to-vesting completeness, identity-link references, excluded-record keys,
and optional evidence offsets.

Validate it before any model scoring:

```bash
python3 "analysis/in-text citations/pipeline.py" validate-gold \
  --documents "analysis/in-text citations/outputs/benchmark/documents.jsonl" \
  --gold "analysis/in-text citations/outputs/benchmark/gold.jsonl" \
  --output "analysis/in-text citations/outputs/benchmark/gold_validated.jsonl"
```

## Prepared model workflow — do not run without an explicit decision

The runner prints a request summary and exits unless both `--execute` and
`--confirm-model-run` are present. A dry check is safe:

```bash
python3 "analysis/in-text citations/run_models.py" \
  "analysis/in-text citations/outputs/benchmark/terra_requests.jsonl" \
  "analysis/in-text citations/outputs/benchmark/terra_raw_responses.jsonl"
```

When model execution is explicitly approved, run Terra same command with both confirmation
flags, then repeat for Sol. Validate raw results with `pipeline.py validate-responses`.

After Terra validation, build hybrid high-reasoning Sol requests for disagreements:

```bash
python3 "analysis/in-text citations/pipeline.py" build-hybrid-requests \
  --documents "analysis/in-text citations/outputs/benchmark/documents.jsonl" \
  --regex "analysis/in-text citations/outputs/benchmark/regex_predictions.jsonl" \
  --terra "analysis/in-text citations/outputs/benchmark/terra_validated.jsonl" \
  --output "analysis/in-text citations/outputs/benchmark/hybrid_requests.jsonl"
```

Run and validate those requests, then use `combine-hybrid`. Score regex, Terra, Sol, and
hybrid with repeated `--prediction NAME=PATH` arguments. Scoring uses only the 100 locked
evaluation records, reports instrument/provision results plus region/source-type diagnostics,
and selects a method only when both identity levels reach at least 90% precision and recall.

## Production gate

Do not build production model requests until `benchmark_score.json` contains a non-null
`selected_method`. The deterministic corpus package can be prepared without calls:

```bash
python3 "analysis/in-text citations/pipeline.py" build-corpus
```

That command creates only segmented inputs and regex candidates, records the exact development
hash, and marks the package `inputs_only`. If the selected method uses a model,
`build-requests` requires the passing score file through `--benchmark-score`. If no method
passes, stop; do not produce corpus frequencies from a failed extractor.

## Verification notes

The usual `pytest` executable and pytest module were unavailable in both local virtual
environments, so the existing pytest-style corpus unit test file was not run through pytest.
The new analysis suite uses standard `unittest` and passed. The canonical corpus constructor
was also exercised directly against the historical master, including field-level partition
equality after CSV materialization.

Unrelated pre-existing worktree changes were left untouched.
