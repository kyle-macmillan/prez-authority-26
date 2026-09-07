# VC boilerplate classification

This directory measures what presidential directives citing only generic constitutional
and generic statutory authority actually do. It contains two frozen, deterministic
Codebook 0–4 classifiers and evaluates them against the finalized 139-document Round 2
ground truth.

The first classifier reads directive text. The second reads only the structured fields
of the existing canonical Gemini 3.6 Flash function profiles. It deliberately excludes
profile `evidence`, offsets, confidence, raw directive text, document type, date,
president, title, and URL. No model is called by this analysis. A missing profile is an
explicit `P0_NO_PROFILE` state rather than a text fallback.

## Design

The seeded split contains 46 development and 93 validation documents. It is stratified
by gold code and document type for partition balance, but document type is never a
predictor. The sole Code 4 and one of two Code 2 records are in development; the other
Code 2 is in validation. The exact allocation and seed are recorded in
`outputs/manifest.json`.

Rules were developed from the development partition, ordered and frozen in `build.py`,
and then run once on validation. Validation errors are reported without being used to
revise the rules. See `RULES.md` for the decision-list overview and `RESULTS.md` for the
findings.

The rules are deliberately verb-led rather than example-led. Active predicates carry
the primary signal: review, study, report, coordinate, and recommend point toward Code 1;
require, issue, rescind, condition, and terminate point toward Code 2 when paired with a
specific later legal object; and waive, block, suspend, designate, prohibit, and set point
toward Code 3 when the directive itself supplies the trigger. Objects and conditions are
used to resolve the Code 1/2/3 boundary, not to memorize particular policy subjects or
presidential eras.

The final population is recomputed from the current repository logic: both source
corpora are filtered by the existing ceremonial exclusion, vesting clauses are extracted,
and only `generic_constitution_and_generic_statute` directives are retained. This is
slower than reading the older generic-authority audit, but it reproduces the current
1,369-document population.

## Reproduce

From the repository root:

```bash
python3 analysis/vc-boilerplate/build.py build
python3 analysis/vc-boilerplate/test_build.py
```

A full build takes roughly 40–50 seconds because it recomputes vesting categories over
the complete development-plus-holdout corpus. The implementation uses only the Python
standard library and repository modules.

## GPT-5.6 Sol sub-directive benchmark

The separate `sol_subdirective_benchmark.py` experiment evaluates one independent,
schema-constrained `gpt-5.6-sol` / low-reasoning Codex CLI call per finalized operative
sub-directive. It uses the document-disjoint development/validation split (91 targets
from 40 documents and 198 targets from 80 documents), supplies the
full directive as context, and scores only the explicitly marked target chunk. It invokes
the locally installed `codex exec`; it does not use an OpenAI API client or API key.
Built-in web search is permitted for genuine legal ambiguities, while shell, filesystem,
MCP, computer-use, and other tools are rejected from the recorded run.

```bash
python3 analysis/vc-boilerplate/sol_subdirective_benchmark.py prepare
python3 analysis/vc-boilerplate/sol_subdirective_benchmark.py run-dev --smoke
python3 analysis/vc-boilerplate/sol_subdirective_benchmark.py run-dev
python3 analysis/vc-boilerplate/sol_subdirective_benchmark.py freeze-validation
python3 analysis/vc-boilerplate/sol_subdirective_benchmark.py run-validation
python3 analysis/vc-boilerplate/sol_subdirective_benchmark.py evaluate
```

For the full nonceremonial generic-authority executive-order population, the scaled
runner makes one Codex call per EO and returns one independent classification for every
operative segment in that EO:

```bash
python3 analysis/vc-boilerplate/sol_eo_population.py prepare
python3 analysis/vc-boilerplate/sol_eo_population.py run --smoke
python3 analysis/vc-boilerplate/sol_eo_population.py run
python3 analysis/vc-boilerplate/sol_eo_population.py evaluate
```

The identical protocol for nonceremonial generic-authority presidential memoranda uses
one local Codex call per memorandum and audits memoranda with no detected operative segment:

```bash
python3 analysis/vc-boilerplate/sol_memo_population.py prepare
python3 analysis/vc-boilerplate/sol_memo_population.py run --smoke
python3 analysis/vc-boilerplate/sol_memo_population.py run
python3 analysis/vc-boilerplate/sol_memo_population.py evaluate
```

The remaining vague-authority document types use the same frozen population prompt and
protocol:

```bash
python3 analysis/vc-boilerplate/sol_proclamation_population.py prepare
python3 analysis/vc-boilerplate/sol_proclamation_population.py run
python3 analysis/vc-boilerplate/sol_proclamation_population.py evaluate
python3 analysis/vc-boilerplate/sol_letter_population.py prepare
python3 analysis/vc-boilerplate/sol_letter_population.py run
python3 analysis/vc-boilerplate/sol_letter_population.py evaluate
```

### Context-instruction A/B experiment

`sol_context_ablation.py` preserves the original frozen validation artifacts and makes
fresh paired calls on the 198 held-out sub-directives. The v2 condition adds an explicit
statement that verb-led segmentation can detach a target from relevant context and that
the full directive should be used to interpret—but not replace—the target action. Gold
labels are not loaded until both conditions are complete.

```bash
python3 analysis/vc-boilerplate/sol_context_ablation.py prepare
python3 analysis/vc-boilerplate/sol_context_ablation.py run
python3 analysis/vc-boilerplate/sol_context_ablation.py evaluate
```

## Outputs

- `dev_split.csv` and `validation_blind.csv`: the frozen partition manifests.
- `dev_predictions.csv` and `validation_predictions.csv`: gold labels, predictions,
  fired rules, rationales, and evidence used by each classifier.
- `validation_errors.csv`: validation mistakes and cross-classifier disagreements.
- `metrics.json`: accuracy, majority baseline, supported-class macro-F1, per-class
  metrics, and confusion matrices.
- `target_classifications.csv`: both predictions for every target directive.
- `target_disagreements.csv`: the target directives on which the classifiers differ.
- `content_summary.csv`: overall and document-type code distributions.
- `representative_directives.csv`: five deterministic examples per available code and
  classifier.
- `manifest.json`: input hashes, rule hash, counts, profile coverage, and forbidden
  predictors.

The finalized gold source is tracked at
`data/Annotations/Round 2/round-2-finalized-validation-labels-with-subdirectives.json`.
Its expected SHA-256 is
`d3eb11f4a88b321a6c2bb8e816ca6786a89a7c8c6267177ccc41704f90dac8a7`.

## Limits

The validation set has no Code 4 example and only one Code 2 example. Overall accuracy
therefore mostly reflects Codes 0, 1, and 3. Flash profiles are static model-generated
upstream artifacts, so the rules over those files are deterministic but the upstream
profile-generation process was not. The output classifications are measurements from
transparent rules, not replacement human annotations.
