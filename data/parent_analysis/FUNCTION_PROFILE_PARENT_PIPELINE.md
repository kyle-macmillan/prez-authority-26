# Function-profile parent-identification plan

## Objective

Identify a single best plausible parent for each unresolved presidential directive while
preserving the evidence needed to audit every retrieval, model, and human-review decision.
An inferred relationship is a `plausible_precedent`; functional similarity alone is not
proof of literal drafting dependence.

## Pipeline

1. **Create automatic edges from explicit references.** Resolve unambiguous references
   to earlier directives and retain ambiguous, cross-type, outside-corpus, and non-earlier
   references separately for audit.

2. **Freeze a validated profile snapshot.** Overlay recovery responses on the original
   batch responses, validate them, and hash the resulting document/profile pairs. Every
   downstream artifact carries this hash. Profiles with no policy or operative functions
   remain valid corpus assets but are ineligible as pilot children because none of the
   function-ranking methods can compare them.

3. **Retrieve one shared pool of 25 strictly earlier candidates.** Use separate channels
   for policy-function semantic similarity, operative-function semantic similarity,
   operative-text BM25, and distinctive 10-token text reuse. Fuse channel ranks with RRF
   (`k=60`). Flash evidence excerpts are excluded from semantic embeddings; lexical
   reuse operates on source operative segments. Whole-document semantic similarity is
   not in the adopted pool because the profiles supply the semantic distillation and the
   lexical channels retain drafting reuse.

4. **Rank the identical pool with three methods.** The pilot compares:

   - deterministic maximum-weight one-to-one function alignment, with unmatched child
     functions scoring zero and `0.30 policy + 0.70 operative`;
   - local Qwen3-Reranker-0.6B judgments for policy, operative, and joint profile match,
     combined as `0.20 policy + 0.50 operative + 0.30 joint`;
   - one Gemini 3.6 Flash joint ranking of all 25 candidates per child. Google Search is
     enabled because the practical objective is best-candidate identification, not a
     controlled profile-only model comparison. This method must therefore be labeled
     `gemini_search`, and grounding metadata must remain auditable.

5. **Blind-review the unique method winners.** Show each child and the union of the three
   top-ranked candidates, shuffle their presentation deterministically, and hide method
   identity. The reviewer records `parent`, `not_parent`, or `none_available`, plus an
   explanation. Review judgments become the pilot ground truth for choosing a production
   method; functional similarity by itself is never saved as proof of literal dependence.

## Durable Flash-profile tracking

Flash profiles are corpus assets and must never depend on a transient run directory or
an overwritten request file.

- Use the stable request ID `function-profile-v1:<document_id>`.
- Write raw responses to an append-only JSONL response log.
- Write submission and outcome records to an append-only attempt/spend ledger before and
  after every network call.
- Validate raw responses locally and write accepted profiles to a durable JSONL profile
  cache keyed by `document_id` and `prompt_version`.
- Keep validation failures in a separate error log; do not mark them as usable profiles.
- Treat submitted requests with no confirmed response as unknown outcomes and do not
  retry them automatically.
- Before building or executing a run, subtract IDs already present in the validated
  profile cache. Also inspect raw completed responses that have not yet been validated so
  they are validated rather than resubmitted.
- Reject duplicate document IDs or conflicting profiles during cache consolidation.
- Preserve the request, raw response, usage metadata, validation status, model settings,
  prompt version, and run identifier so every profile can be traced to its source call.
- Resume with the same response and attempt-log paths. Never overwrite a completed run.

The validated cache, rather than a manually maintained consumed-ID list, should become
the authoritative source for deciding whether a directive still needs profiling. A
generated inventory should report requested, submitted, completed, unknown, invalid,
validated, and missing IDs for every run.

## Evaluation before production ranking

Use reviewed relationships and/or held-out automatic edges to compare methods on the same
top-25 pools. Candidate generation is evaluated separately from ranking: compare RRF with
channel-reserved fusion using Recall@25, then Recall@10, then MRR; add whole-document
embeddings only if their ablation improves Recall@25. On the frozen pool, select the
ranking method primarily by blinded top-1 accuracy. Rank-sensitive metrics are secondary
when the reviewed parent is present below rank 1. Human review remains final even after a
production method is selected.

## Provisional pilot completed (August 13, 2026)

- Snapshot `06814d11698b99009f85353628070bab614029779d434db73421ae9d15e2b087`
  contains 8,219 validated profiles and 517 invalid responses. It includes 284 recovery
  responses and is deliberately marked provisional.
- The fixed development sample has 50 unresolved children: 20 trade proclamations and 10
  each of executive orders, memoranda, and letters. It excludes 2,271 holdout or previously
  reviewed IDs and excludes zero-function profiles.
- Qwen3-Embedding-0.6B produced 46,760 function embeddings at a 512-token maximum. The
  shared RRF candidate pool contains 1,250 pairs: 25 candidates for every child.
- Deterministic, Qwen, and Gemini-with-Search each produced complete ranks 1–25 for all 50
  children. Gemini required one retry. Validation performed only narrow mechanical repairs:
  removing an erroneously added child ID, sorting by the model's emitted scores, and
  removing the stray word in `policy_score: 0.75 revenue` from the retry JSON.
- Winner agreement before human review: all three methods agree for 10 children; 18 have
  two unique winners; and 22 have three unique winners. Pairwise top-1 agreement is 14/50
  deterministic–Qwen, 11/50 deterministic–Gemini, and 23/50 Qwen–Gemini.
- The provisional blinded unique-winner review is
  `function_parent_pilot/provisional/blind_top_candidate_review.html` and is committed as
  `23ef645`.

## Work remaining

1. Complete the blinded human review and save structured decisions and explanations.
2. Score top-1 accuracy by method and directive stratum; inspect Search grounding where it
   influenced Gemini's winner. Decide whether a single method, consensus rule, or a staged
   method should be used in production.
3. Benchmark RRF against channel-reserved fusion on eligible known edges and run the
   whole-document-embedding ablation before changing the adopted candidate pool.
4. After Flash recovery is complete, build a new final snapshot and rerun sampling,
   embeddings, retrieval, all rankers, and the viewer. Never merge provisional and final
   rankings across snapshot hashes.
5. After method selection, implement the durable reviewed-edge output with matched
   function IDs, evidence, scores, model/version, reviewer, and decision provenance.
