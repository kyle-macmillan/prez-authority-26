# Session handoff: Qwen Round 2 sub-directive benchmark

Continue implementing and executing the Qwen benchmark in
`/home/kyle/Projects/prez-authority-26/analysis/qwen_subdirective_benchmark/`.
Keep all new code, run state, reports, and results in that directory.

## User goal

Test the Qwen model running on Tigerteam for classification under the
presidential-directive codebook.  Qwen should receive a condensed codebook and
the complete Gemini Flash profile for a directive, then classify one explicitly
marked operative-function group at a time.  Thinking must be enabled.  Web
search is deferred.  The user also wants live, resumable progress monitoring.

## Locked design decisions

- Tigerteam model: `qwen3.8:27b-32k` through Ollama; installed ID
  `a6643404c0cd`; Ollama was `0.32.14` when inspected.
- Three seeded runs using installed sampling defaults (temperature 1, top-p
  0.95, top-k 20) and seeds `20260819`, `20260820`, `20260821`.
- Include Code 4.  Prompt uses a condensed Code 0–4 codebook.
- Input is the complete same-directive Flash profile.  Remove every `evidence`,
  `evidence_start`, and `evidence_end` field.  Do not send raw directives,
  raw chunks, or annotation labels.
- Target is the group of all Flash `operative_functions` sharing a normalized
  `segment_id`, not each finer function individually.  This matches the human
  W&P chunk as closely as possible.
- Consensus is majority vote; a three-way tie uses numerical median and is
  flagged unstable.

## Gold and profile sources

The local worktree is behind the pushed annotation commit and is dirty.  Do not
blindly pull, reset, or overwrite it.  A read-only temporary clone exists at:

`/tmp/prez-authority-plan-df5ab70`

It contains commit `df5ab70e9547e835aca0ab27c36468975b2f60f6`, including the
authoritative gold file:

`data/Annotations/Round 2/round-2-finalized-validation-labels-with-subdirectives.json`

The local Flash profile source is:

`data/parent_analysis/canonical_profiles/profiles.jsonl`

The new gold export has 289 labels across 120 directives.  The current profile
snapshot aligns directly to 172 gold chunks across 62 directives:

- Code 0: 9
- Code 1: 116
- Code 2: 7
- Code 3: 37
- Code 4: 3

Exclude and report 24 gold chunks without a corresponding Flash operative
function, three Flash segments with no gold chunk, and the two directives with
no aligned target.  Do not revive the earlier directive-level aggregation plan;
the sub-directive labels now allow direct metrics.

## What is already done

- Verified the schema and alignment counts above.
- Verified `ssh tigerteam` access and that Ollama served the requested model.
- Created this directory with `IMPLEMENTATION_PLAN.md`, `WORK_STATUS.md`, and
  this handoff file.

## What remains

1. Implement a self-contained Python CLI in this directory with `prepare`,
   `run`, `status`, and `evaluate` commands.
2. `prepare` must write blind requests and separate gold mapping, assert 172
   targets, and redact all evidence/labels/text from prompts.
3. `run` must use an SSH tunnel to Tigerteam's local Ollama endpoint,
   set `think: true`, preserve response/thinking/timing data, cache by target
   and seed, and write atomic `status.json` plus append-only `events.jsonl`.
4. `status --watch` must show total/per-seed completion, current request,
   latency, ETA, latest success/error, and stale state.
5. Add tests and run one smoke target before the full 172 × 3 = 516 calls.
6. Evaluate each seed and consensus: accuracy, balanced accuracy, macro/weighted
   F1, per-class metrics, confusion matrices, agreement, directive-balanced
   accuracy, clustered bootstrap CIs, and an error table.
7. Update `WORK_STATUS.md` after each completed milestone and deliver the final
   report from the directory.

## Copy-paste prompt

> Continue the Qwen Round 2 sub-directive benchmark described in `analysis/qwen_subdirective_benchmark/HANDOFF.md`. Implement the self-contained prepare/run/status/evaluate workflow in that directory, preserve the dirty worktree, use the authoritative gold file from `/tmp/prez-authority-plan-df5ab70` until the local checkout is safely updated, run the Tigerteam smoke test and then the full 516-call benchmark, monitor it via the status command, evaluate the results, and update `WORK_STATUS.md` as milestones complete.
