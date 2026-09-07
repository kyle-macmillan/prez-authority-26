# GPT-5.6 Sol / Codex pilot (scaffold only)

This directory is a reproducible, isolated comparison of GPT-5.6 Sol with the
manually reviewed 20-child EO pilot.  It deliberately references the frozen
v2 inputs rather than copying or modifying them:

```
data/parent_analysis/function_parent_pilot/eo_pilot_20_v2/gemini_rank_v2_requests.jsonl
data/parent_analysis/function_parent_pilot/eo_pilot_20_v2/function-parent-review-06814d11698b.json
```

The acceptance phase must be generated from Sol's validated rank-one choices;
the Gemini acceptance requests cannot be reused because Sol may select a
different candidate.

Nothing in this directory has been executed.  The runner is intentionally
blocked unless passed `--execute`.

## Planned protocol

1. Run the 20 frozen ranking prompts independently, one `codex exec` process
   per request, with `gpt-5.6-sol`, `xhigh` reasoning, read-only sandboxing,
   and the ranking schema.
2. Retain each Codex JSON event log and reject a run containing a tool call.
3. Validate complete rankings against the frozen candidate pools.
4. Generate 20 fresh candidate-or-none prompts from Sol's rank-one choices.
5. Run and validate those acceptance judgments.
6. Evaluate the resulting decisions against the frozen manual review.

## Commands to run later

All commands below are documentation only; do not run them until the pilot is
approved.  Run from the repository root.

```bash
# Phase 1: execute isolated ranking calls.
python3 analysis/child-parent-model-research/codex_gpt56_sol_pilot/run_codex_pilot.py \
  --phase ranking --execute

# Reject ranks generated with any tool activity, then normalize/validate them.
python3 analysis/child-parent-model-research/codex_gpt56_sol_pilot/verify_event_logs.py \
  analysis/child-parent-model-research/codex_gpt56_sol_pilot/logs/ranking
python3 src/validate_gemini_function_rankings.py \
  --snapshot-dir data/parent_analysis/function_parent_pilot/eo_pilot_20_v2 \
  --candidates data/parent_analysis/function_parent_pilot/eo_pilot_20_v2/candidate_pool.csv \
  --responses analysis/child-parent-model-research/codex_gpt56_sol_pilot/outputs/ranking_responses.jsonl \
  --method codex_gpt56_sol --output-prefix codex_gpt56_sol

# Phase 2 input: make fresh acceptance requests using Sol's rank-one results.
python3 src/build_function_parent_acceptance_requests.py \
  --snapshot-dir data/parent_analysis/function_parent_pilot/eo_pilot_20_v2 \
  --profiles data/parent_analysis/function_parent_pilot/eo_pilot_20_v2/profiles.jsonl \
  --rankings data/parent_analysis/function_parent_pilot/eo_pilot_20_v2/codex_gpt56_sol_rankings.jsonl \
  --method codex_gpt56_sol --run-label eo20-codex-gpt56-sol-xhigh-v1 \
  --output analysis/child-parent-model-research/codex_gpt56_sol_pilot/outputs/acceptance_requests.jsonl
python3 analysis/child-parent-model-research/codex_gpt56_sol_pilot/run_codex_pilot.py \
  --phase acceptance --execute

# Validate acceptance, then compare with the manual review.
python3 analysis/child-parent-model-research/codex_gpt56_sol_pilot/verify_event_logs.py \
  analysis/child-parent-model-research/codex_gpt56_sol_pilot/logs/acceptance
python3 src/validate_function_parent_acceptance.py \
  analysis/child-parent-model-research/codex_gpt56_sol_pilot/outputs/acceptance_responses.jsonl \
  --snapshot-dir data/parent_analysis/function_parent_pilot/eo_pilot_20_v2 \
  --output analysis/child-parent-model-research/codex_gpt56_sol_pilot/outputs/decisions.jsonl \
  --errors analysis/child-parent-model-research/codex_gpt56_sol_pilot/outputs/acceptance_errors.jsonl
python3 analysis/child-parent-model-research/codex_gpt56_sol_pilot/evaluate_against_review.py \
  --review data/parent_analysis/function_parent_pilot/eo_pilot_20_v2/function-parent-review-06814d11698b.json \
  --decisions analysis/child-parent-model-research/codex_gpt56_sol_pilot/outputs/decisions.jsonl \
  --output analysis/child-parent-model-research/codex_gpt56_sol_pilot/outputs/evaluation.json
```

The generic validator filenames retain their historic `gemini` names but do
not call Gemini; their `--method` and input paths make the produced records
unambiguously Sol/Codex records.

The runner prepends a short no-tools instruction to every frozen prompt. This
resolves the legacy acceptance prompt's optional Search language and makes the
tool-log rejection criterion enforceable.
