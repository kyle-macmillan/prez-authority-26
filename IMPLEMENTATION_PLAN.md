# Implementation Plan: Presidential-Directive Parent Analysis

## 1. Objective

This project studies when a presidential directive invokes legal authority that differs
from the authority invoked by its most relevant earlier precedent.

The immediate task is to construct and validate a parent graph for all 16,397 directives
in `data/4_28_2026_build_dev.csv`: 3,620 executive orders, 2,806 memoranda,
6,691 proclamations, and 3,280 letters.

- A **child** is the later directive being evaluated.
- A **parent** is an earlier directive of the same document type with a qualifying
  relationship to the child.
- Formal relationships and text-similarity relationships are identified in separate
  stages.
- A directive may have more than one parent.
- A directive may have no parent and therefore remain an **orphan**.

The analysis includes executive orders, memoranda, proclamations, and letters. Other
presidential-document types are outside the initial scope. Parent-child pairs must be
within the same document type; cross-document-type parents are not permitted.

Parent status means that an earlier same-type directive is a useful drafting precedent.
It does not prove that the drafter actually consulted or copied it.

## 1.1 Implementation status — July 31, 2026

Implementation has resumed on an NVIDIA GeForce RTX 2080 Ti with 11,264 MiB of memory.
The locked local environment and pinned Qwen snapshot are installed. GPU smoke tests and
full dual-role embedding generation and candidate ranking are complete for all four
directive types. The generated results remain provisional until the cross-type reference
extraction, masking, segmentation, and retrieval outputs receive manual validation.

### Completed

- Revised `segment_ordering()` so the extended Woolley and Peters matcher applies to all
  documents regardless of formal section headings.
- Removed the section-priority branch from the W&P path.
- Added regression tests for extended matching in structured and unstructured documents.
- Implemented automatic extraction of references to earlier EOs.
- Implemented relation labels for amendments, revocations, supersessions, modifications,
  continuations, replacements, delegations of authority under an earlier EO, and general
  citations/discussions.
- Implemented chronological eligibility, including same-day ordering by EO number.
- Identified seven duplicate-number UCSB URLs that omit an official `-A` suffix and added a
  derived correction map without altering the source CSV:
  `11359-A`, `10695-A`, `10571-A`, `10417-A`, `10026-A`, `9973-A`, and `9934-A`.
- Generated automatic-edge and unresolved-child artifacts.
- Implemented initial authority-span masking across the complete EO text.
- Implemented initial removal of severability clauses and recurring general-provisions
  limitation language.
- Added tests showing that connectors remain visible, internal references such as
  `section 2 of this order` are retained, and findings and definitions remain.
- Generated stable cleaned-document and operative-segment JSONL artifacts.
- Pinned the embedding pipeline dependencies to exact versions compatible with the
  CUDA 12.5-era host driver.
- Compiled `requirements-parent-analysis.lock.txt` with all transitive dependencies for
  reproducible installation.
- Installed the locked dependencies into `.venv-parent-analysis`.
- Downloaded `Qwen/Qwen3-Embedding-0.6B` at exact revision
  `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` into the project-local cache.
- Verified PyTorch 2.6.0+cu124 can access the RTX 2080 Ti.
- Verified both retrieval instructions on the RTX 2080 Ti.
- Audited all model inputs against Qwen's 32,768-token limit; the maxima are 13,806 tokens
  for instructed full-document queries and 12,921 for instructed operative-segment
  queries, with no overlength input.
- Generated normalized 1,024-dimensional embeddings for 3,620 full documents and 14,309
  operative segments. Each item has an instructed child-query embedding and an unprompted
  candidate-parent embedding.
- Cached both embedding matrices with stable identifiers, source hashes, model and
  tokenizer revisions, package versions, instructions, token-length summaries, and
  runtime provenance.
- Extended the complete artifact and embedding pipeline to all 16,397 directives.
- Retrieved up to 25 strictly earlier same-type candidates for 14,291 unresolved
  children, producing 356,100 candidate pairs; four earliest directives have no eligible
  same-type predecessor.
- Implemented and retained separate case-sensitive BM25, case-sensitive corpus-wide word
  3-gram TF-IDF, 10-word-minimum text-reuse, and top-three operative-embedding rankings.
- Fused the four rankings with unweighted RRF using `k=20` and selected up to 10
  candidates per child.
- Drew a reproducible, holdout-excluding pilot sample of 50 unresolved children per
  directive type (200 children total).
- Built a blinded interactive masked-document viewer containing 1,994 candidate
  comparisons, highlighted operative-segment alignments, persistent judgments, and JSON
  export.

### Current generated results

The current all-directive build contains:

- 16,397 directives;
- 5,020 automatic parent edges across 2,102 children;
- 14,295 unresolved children eligible for Stage B: 1,978 executive orders,
  2,764 memoranda, 6,279 proclamations, and 3,274 letters;
- 5,099 unresolved or non-parent references retained for audit;
- 356,100 embedding-gated candidate pairs; and
- 356,100 fully ranked candidate pairs with an RRF top-10 flag.

Generated artifacts are written under `data/parent_analysis/`. Small audit tables and
embedding provenance may be committed. Large, reproducible JSONL, embedding, candidate-
pool, and ranked-candidate artifacts are ignored by Git and must be transferred through
external artifact storage when they need to be shared. Large source datasets are handled
the same way; their expected local paths remain stable so the pipeline commands do not
change.

### Validation still required for completed components

The code above is implemented and its automated tests pass, but the following outputs
remain provisional pending manual audit:

- recall of EO-reference extraction, especially plural or list-form references;
- accuracy of relation labels when one paragraph mentions several earlier EOs;
- accuracy and completeness of document-wide authority masking across all four types;
- over-masking by named-Act patterns;
- removal of recurring limitation language without removing EO-specific provisions;
- the quality and granularity of the generalized operative segments;
- treatment of directives producing no operative segment; and
- quality of the 356,100-pair candidate ranking, including tie behavior and the
  top-three segment-pair aggregation.

### Not yet completed

- Collect parent-or-none judgments and explanations.
- Estimate and qualitatively assess orphanhood.
- Specify or run the later authority-divergence analysis.

### Legally operative path-dependency comparison pilot

A separate 50-child comparison pilot is implemented under `src/path_dependency/`. It
uses the codebook's Code 3 definition, two codebook-grounded Qwen classification prompts,
the existing conservative self-executing rules, and the existing Round 2 majority labels
for automated validation. It changes child selection only: candidate generation and
ranking remain identical to the original random pilot. Its outputs are isolated under
`data/parent_analysis/path_dependency_pilot/operative/`.

The classifier and viewer generator are complete, and the pinned model snapshot is stored
in the ignored project cache. GPU inference and validation selected the conservative rule
policy (precision 0.857 and recall 0.300 on the Round 2 majority labels). The resulting
50-child sample and 500-comparison viewer are materialized under
`data/parent_analysis/path_dependency_pilot/operative/`; the sample has no overlap with
the original pilot or the holdout set.

### Current resume point

Resume at section 13, step 7 by conducting the 200-child blinded pilot review in
`data/parent_analysis/pilot/parent_candidate_viewer.html`. Generalized artifacts,
embeddings, the 356,100-pair embedding gate, and all within-pool scores and ranks are
stored in `data/parent_analysis/`.

## 2. Parent definition

### 2.1 Similarity-based parents

For relationships not established by an explicit reference to an earlier same-type
directive, two forms of similarity are necessary:

1. **Substantive-policy similarity**: the earlier directive addresses the same substantive
   policy problem.
2. **Operative-mechanism similarity**: the earlier directive uses a similar legal command,
   directed operative action, or legal or administrative mechanism.

The third form of evidence is supplementary:

3. **Language or structural similarity**: the earlier directive supplies reusable language,
   organization, or drafting architecture.

Language or structural similarity may increase the similarity score, but it is not
sufficient by itself. This limitation is important because presidential directives
contain recurring
boilerplate.

The final similarity thresholds and weights are not yet specified. They will be informed
by the pilot review rather than assumed in advance.

### 2.2 Level of evidence

One highly similar operative segment may be sufficient to establish a document-level
parent relationship. A parent does not need to support a minimum proportion of the child
directive.

Substantive-policy similarity may be established from the full documents while a
particular segment pair supplies the operative-mechanism evidence. Both forms of evidence
do not have to be concentrated in the same segment pair.

### 2.3 Explicit-reference parents

An explicit reference to an earlier same-type directive automatically creates a parent
edge. This includes both general citations or discussions of that directive and formal
actions such as:

- amends;
- revokes;
- supersedes;
- modifies;
- continues;
- replaces; or
- delegates authority under.

The edge must record the action taken when one can be identified. A general citation or
discussion receives a distinct citation/discussion label. A continuing-program
determination is not required.

A directive with at least one automatic parent edge will not proceed through similarity
retrieval for additional uncited parents in the initial specification. A reference to a
different document type may be recorded as a cross-type relationship, but it does not
create a parent edge or remove the child from Stage B.

## 3. Ordered identification process

Parent identification has two ordered branches.

### 3.1 Stage A: explicit relationships using unmasked text

Use the original, unmasked directive text to:

1. identify every explicit reference to an earlier presidential directive;
2. resolve the referenced directive to the corpus and identify its document type;
3. identify any accompanying relationship language; and
4. create an automatic, labeled parent edge only when the referenced directive has the
   same document type as the child.

This stage may use the vesting clause and all other portions of the document. It occurs
before authority masking because directive references appearing in legal-authority language
must remain available for relationship extraction.

### 3.2 Stage B: similarity relationships for unresolved directives

An **unresolved directive** is a child with no same-type automatic edge from Stage A.

Only unresolved directives enter the similarity pipeline:

1. Create cleaned, authority-masked representations.
2. Use full-document embeddings to retrieve up to 25 closest earlier directives of the
   child's document type. Use all eligible earlier same-type directives when fewer than
   25 exist.
3. Within those 25, independently rank candidates using operative-segment embeddings,
   lexical similarity, n-grams, and text reuse.
4. Combine those rankings using unweighted Reciprocal Rank Fusion (RRF).
5. Retain up to 10 candidates for manual review. Use every candidate in the embedding
   pool when fewer than 10 exist.

The non-embedding approaches operate only within the embedding pool of up to 25 in the
initial specification. They do not introduce candidates that failed the embedding gate.

Only earlier directives of the same document type are eligible parents. No temporal
window is imposed.

## 4. Authority masking and preprocessing

### 4.1 Separation between parent identification and authority analysis

Unmasked text is permitted only for Stage A explicit-relationship extraction.

For Stage B similarity retrieval and manual review, cited legal authority is an outcome
that must not influence parent selection. The similarity representations must therefore
mask all cited legal authorities, including:

- references to earlier presidential directives;
- constitutional provisions or roles;
- statutes and U.S.C. provisions;
- Public Laws;
- named Acts; and
- other identifiable legal-authority citations.

Authority information must be stored separately from retrieval features. Authority
comparison begins only after parent identification is fixed.

### 4.2 Preprocessing shared by all similarity channels

The same cleaned, authority-masked source text will define the input for embeddings,
lexical retrieval, n-grams, and text-reuse detection.

Remove:

- severability clauses; and
- recurring general-provisions limitation language, such as standard language concerning
  agency authority, implementation consistent with law and appropriations, enforceable
  rights, and publication.

Do not remove an entire section merely because it is titled `General Provisions`.
Directive-specific operative material must remain.

Retain:

- findings and policy-purpose material;
- definitions, including program-specific definitions;
- non-directive preambles; and
- all other substantive text.

The preprocessing implementation must be tested on representative documents of all four
directive types before retrieval is run. Rules for identifying authority spans and
recurring limitation language remain an implementation task; this plan does not assume
that the current rules already satisfy these requirements.

## 5. Segmentation and text representations

### 5.1 Operative segmentation

Use the extended Woolley and Peters ordering-phrase approach throughout. Do not switch to
formal-section segmentation when section headings are present, and do not use formal
section boundaries as the primary segmentation rule.

Extended ordering phrases define the operative-action segments used for
operative-mechanism comparison.

### 5.2 Full-document policy representation

Non-directive text—including findings, purposes, definitions, and preambles—remains
available in the cleaned full-document representation used for substantive-policy
similarity.

The pipeline therefore retains two linked representations:

1. **Cleaned full-document text** for the initial policy-and-action embedding gate.
2. **Extended W&P operative segments** for detailed operative-mechanism comparison.

Every directive and operative segment must receive a stable identifier that includes or
joins to its document type so candidate edges can be traced to their supporting text and
same-type eligibility can be enforced.

## 6. Embedding model and instructions

Use the open-weight `Qwen/Qwen3-Embedding-0.6B` model locally for the initial pilot.

- Use the full 1,024-dimensional output.
- Cache embeddings and preprocessing metadata.
- Record the exact model revision, tokenizer revision, package versions, instruction,
  preprocessing version, and creation date.
- Check token counts explicitly and do not silently truncate overlength inputs.

Use this instruction for cleaned full-document embeddings:

> Represent this presidential directive for identifying earlier directives of the same
> document type that address the same substantive policy problem and contain a similar
> legal directive or directed operative action.

Use this instruction for operative-segment embeddings:

> Represent this directed operative action for identifying earlier actions in directives
> of the same document type that use a similar legal or administrative mechanism.

The human-labeled pilot will evaluate whether the model and instructions retrieve useful
parents. Generic embedding benchmarks alone are not validation for this task.

## 7. Candidate-ranking channels

The four within-pool rankings remain separate and inspectable before fusion.

### 7.1 Operative-segment embeddings

Compare the child's extended W&P operative segments with the candidate's operative
segments using the segment-specific Qwen instruction. Preserve the strongest supporting
segment alignments rather than only a document-level average.

Rank candidates by the mean of the three strongest child-parent segment-pair cosine
similarities, or all available pairs when fewer than three exist. Preserve those
alignments for review.

### 7.2 Lexical similarity

Use case-sensitive BM25 over the complete cleaned, authority-masked text with `k1=1.5`
and `b=0.75`. This channel should capture shared policy vocabulary, institutional names,
affected groups, and operative terms.

### 7.3 N-gram similarity

Use case-sensitive word 3-gram TF-IDF cosine similarity, with IDF calculated across the
full directive corpus so common drafting phrases are discounted.

### 7.4 Text reuse

Measure sustained local copying using exact matching passages of at least 10 words.
Rank candidates by the total number of unique child words covered by qualifying passages,
without double-counting overlapping passages. This includes:

- verbatim passages;
- small substitutions;
- reordered provisions; and
- reused passages embedded in longer segments.

Text reuse is evidence that may boost a candidate but cannot independently establish a
similarity-based parent.

### 7.5 Rank fusion

Use unweighted Reciprocal Rank Fusion with `k=20` to combine the four rankings within each
child's pool of up to 25 candidates. Retain every raw score, rank, and channel contribution
in the candidate dataset.

Use the fused rank to select up to 10 candidates shown in manual review.

## 8. Manual pilot

### 8.1 Sample

After Stage A is complete for all four document types, take a separate reproducible random
sample of 50 unresolved children from each directive type: 50 executive orders,
50 memoranda, 50 proclamations, and 50 letters, for 200 children total.

For each sampled child, manually review up to 10 candidates selected by RRF, producing no
more than 2,000 candidate comparisons in total. If fewer than 10 eligible earlier
same-type candidates exist, review all available candidates.

The random seed and sampling frame must be recorded. Reserved holdout documents must not
be used to tune preprocessing or retrieval rules.

### 8.2 Reviewer presentation

Build an interactive viewer in which the reviewer can move through every sampled child
and analyze each of its available candidate parents, up to 10. For every child and
candidate, show:

- the complete cleaned directive text;
- document type, title, date, and type-specific identifier when available;
- proposed operative-segment matches highlighted; and
- enough visible structure to understand the document.

The viewer must also:

- make the child and current candidate easy to compare;
- provide navigation among all available candidates for the child, up to 10;
- support recording `parent` or `not parent` for each candidate;
- support a child-level `none` judgment when no candidate qualifies;
- capture a short explanation for the final parent-or-none decision;
- preserve multiple qualifying parents when the reviewer identifies them; and
- save judgments with stable child, candidate, and segment identifiers.

Do not show:

- the vesting clause;
- cited legal-authority text;
- extracted authority outcomes; or
- a model-generated parent conclusion.

Candidate order should not expose the fused ranking.

### 8.3 Reviewer decision

For each child, the reviewer should:

- identify the qualifying parent or parents from the available candidates; or
- select `none` and explain why none qualifies.

Do not require separate numerical grades for policy and mechanism in the initial pilot.
Record a short explanation for the decision.

If multiple candidates qualify, the reviewer should generally select the most recent
qualifying parent. Multiple parents may be retained when different earlier directives
meaningfully support different operative segments; the explanation must identify that
exception.

## 9. Pilot evaluation

The pilot should evaluate the complete candidate-generation process rather than assume
that a highly ranked candidate is a parent.

At minimum, report:

- the share of sampled children with a qualifying parent in the reviewed candidate set;
- the share classified as orphans;
- the fused rank of selected parents;
- which channels ranked the selected parent highly;
- cases in which operative-segment evidence altered the full-document embedding order;
- false positives caused by generic language;
- candidates sharing a policy but lacking a similar operative mechanism;
- candidates sharing a mechanism but lacking the same policy problem; and
- apparent retrieval failures where none of the available candidates is adequate.

The pilot cannot by itself distinguish a genuinely novel orphan from a child whose true
parent fell outside the embedding pool of up to 25. Qualitative orphan review is therefore
required.

## 10. Orphan analysis

Orphanhood is a substantive outcome, not an error to be eliminated by forcing every child
to have a parent.

After the method is validated and applied more broadly:

- estimate the percentage of directives with no identified parent, overall and by
  document type;
- examine orphan rates over time and across relevant groupings; and
- qualitatively review orphan directives.

The qualitative review should distinguish, as far as possible:

- genuine policy or operative novelty;
- left-censoring from the corpus start date;
- failure of the embedding gate of up to 25 candidates;
- failure of within-pool ranking; and
- masking or preprocessing errors.

An absolute parent threshold may be developed later. The initial pilot uses manual
parent-or-none judgments rather than an assumed automated threshold.

## 11. Graph representation

Store the result as a directed graph with typed edges. The edge table should contain at
least:

| Field | Description |
|---|---|
| `child_id` | Corpus identifier for the later directive |
| `parent_id` | Corpus identifier for the earlier same-type directive |
| `document_type` | Shared document type of the child and parent |
| `child_date` | Date of the child |
| `parent_date` | Date of the parent |
| `temporal_distance` | Time between parent and child |
| `edge_source` | Automatic reference or similarity review |
| `formal_relation` | Amend, revoke, supersede, modify, continue, replace, delegate under, citation/discussion, or null |
| `child_segment_ids` | Supporting child operative segments |
| `parent_segment_ids` | Supporting parent operative segments |
| `retrieval_ranks` | Rank from each similarity channel |
| `retrieval_scores` | Raw score from each similarity channel |
| `rrf_rank` | Fused within-pool rank |
| `review_decision` | Parent, not parent, none available, or not reviewed |
| `review_explanation` | Short reviewer rationale |
| `evidence` | Masked supporting excerpts or references |

Keep authority outcomes in a separate table joined by directive identifier only after
parent identification is fixed.

## 12. Authority-divergence analysis

The eventual substantive outcome is divergence whenever the child invokes a different
legal authority from its parent or parents.

After the graph is fixed, extract and normalize exact legal authorities and compare each
child with its parent set. At minimum, record:

- authorities retained;
- authorities added;
- authorities removed;
- authorities substituted; and
- whether any authority divergence occurred.

The exact divergence summaries and statistical models will be specified after the
parent-identification pilot. They are not needed to run the initial retrieval test and
must not affect parent selection.

## 13. Immediate implementation sequence

1. **Revise operative segmentation**
   - Make the extended W&P approach independent of formal section boundaries.
   - Preserve full-document non-directive text for policy comparison.
   - Add regression tests before regenerating segments.

2. **Extract automatic directive-reference edges**
   - Work from unmasked text.
   - Resolve every earlier presidential-directive reference and its document type.
   - Label formal actions and general citations/discussions.
   - Create parent edges only for same-type references; retain cross-type references
     separately without treating them as parents.

3. **Create Stage B preprocessing**
   - Mask all cited legal authorities.
   - remove severability and recurring limitation language;
   - retain findings and definitions; and
   - verify masking and removal with tests and a manual sample.

4. **Create stable document and segment artifacts**
   - Store cleaned full-document text and extended W&P operative segments.
   - Record document types, identifiers, and preprocessing provenance.

5. **Install and validate Qwen locally**
   - [x] Pin dependency revisions and compile a transitive lockfile.
   - [x] Record the available GPU model, memory, and driver.
   - [x] Create the project-local environment from the lockfile.
   - [x] Download and record exact model and tokenizer revision
     `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`.
   - [x] Re-run the small smoke test with both agreed instructions.
   - [x] Check input lengths and runtime.
   - [x] Cache dual-role document and operative-segment embeddings for executive orders.
   - [x] Generate generalized-instruction caches for all four document types, including
     regenerated executive-order caches.
   - [ ] Manually validate the generalized caches and representative retrieval results.

6. **Run candidate generation**
   - [x] Retrieve up to 25 earlier same-type directives with full-document embeddings, using
     all eligible candidates when fewer than 25 exist.
   - [x] Compute the four within-pool rankings.
   - [x] Fuse them with unweighted RRF (`k=20`) and select up to 10.

7. **Build the 200-child pilot and viewer**
   - [x] Draw a reproducible random sample of 50 unresolved children from each of the four
     directive types.
   - [x] Build the interactive masked-document viewer.
   - [x] For every sampled child, present up to 10 same-type candidates with highlighted
     operative-segment matches, or every available candidate if fewer than 10 exist.
   - [ ] Collect candidate-level parent/not-parent judgments, child-level `none` judgments,
     multiple-parent selections, and explanations.

8. **Evaluate and revise**
   - Assess parent retrieval and orphan cases.
   - Decide whether to change the model, instructions, pool size of up to 25, channel
     definitions, fusion rule, or eventual absolute threshold.

## 14. Decisions deliberately deferred

The following choices remain open until inspection or pilot evidence supports them:

- the exact authority-span masking rules;
- the exact recurring-limitation boilerplate rules;
- any weights replacing unweighted RRF;
- an absolute embedding candidate threshold;
- an automated parent/no-parent threshold;
- whether to compare Qwen with another embedding model;
- the scale and reliability design of later manual annotation;
- the final authority-divergence statistics.

## 15. Initial acceptance criteria

The initial pilot is complete when:

- explicit same-type directive-reference edges are reproducibly extracted and labeled;
- cross-type directive references are retained separately and never treated as parent
  edges;
- Stage B contains only directives with no same-type automatic parent edge;
- all authority citations are masked from every Stage B retrieval and review input;
- recurring severability and limitation boilerplate is removed without discarding
  directive-specific operative material;
- extended W&P operative segments are generated regardless of formal sections;
- Qwen embeddings are reproducible and cached with complete provenance;
- every unresolved directive can produce a same-type embedding pool of up to 25 and a
  fused list of up to 10, using all eligible candidates when fewer exist;
- the same four within-pool channels can be inspected independently;
- the viewer exposes masked full text and highlighted operative-segment matches for every
  sampled child and each of its available candidates, up to 10;
- 50 randomly sampled unresolved children per directive type (200 total) receive recorded
  candidate-level and child-level manual parent-or-none review;
- selected parents and exceptions are explained;
- orphan frequency in the pilot is reported; and
- orphan cases receive qualitative error analysis before any corpus-wide conclusion.
