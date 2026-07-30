# Implementation Plan: Executive-Order Parent Analysis

## 1. Objective

This project studies when an executive order (EO) invokes legal authority that differs
from the authority invoked by its most relevant earlier precedent.

The immediate task is to construct and validate a parent graph for the 3,620 EOs in
`data/4_28_2026_build_dev.csv`.

- A **child** is the later EO being evaluated.
- A **parent** is an earlier EO with a qualifying relationship to the child.
- Formal relationships and text-similarity relationships are identified in separate
  stages.
- An EO may have more than one parent.
- An EO may have no parent and therefore remain an **orphan**.

The initial analysis is limited to executive orders. Memoranda, proclamations, letters,
and other presidential documents are outside the initial scope.

Parent status means that an earlier EO is a useful drafting precedent. It does not prove
that the drafter actually consulted or copied it.

## 1.1 Implementation status — July 30, 2026

Implementation is paused before model download and embedding generation while GPU
provisioning is considered.

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
- Added a project-local dependency specification for the embedding pipeline.

### Current generated results

The current development-corpus build contains:

- 3,620 EOs;
- 3,658 automatic parent edges;
- 1,642 children with at least one automatic parent;
- 1,978 unresolved children eligible for Stage B;
- 1,702 references that do not resolve to an earlier EO in the available corpus; and
- 14,309 extended-W&P operative segments.

Generated artifacts are stored in `data/parent_analysis/`:

- `automatic_edges.csv`;
- `unresolved_references.csv`;
- `unresolved_children.csv`;
- `eo_similarity_documents.jsonl`; and
- `eo_operative_segments.jsonl`.

### Validation still required for completed components

The code above is implemented and its automated tests pass, but the following outputs
remain provisional pending manual audit:

- recall of EO-reference extraction, especially plural or list-form references;
- accuracy of relation labels when one paragraph mentions several earlier EOs;
- accuracy and completeness of document-wide authority masking;
- over-masking by named-Act patterns;
- removal of recurring limitation language without removing EO-specific provisions;
- the quality and granularity of the 14,309 operative segments; and
- treatment of the 36 EOs currently producing no operative segment.

### Not yet completed

- Install the local embedding environment.
- Download and pin `Qwen/Qwen3-Embedding-0.6B`.
- Run representative GPU runtime and memory smoke tests.
- Generate full-document and operative-segment embeddings.
- Retrieve the top 25 earlier EOs for each unresolved child.
- Implement the within-pool BM25, n-gram, text-reuse, and operative-embedding rankings.
- Implement unweighted Reciprocal Rank Fusion and select the top 10 candidates.
- Draw the reproducible random sample of 50 unresolved children.
- Build the masked manual-review viewer with highlighted operative segments.
- Collect parent-or-none judgments and explanations.
- Estimate and qualitatively assess orphanhood.
- Specify or run the later authority-divergence analysis.

### Resume point after GPU provisioning

Resume at section 13, step 5. First record the GPU model and available memory, create the
project-local environment from `requirements-parent-analysis.txt`, download the pinned
Qwen revision, and run a small benchmark before generating the full embedding artifacts.

## 2. Parent definition

### 2.1 Similarity-based parents

For relationships not established by an explicit reference to an earlier EO, two forms
of similarity are necessary:

1. **Substantive-policy similarity**: the earlier EO addresses the same substantive
   policy problem.
2. **Operative-mechanism similarity**: the earlier EO uses a similar legal directive,
   directed operative action, or legal or administrative mechanism.

The third form of evidence is supplementary:

3. **Language or structural similarity**: the earlier EO supplies reusable language,
   organization, or drafting architecture.

Language or structural similarity may increase the similarity score, but it is not
sufficient by itself. This limitation is important because EOs contain recurring
boilerplate.

The final similarity thresholds and weights are not yet specified. They will be informed
by the pilot review rather than assumed in advance.

### 2.2 Level of evidence

One highly similar operative segment may be sufficient to establish a document-level
parent relationship. A parent does not need to support a minimum proportion of the child
EO.

Substantive-policy similarity may be established from the full documents while a
particular segment pair supplies the operative-mechanism evidence. Both forms of evidence
do not have to be concentrated in the same segment pair.

### 2.3 Explicit-reference parents

An explicit reference to an earlier EO automatically creates a parent edge. This includes
both general citations or discussions of an earlier EO and formal actions such as:

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

An EO with at least one automatic parent edge will not proceed through similarity
retrieval for additional uncited parents in the initial specification.

## 3. Ordered identification process

Parent identification has two ordered branches.

### 3.1 Stage A: explicit relationships using unmasked text

Use the original, unmasked EO text to:

1. identify every explicit reference to an earlier EO;
2. resolve the referenced EO to the corpus;
3. identify any accompanying relationship language; and
4. create an automatic, labeled parent edge.

This stage may use the vesting clause and all other portions of the document. It occurs
before authority masking because EO references appearing in legal-authority language
must remain available for relationship extraction.

### 3.2 Stage B: similarity relationships for unresolved EOs

An **unresolved EO** is a child with no automatic edge from Stage A.

Only unresolved EOs enter the similarity pipeline:

1. Create cleaned, authority-masked representations.
2. Use full-document embeddings to retrieve the 25 closest earlier EOs.
3. Within those 25, independently rank candidates using operative-segment embeddings,
   lexical similarity, n-grams, and text reuse.
4. Combine those rankings using unweighted Reciprocal Rank Fusion (RRF).
5. Retain the top 10 candidates for manual review.

The non-embedding approaches operate only within the top-25 embedding pool in the initial
specification. They do not introduce candidates that failed the embedding gate.

Only earlier EOs are eligible parents. No temporal window is imposed.

## 4. Authority masking and preprocessing

### 4.1 Separation between parent identification and authority analysis

Unmasked text is permitted only for Stage A explicit-relationship extraction.

For Stage B similarity retrieval and manual review, cited legal authority is an outcome
that must not influence parent selection. The similarity representations must therefore
mask all cited legal authorities, including:

- references to earlier executive orders;
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
EO-specific operative material must remain.

Retain:

- findings and policy-purpose material;
- definitions, including program-specific definitions;
- non-directive preambles; and
- all other substantive text.

The preprocessing implementation must be tested on representative EOs before retrieval
is run. Rules for identifying authority spans and recurring limitation language remain an
implementation task; this plan does not assume that the current rules already satisfy
these requirements.

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

Every EO and operative segment must receive a stable identifier so candidate edges can be
traced to their supporting text.

## 6. Embedding model and instructions

Use the open-weight `Qwen/Qwen3-Embedding-0.6B` model locally for the initial pilot.

- Use the full 1,024-dimensional output.
- Cache embeddings and preprocessing metadata.
- Record the exact model revision, tokenizer revision, package versions, instruction,
  preprocessing version, and creation date.
- Check token counts explicitly and do not silently truncate overlength inputs.

Use this instruction for cleaned full-document embeddings:

> Represent this executive order for identifying earlier executive orders that address
> the same substantive policy problem and contain a similar legal directive or directed
> operative action.

Use this instruction for operative-segment embeddings:

> Represent this directed operative action for identifying earlier executive-order
> actions that use a similar legal or administrative mechanism.

The human-labeled pilot will evaluate whether the model and instructions retrieve useful
parents. Generic embedding benchmarks alone are not validation for this task.

## 7. Candidate-ranking channels

The four within-pool rankings remain separate and inspectable before fusion.

### 7.1 Operative-segment embeddings

Compare the child's extended W&P operative segments with the candidate's operative
segments using the segment-specific Qwen instruction. Preserve the strongest supporting
segment alignments rather than only a document-level average.

The exact rule for aggregating multiple segment-pair scores remains to be selected after
inspection of pilot examples.

### 7.2 Lexical similarity

Use a transparent lexical retrieval method such as BM25 over the cleaned, authority-masked
text. This channel should capture shared policy vocabulary, institutional names, affected
groups, and operative terms.

### 7.3 N-gram similarity

Compare word or character n-grams to capture local phrase overlap. Common n-grams must be
discounted so generic EO drafting language does not dominate the ranking.

The exact n-gram representation and commonness threshold remain to be tested.

### 7.4 Text reuse

Measure sustained local copying or light revision, including:

- verbatim passages;
- small substitutions;
- reordered provisions; and
- reused passages embedded in longer segments.

Text reuse is evidence that may boost a candidate but cannot independently establish a
similarity-based parent.

### 7.5 Rank fusion

Use unweighted Reciprocal Rank Fusion to combine the four rankings within each child's
25-candidate pool. Retain every raw score, rank, and channel contribution in the candidate
dataset.

Use the fused rank to select the 10 candidates shown in manual review.

## 8. Manual pilot

### 8.1 Sample

After Stage A is complete, take a reproducible random sample of 50 unresolved child EOs.

For each sampled child, manually review the 10 candidates selected by RRF, producing 500
candidate comparisons in total.

The random seed and sampling frame must be recorded. Reserved holdout documents must not
be used to tune preprocessing or retrieval rules.

### 8.2 Reviewer presentation

For every child and candidate, show:

- the complete cleaned EO text;
- title, date, and EO number;
- proposed operative-segment matches highlighted; and
- enough visible structure to understand the document.

Do not show:

- the vesting clause;
- cited legal-authority text;
- extracted authority outcomes; or
- a model-generated parent conclusion.

Candidate order should not expose the fused ranking.

### 8.3 Reviewer decision

For each child, the reviewer should:

- identify the qualifying parent from the 10 candidates; or
- select `none` and explain why none qualifies.

Do not require separate numerical grades for policy and mechanism in the initial pilot.
Record a short explanation for the decision.

If multiple candidates qualify, the reviewer should generally select the most recent
qualifying parent. Multiple parents may be retained when different earlier EOs
meaningfully support different operative segments; the explanation must identify that
exception.

## 9. Pilot evaluation

The pilot should evaluate the complete candidate-generation process rather than assume
that a highly ranked candidate is a parent.

At minimum, report:

- the share of sampled children with a qualifying parent in the reviewed top 10;
- the share classified as orphans;
- the fused rank of selected parents;
- which channels ranked the selected parent highly;
- cases in which operative-segment evidence altered the full-document embedding order;
- false positives caused by generic language;
- candidates sharing a policy but lacking a similar operative mechanism;
- candidates sharing a mechanism but lacking the same policy problem; and
- apparent retrieval failures where none of the 10 candidates is adequate.

The pilot cannot by itself distinguish a genuinely novel orphan from a child whose true
parent fell outside the embedding top 25. Qualitative orphan review is therefore required.

## 10. Orphan analysis

Orphanhood is a substantive outcome, not an error to be eliminated by forcing every child
to have a parent.

After the method is validated and applied more broadly:

- estimate the percentage of EOs with no identified parent;
- examine orphan rates over time and across relevant groupings; and
- qualitatively review orphan EOs.

The qualitative review should distinguish, as far as possible:

- genuine policy or operative novelty;
- left-censoring from the corpus start date;
- failure of the embedding top-25 gate;
- failure of within-pool ranking; and
- masking or preprocessing errors.

An absolute parent threshold may be developed later. The initial pilot uses manual
parent-or-none judgments rather than an assumed automated threshold.

## 11. Graph representation

Store the result as a directed graph with typed edges. The edge table should contain at
least:

| Field | Description |
|---|---|
| `child_id` | Corpus identifier for the later EO |
| `parent_id` | Corpus identifier for the earlier EO |
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

Keep authority outcomes in a separate table joined by EO identifier only after parent
identification is fixed.

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

2. **Extract automatic EO-reference edges**
   - Work from unmasked text.
   - Resolve every earlier EO reference.
   - Label formal actions and general citations/discussions.

3. **Create Stage B preprocessing**
   - Mask all cited legal authorities.
   - remove severability and recurring limitation language;
   - retain findings and definitions; and
   - verify masking and removal with tests and a manual sample.

4. **Create stable document and segment artifacts**
   - Store cleaned full-document text and extended W&P operative segments.
   - Record identifiers and preprocessing provenance.

5. **Install and validate Qwen locally**
   - Pin the model and dependency revisions.
   - run a small smoke test with both agreed instructions;
   - check input lengths and runtime; and
   - cache embeddings.

6. **Run candidate generation**
   - Retrieve the top 25 earlier EOs with full-document embeddings.
   - Compute the four within-pool rankings.
   - Fuse them with unweighted RRF and select 10.

7. **Build the 50-child pilot**
   - Draw the reproducible random sample from unresolved EOs.
   - Build the masked review interface.
   - Collect parent-or-none judgments and explanations.

8. **Evaluate and revise**
   - Assess parent retrieval and orphan cases.
   - Decide whether to change the model, instructions, top-25 pool, channel definitions,
     fusion rule, or eventual absolute threshold.

## 14. Decisions deliberately deferred

The following choices remain open until inspection or pilot evidence supports them:

- the exact authority-span masking rules;
- the exact recurring-limitation boilerplate rules;
- aggregation of multiple operative-segment similarities;
- the BM25 field definition;
- word versus character n-grams and their sizes;
- the text-reuse alignment method;
- any weights replacing unweighted RRF;
- an absolute embedding candidate threshold;
- an automated parent/no-parent threshold;
- whether to compare Qwen with another embedding model;
- the scale and reliability design of later manual annotation; and
- the final authority-divergence statistics.

## 15. Initial acceptance criteria

The initial pilot is complete when:

- explicit EO-reference edges are reproducibly extracted and labeled;
- Stage B contains only EOs with no automatic parent edge;
- all authority citations are masked from every Stage B retrieval and review input;
- recurring severability and limitation boilerplate is removed without discarding
  EO-specific operative material;
- extended W&P operative segments are generated regardless of formal sections;
- Qwen embeddings are reproducible and cached with complete provenance;
- every unresolved EO can produce a top-25 embedding pool and fused top-10 list;
- the same four within-pool channels can be inspected independently;
- 50 randomly sampled unresolved children receive manual parent-or-none review;
- selected parents and exceptions are explained;
- orphan frequency in the pilot is reported; and
- orphan cases receive qualitative error analysis before any corpus-wide conclusion.
