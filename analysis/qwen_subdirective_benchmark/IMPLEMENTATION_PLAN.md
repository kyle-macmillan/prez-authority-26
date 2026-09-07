# Qwen Round 2 sub-directive benchmark

## Objective

Measure `qwen3.8:27b-32k` on finalized Round 2 sub-directive labels.  The
benchmark uses each directive's complete Gemini Flash profile as context and
asks Qwen to classify one explicitly marked target segment at a time.

## Inputs and alignment

- Gold source: `data/Annotations/Round 2/round-2-finalized-validation-labels-with-subdirectives.json` from commit `df5ab70`.
- Profile source: `data/parent_analysis/canonical_profiles/profiles.jsonl`.
- Target unit: a finalized W&P chunk, represented by every Flash operative
  function with the matching normalized `segment_id`.
- Eligible benchmark: 172 aligned targets across 62 directives.  Twenty-four
  gold chunks without a Flash target and three unmatched Flash segments are
  excluded and listed in the manifest.
- Prompt content: condensed Codes 0–4 codebook, full same-directive Flash
  profile with evidence text and offsets removed, and an explicit target group.
  Gold labels and raw gold chunk text never enter prompts.

## Execution

- Model: Tigerteam Ollama `qwen3.8:27b-32k`.
- Three thinking-enabled runs with seeds `20260819`, `20260820`, and
  `20260821`; installed sampling defaults are pinned in the run manifest.
- Output is strict JSON containing a code and short rationale.  Raw final text,
  thinking trace, timings, attempts, and validation status are cached.
- The cache key is target, seed, model, and prompt hash, making interrupted
  runs resumable without repeating completed calls.

## Monitoring and reporting

- The runner updates an atomic `status.json` heartbeat and append-only
  `events.jsonl` after every state change.
- `status --watch` displays completion, per-seed progress, current request,
  throughput, ETA, most recent result/error, and stale-run state.
- Evaluation reports seed-level and consensus accuracy, macro/weighted F1,
  per-class metrics, confusion matrices, agreement, directive-balanced
  accuracy, clustered bootstrap intervals, and a detailed error table.

## Validation gates

1. Preparation must produce exactly 172 aligned requests and prove prompts do
   not contain labels, gold chunk text, or removed evidence fields.
2. A one-target Tigerteam smoke run must return a valid structured response.
3. Full evaluation runs only after every target/seed result is terminal.
