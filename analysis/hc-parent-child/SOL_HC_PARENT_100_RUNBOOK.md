# Sol HC parent-identification runbook

## Purpose

This frozen package asks `gpt-5.6-sol` to identify a plausible drafting parent, or abstain,
for 100 fresh HC directives: 20 uniquely assigned to each of the five HC categories. All
children are scoped, lack a resolved explicit parent link, have an operative Flash profile,
and were excluded from prior HC metric and parent-review samples.

Each blinded request contains the child's cleaned text and function profile plus 25 shuffled
candidates. The pool preserves the deduplicated union of the top five candidates from
five-word reuse, ten-word reuse, BM25, and operative-function similarity, plus the two most
recent same-family predecessors. Remaining slots are filled with the next-best candidates
under reciprocal-rank fusion across the four retrieval channels, using
`sum(1 / (60 + channel_rank))`. Requests hide category,
document IDs, retrieval sources, scores, and ranks. Vesting clauses and generic boilerplate
are absent, and directive-number references are masked.

Sol ranks the three strongest displayed candidates and then either accepts the first-ranked
candidate as a plausible parent, returns `none`, or returns `uncertain`. These decisions are
silver labels. They allow comparison of objective retrieval metrics against a consistent
model judgment, but are not independent ground truth.

## Prerequisites on the run machine

- A copy of this repository including `analysis/hc-parent-child/outputs/sol_hc_parent_100/`.
- An authenticated `codex` CLI available on `PATH`.
- Python 3.10 or newer. The runner itself uses only the standard library.

The runner pins `gpt-5.6-sol` with `model_reasoning_effort="low"`, ignores user/project
instructions, uses an ephemeral session and read-only sandbox, and enforces the response
schema. It does not enable web search.

## Validate and inspect without running a model

```bash
python3 analysis/hc-parent-child/validate_sol_hc_parent_100.py
python3 analysis/hc-parent-child/run_sol_hc_parent_100.py --dry-run --limit 2
```

## Run one smoke-test case

```bash
python3 analysis/hc-parent-child/run_sol_hc_parent_100.py \
  --case-id SHC001
```

Inspect:

- `analysis/hc-parent-child/outputs/sol_hc_parent_100/responses/SHC001.json`
- `analysis/hc-parent-child/outputs/sol_hc_parent_100/logs/SHC001.events.jsonl`
- `analysis/hc-parent-child/outputs/sol_hc_parent_100/logs/SHC001.stderr.txt`
- `analysis/hc-parent-child/outputs/sol_hc_parent_100/attempts.jsonl`

## Run or resume all 100

```bash
python3 analysis/hc-parent-child/run_sol_hc_parent_100.py
```

Completed, valid responses are skipped automatically. If the process stops, rerun the same
command. An invalid existing response causes a stop for inspection; use `--force` only to
replace that case deliberately. Use `--limit N` for a partial run.

## Compile results

```bash
python3 analysis/hc-parent-child/score_sol_hc_parent_100.py --require-complete
```

This writes:

- `sol_parent_selections.csv`: one decision per child, with hidden IDs and metric ranks
  restored for analysis;
- `sol_top3_rankings.csv`: Sol's three strongest candidates per child, with hidden IDs and
  metric ranks restored;
- `metric_retrieval_summary.csv`: Recall@1/5/10/25 and MRR for each objective metric among
  Sol-accepted parents; and
- `decision_summary_by_family.csv`: candidate/none/uncertain counts by assigned HC family.

Do not expose `sampled_children.csv`, `candidate_pool_key.csv`, or `manifest.json` to the
model during the run. The runner reads only the already-blinded request files.
