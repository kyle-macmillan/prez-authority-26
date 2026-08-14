# Source layout

- `analysis/`: downstream statistical and clustering analysis tasks
- `embeddings/`: embedding generation and provenance maintenance
- `tests/`: Python and JavaScript tests
- root modules: shared segmentation, annotation-viewer generation, and parent-retrieval pipeline code

Run the Python test suite from the repository root with `pytest src/tests`.

Build the 200-child parent-candidate pilot viewer with:

`python src/build_parent_candidate_viewer.py`

The generated viewer is written to
`data/parent_analysis/pilot/parent_candidate_viewer.html`. It is intentionally ignored
because it embeds masked source documents; the sample CSV and manifest remain trackable.
Similarity scores and channel ranks are available behind an explicit toggle. Candidate
tabs follow ascending fused RRF rank.
Extended Woolley and Peters ordering phrases are bolded in full documents and in the
aligned operative-segment excerpts.

Build the corpus-wide Candidate 1 and Candidate 2 score distributions after ranking with:

`python src/analysis/candidate_score_distributions.py`

The command writes pair-level scores, descriptive statistics, and a six-panel histogram
report under `data/parent_analysis/candidate_score_distributions/`. Candidate positions
use three-channel RRF; W&P phrase agreement remains visible as a diagnostic but is not a
fusion channel.

The separate legally operative path-dependency pilot is organized under
`src/path_dependency/` with artifacts under
`data/parent_analysis/path_dependency_pilot/`. See the README files in those directories
for the GPU classification and viewer-generation commands.

## Function-profile pilot

Build authority-masked, reviewable Gemini requests without network access. By default,
the builder uses `data/parent_analysis_full/unresolved_children.csv`, whose IDs are the
non-ceremonial directives with no automatic parent edge:

`python src/build_function_profile_requests.py --output data/parent_analysis/function_profile_requests.jsonl`

Previously processed pilot IDs are also excluded by default via
`data/parent_analysis/function_profile_prior_consumed_ids.csv`. Use `--sample-per-type 50`
only for a pilot. Use `--all-documents` or `--ignore-consumed` only when deliberately
overriding the budget-safe defaults. The stable request ID is
`function-profile-v1:<document_id>`.

The request file must be reviewed before execution. If approved, the existing transport
harness requires both `--execute` and `--confirm-network`:

`python src/gemini_flash_harness.py data/parent_analysis/function_profile_requests.jsonl data/parent_analysis/function_profile_responses.jsonl --execute --confirm-network --google-search`

For the first budgeted batch, generate exactly 500 new requests:

`python src/build_function_profile_requests.py --limit 500 --output data/parent_analysis/function_profile_run_001/function_profile_requests.jsonl`

Run that batch with results persisted to
`data/parent_analysis/function_profile_run_001/function_profile_responses.jsonl`; the spend ledger is written
automatically to `data/parent_analysis/function_profile_run_001/function_profile_responses.jsonl.attempts.jsonl`:

`python src/gemini_flash_harness.py data/parent_analysis/function_profile_run_001/function_profile_requests.jsonl data/parent_analysis/function_profile_run_001/function_profile_responses.jsonl --execute --confirm-network --thinking-off --google-search`

Google Search is an explicit opt-in. It may provide contextual background, but the prompt
prohibits reconstructing `[AUTHORITY]` spans; grounding metadata and citations are retained
in the response log for review.

Every network attempt is also written before submission to a sidecar attempt log named
`<responses>.attempts.jsonl` by default. It contains the exact submitted prompt, metadata,
model, search setting, timestamp, and outcome. If a process dies or the API returns an
ambiguous transport error, the request is treated as spent/unknown and is not retried on
the next run. This sidecar is the spend tracker: completed requests are never submitted
again, and unknown outcomes are held back by default. Keep the same response and
attempt-log paths for resumed runs. Use `--retry-unknown` only after checking the attempt
log and accepting the risk of duplicate billing.

Transient 429 and retryable 5xx responses are recorded as unknown outcomes and are not
retried. The harness applies an exponential cooldown and continues with the next pending
request; non-transient errors remain fail-fast. Configure the cooldown with
`--transient-backoff-seconds` and `--transient-backoff-max-seconds` when needed.

Validate responses locally before using them in retrieval:

`python src/validate_function_profiles.py data/parent_analysis/function_profile_responses.jsonl --documents data/parent_analysis_full/directive_similarity_documents.jsonl --segments data/parent_analysis_full/directive_operative_segments.jsonl --profiles data/parent_analysis/function_profiles.jsonl --errors data/parent_analysis/function_profile_errors.jsonl`

Consolidate completed run directories into the durable validated-profile cache and status
inventory (this also rewrites each run's derived validation outputs, never its raw logs):

`python src/consolidate_function_profiles.py data/parent_analysis/function_profile_run_001`

Request generation excludes IDs in both the durable cache and the legacy consumed-ID list
by default. Use repeated `--consumed-ids` arguments only when explicitly selecting other
registries.

Build the deduplicated candidate-parent batch for the 500 run-001 children without making
network calls:

`python src/build_candidate_function_profile_batch.py`

The builder writes requests, a unique-parent status inventory, child candidate coverage,
and a manifest under `data/parent_analysis/function_profile_candidate_run_001/`. It
excludes validated profiles, all previously saved responses, and legacy consumed IDs.

Build the complete network-free execution plan for the 7,011 eligible unresolved children
and their candidate parents:

`python src/build_full_function_profile_plan.py`

The full plan is written under `data/parent_analysis/function_profile_full_plan/` with a
master status inventory and non-overlapping 500-request checkpoints. The earlier
500-child candidate batch is superseded by this plan and must not be executed separately.

Function extraction does not make parent judgments. After parent edges are fixed, authority
divergence can be computed with `src/authority_divergence.py`.

Build the local source-versus-Flash comparison viewer:

`python src/build_function_profile_viewer.py --profiles data/parent_analysis/function_profile_pilot/function_profiles.jsonl --responses data/parent_analysis/function_profile_pilot/function_profile_responses.jsonl --errors data/parent_analysis/function_profile_pilot/function_profile_errors.jsonl`

The viewer is authority-masked and shows the original directive, highlighted model evidence,
policy functions, operative functions by segment, raw validated JSON, and audit warnings.
## Function-profile parent pilot

The incremental pilot is built under `data/parent_analysis/function_parent_pilot/provisional`.
It freezes a validated profile snapshot, samples 50 development children (20 trade
proclamations and 10 each of executive orders, memoranda, and letters), retrieves one
shared 25-parent pool from separate policy, operative, BM25, and text-reuse channels,
and ranks that identical pool with deterministic function alignment, local Qwen, and a
single joint Gemini request per child. Every output carries the snapshot hash and the
review page is visibly marked provisional until profile recovery finishes.

Run the stages in order:

```bash
.venv-parent-analysis/bin/python src/build_function_profile_snapshot.py
.venv-parent-analysis/bin/python src/build_function_parent_pilot_sample.py
.venv-parent-analysis/bin/python src/embed_function_profiles.py
.venv-parent-analysis/bin/python src/build_function_candidate_pool.py
.venv-parent-analysis/bin/python src/rank_function_candidate_pool.py deterministic
.venv-parent-analysis/bin/python src/rank_function_candidate_pool.py qwen
.venv-parent-analysis/bin/python src/build_gemini_function_rank_requests.py
```

The August 13 provisional run is complete at snapshot
`06814d11698b99009f85353628070bab614029779d434db73421ae9d15e2b087`: 8,219 validated
profiles, 46,760 function embeddings, 50 sampled children, and 1,250 pairs ranked fully
by each method. Gemini used `gemini-3.6-flash`, thinking off, and Google Search on; retain
the grounding metadata and label this method `gemini_search`. The other methods are
deterministic one-to-one function alignment (`0.30 policy + 0.70 operative`) and local
Qwen profile judgments (`0.20 policy + 0.50 operative + 0.30 joint`).

The three methods agree on the winner for 10/50 children. Qwen and Gemini agree on 23/50,
deterministic and Qwen on 14/50, and deterministic and Gemini on 11/50. The blinded page
contains only the union of unique method winners and hides their provenance:

`data/parent_analysis/function_parent_pilot/provisional/blind_top_candidate_review.html`

Next, complete blinded human review, compare method top-1 accuracy by stratum, benchmark
RRF versus channel-reserved retrieval and the document-embedding ablation, then regenerate
everything from a final snapshot after Flash recovery. Do not combine artifacts whose
snapshot hashes differ. Full decisions, validation normalizations, and remaining work are
documented in `data/parent_analysis/FUNCTION_PROFILE_PARENT_PIPELINE.md`.
