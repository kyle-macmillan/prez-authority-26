# Round 4 enriched annotations

The sample reserves 56 documents likely to contain category 2, 42 likely to contain
category 3, and 41 random unseen documents. These are document selection strata,
not human labels. Category 2 is deliberately oversampled because the finalized
rounds 2–3 contain only 11 category-2 subdirectives out of 526.

Distribute only `round_4.html` to annotators once the build is complete. It uses
the existing annotation interface, full documents, displayed extended W&P
subdirectives, and independent round-4 local storage and JSON exports. Do not
distribute the screening directory or sampling manifest with the blind task.

## Reproduce or resume

From the repository root:

```bash
python3 src/build_annotation_round4.py prepare
python3 src/build_annotation_round4.py diagnostic --smoke
python3 src/build_annotation_round4.py diagnostic
python3 src/build_annotation_round4.py screen
python3 src/build_annotation_round4.py build
```

`prepare` is local and freezes the random draw, eligible population, retrieval
signals, diagnostic cohort, and prompt. Model stages invoke the existing
`gpt-5.6-sol` / low Codex workflow, one request per document and four concurrent
requests by default. Each request includes full context and separately marked
subdirectives. No tools or web search are allowed in classifications. Diagnostic
requests use the historical human-labeled chunks; candidate requests use the exact
current viewer chunks. Human gold labels are not included in requests.

The diagnostic contains all eight previously labeled category-2 documents,
12 additional category-3 documents, and 10 controls. It is a purposive diagnostic
on previously exposed data, not an independent accuracy estimate. The unseen
screening limit is 500 distinct documents, additional to the 30 diagnostics.

Candidate batches contain 100 documents, initially allocating approximately
two-thirds of retrieval slots to category-2 signals. Later batches prioritize an
unfilled stratum. Retrieval searches both categories independently. Within each
stratum it cycles through seeded mechanism/document-type/administration cells.
The random 41 are drawn first and excluded from targeted screening.

Selection uses the same seeded diversity procedure. Dual-positive documents fill
category 2 first. At the user's request, final selection prefers fewer subdirectives,
then fewer words, within otherwise comparable mechanism/type/administration cells;
seeded ordering breaks ties. Retrieval itself is not length-prioritized.
A greedy near-template cap permits at most three documents per
group, using 0.65 Jaccard similarity of word 5-grams with numbers normalized. This
is a diversity heuristic, not a guarantee that every recurring policy family is
identified. Inspect `screening/selection.json` and the final composition report.

Successful and failed results are retained. Completed results are reused only if
their request fingerprint matches. `--retry-failed` explicitly archives and retries
known failed results. A started request without a recorded outcome is never retried
automatically. Inspect its saved logs before resolving that state. Quota shortages
stop the build instead of changing the agreed mixture.

Service/process errors stop dispatch immediately; only requests already in flight
finish. After a service interruption, check recovery with one known failed request:

```bash
python3 src/build_annotation_round4.py screen --retry-failed --smoke --workers 1
python3 src/build_annotation_round4.py screen --retry-failed
```

## Artifacts and checks

- `round_4.html`: blinded annotation task, without predictions or selection reasons.
- `doc_id_map_viewer.json`: round-local IDs to original development IDs.
- `sample_manifest.json`: reproducibility, exclusions, strata counts, and workload.
- `screening/`: retrieval candidates, frozen prompt, requests, model results,
  diagnostics, batches, template checks, and final selection provenance.

Run focused checks with:

```bash
uv run --with pytest python -m pytest src/tests/test_annotation_round4.py src/tests/test_view_segments.py -q
```

The build checks exact sample size, stratum counts, exclusions, random/targeted
disjointness, and equality of every screened/displayed subdirective. Rerunning a
build from unchanged inputs reproduces the same sample and viewer.

After human annotation and adjudication, join labels through the global document
ID to `screening/selection.json`. Report category-2 and category-3 subdirective
counts and the share of documents containing each category separately for all
three strata. Preserve the random component for comparison. The enriched sample's
overall category proportions do not estimate corpus prevalence.
