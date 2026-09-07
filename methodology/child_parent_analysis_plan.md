# Child–Parent Directive Method

**Status:** living methodology and run record, updated August 16, 2026. The
relationship inferred here is a `plausible_precedent`: evidence that an earlier
directive could have supplied useful substantive drafting material for a later one. It is
not proof that the later drafter consulted, copied, or intended to follow the earlier
directive.

The detailed execution/provenance record is
`data/parent_analysis/FUNCTION_PROFILE_PARENT_PIPELINE.md`. This document states the
current method, population transitions, completed runs, and interpretation rules in one
place.

## 1. Corpus and eligibility

The parent-analysis corpus contains 20,232 unique directives across executive orders,
memoranda, proclamations, and letters. The segmentation/vesting holdout is retained for
that separate task, but both physical corpus partitions are in scope for parent analysis.

The successive eligibility filters were:

| Stage | Directives | Rule |
|---|---:|---|
| Source corpus | 20,232 | Unique directives in the combined corpus |
| Non-ceremonial analytic corpus | 13,461 | Exclude 6,771 codebook-defined ceremonial documents |
| Unresolved children | 10,581 | Exclude 2,880 children with an automatic same-type parent edge from an explicit reference |
| Flash/profile-retrieval eligible children | 7,036 | Exclude 3,446 without a canonical operative profile, 75 without function embeddings, and 24 with fewer than 25 earlier profiled directives |

The explicit-reference stage generated 7,523 edge records for 2,880 unique children. A
child with at least one qualifying edge was resolved by that stage and did not enter
similarity retrieval. Ambiguous, cross-type, outside-corpus, and non-earlier references
are retained for audit rather than silently treated as parent edges.

Candidate parents must be strictly earlier than the child. Same-day documents are
excluded because chronological drafting order is not observable reliably. In the current
function-profile retrieval, any earlier profiled directive can be a candidate parent;
document type is recorded but is not a retrieval requirement.

## 2. Authority-blind source preparation

Before similarity, profile extraction, retrieval, reranking, or review, the pipeline:

1. preserves unmasked text only long enough to resolve explicit directive references;
2. removes the complete vesting clause and masks residual authority citations;
3. creates stable operative-action segments from the masked text; and
4. keeps the original authority spans separately for the later authority-divergence study.

Parent inference therefore cannot be driven by a shared legal-authority citation. Parent
judgments and the later authority analysis remain separate until the graph is frozen.

## 3. Flash function profiles

Gemini Flash receives an authority-masked full directive and its operative segments. It
does **not** decide parenthood. Instead, it produces an auditable profile containing:

- zero or more **policy functions**, representing the directive's specific policy purpose;
- zero or more **operative functions**, representing a directed legal or administrative
  action and linked to its operative segment; and
- for each function: actor, action, target, mechanism, effect, condition, timing,
  exact evidence, offsets, and confidence.

Profiles are locally validated: the schema must be valid; IDs and segment links must be
valid; and evidence must be present in the supplied masked source text. Accepted profiles
are retained in an append-only, versioned canonical cache. Every downstream artifact
records its frozen profile-snapshot hash. Flash evidence excerpts are audit evidence, not
embedding input.

## 4. Candidate-pair retrieval

Each policy and operative function is embedded with Qwen3-Embedding-0.6B. Policy and
operative functions use different retrieval instructions, respectively targeting the
same specific policy problem and a materially similar legal or administrative mechanism.

For each unresolved child, all strictly earlier profiled directives are ranked in four
independent channels:

1. policy-function semantic similarity;
2. operative-function semantic similarity;
3. BM25 over the original operative segments; and
4. exact reuse of 10-word operative-text shingles.

For either semantic channel, every child function receives the cosine similarity of its
best matching parent function; those per-child-function maxima are averaged to produce
the document-pair score. The lexical channels operate on source operative text. The four
channel ranks are fused using unweighted Reciprocal Rank Fusion with `k = 60`, and the
top 25 fused candidates are retained. All raw scores, channel ranks, fusion ranks, and
snapshot provenance remain in the candidate-pool artifact.

Being in the top 25 is only a retrieval result. It is not a parent finding.

## 5. Post-retrieval parent decision

For each child, Gemini 3.6 Flash jointly reranks its frozen 25-candidate pool. The model
must return every candidate exactly once, in descending overall score, along with policy
and operative scores, a reason, and supporting function IDs.

The top-ranked candidate is then evaluated in a separate **candidate-or-none** call. The
model asks whether a drafter could have reused concrete language, organization, legal
machinery, institutional pathway, or sequence of actions from the earlier directive. It
recognizes three possible relationship scopes:

1. whole-document parent;
2. structural-framework parent; or
3. material-provision parent.

Generic topical overlap, common actors, boilerplate, ordinary executive-order form, and
routine administrative clauses are insufficient. A `candidate` requires a self-reported
plausibility score of at least 0.50; a lower score is `none`. `None` means the rank-1
candidate was not plausible, not that no possible parent exists outside the reviewed pool.

Gemini outputs are provisional model judgments. A final parent edge requires blinded human
review or another expressly documented validation rule.

## 6. Completed pilots

### Second EO-only pilot

The second pilot used 20 executive orders with no overlap with the original pilot. Both
thinking-off and thinking-medium Gemini variants used the same frozen snapshot, the same
top-25 retrieval procedure, and the drafter-centered v2 prompts. All 1,000 ranking rows
and all 40 acceptance calls validated.

The variants chose the same rank-1 candidate for 17 of 20 children and agreed on the
candidate-or-none decision for 15 of 20. Thinking-off accepted 15 children; thinking
medium accepted 10.

The blinded review export dated August 16, 2026 judged 13 children to have a plausible
parent among the displayed winners and 7 to have none. Against that review, the
thinking-off model agreed on the parent/not-parent decision in 16 of 20 cases:

| Thinking-off versus reviewer | Cases |
|---|---:|
| Both: plausible parent | 12 |
| Both: no plausible parent | 4 |
| Model parent; reviewer none | 3 |
| Reviewer parent; model none | 1 |

Thinking-medium was more conservative and slightly more aligned with the review: 17/20
parent/not-parent agreement and 16/20 exact outcome agreement, compared with 16/20 and
15/20 for thinking-off. These results are small-sample pilot evidence, not a final method
selection.

## 7. Completed all-directives Gemini run

The completed non-thinking Gemini work comprises two non-overlapping batches drawn from
the 7,036-child eligible population: an initial 1,000-child batch and the next 1,500
children.

| Stage | Count | Rate of 2,500 targeted children |
|---|---:|---:|
| Targeted children | 2,500 | 100.0% |
| Valid complete 25-candidate rankings | 2,439 | 97.6% |
| Valid rank-1 acceptance decisions | 2,436 | 97.4% |

Of the 2,436 completed acceptance decisions, Gemini returned 1,808 `candidate` decisions
(74.2%) and 628 `none` decisions (25.8%). The mean acceptance score was 0.656 and the
median was 0.82. These numbers describe model output, not confirmed parent edges.

| Directive type | Completed decisions | Candidate | None |
|---|---:|---:|---:|
| Executive order | 661 | 499 | 162 |
| Letter | 521 | 352 | 169 |
| Memorandum | 920 | 700 | 220 |
| Proclamation | 334 | 257 | 77 |
| **Total** | **2,436** | **1,808** | **628** |

The initial 1,000-child batch completed without validation errors. In the next 1,500,
61 rankings failed validation (52 omitted or duplicated a frozen candidate; 9 were
malformed or schema-invalid). Of the 1,439 valid rerankings, three acceptance responses
omitted the required best-candidate ID. These failures are retained in error logs and are
not counted as decisions.

## 8. Provenance and current limitations

- The all-directives run uses an incomplete canonical snapshot and is provisional. It
  must not be merged with a final snapshot or presented as a finalized parent graph.
- Profile requests, raw responses, validation outcomes, attempt logs, prompts, model
  settings, response IDs, and snapshot hashes are retained so every profile and decision
  can be traced.
- Candidate generation, relative ranking, absolute acceptance, and human review are
  reported separately. Good ranking does not establish a parent relationship.
- Before production-edge release: complete profile recovery; rebuild the final snapshot;
  rerun retrieval/ranking under that snapshot; and perform the specified blinded review
  and method evaluation.

## 9. Primary artifacts

- Eligibility, references, and operative segments:
  `data/parent_analysis_all_corpus/`
- Canonical profiles and snapshot metadata:
  `data/parent_analysis/canonical_profiles/`
- Full function-profile pipeline record:
  `data/parent_analysis/FUNCTION_PROFILE_PARENT_PIPELINE.md`
- Second EO pilot and blinded review export:
  `data/parent_analysis/function_parent_pilot/eo_pilot_20_v2/`
- Completed 1,000-child run:
  `data/parent_analysis/gemini_flash_no_thinking_all_directives_1000/`
- Completed next-1,500-child run:
  `data/parent_analysis/gemini_flash_no_thinking_all_directives_next_1500/`
