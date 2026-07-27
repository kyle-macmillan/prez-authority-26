# Implementation Plan: Authority-Masked Executive-Order Precedent Graph

## 1. Project objective

This project studies variation in the legal authority Presidents invoke when issuing
executive orders (EOs). In particular, it asks when a new EO uses authority that differs
from the authority used in the most relevant earlier drafting precedents.

The immediate task is to construct a historical precedent graph:

- Each **child** is an EO being evaluated.
- A **parent** is an earlier EO that would have been a genuinely useful precedent to a
  lawyer drafting the child.
- A child may have multiple parents because different sections may draw on different
  precedents.
- A child may have no parent in the available corpus.
- Parent relationships are typed and graded rather than forced into a single family-tree
  relationship.

The motivating thought experiment is an attorney at the Office of Legal Counsel drafting
an EO and looking for earlier EOs that are useful because they address the same problem,
use the same governmental mechanism, or contain adaptable language and structure.

This is not limited to formal legal ancestry. An amendment, revocation, replacement, or
superseding order is an obvious candidate parent, but useful precedents can also include:

- recurring annual or periodic orders;
- orders implementing the same statutory program;
- orders that reproduce or adapt substantial portions of an earlier EO; and
- orders concerning a durable institutional regime, such as sanctions, procurement,
  federal personnel, regulatory review, or national-security organization.

The first implementation should cover the 3,620 executive orders in
`data/4_28_2026_build_dev.csv`. Memoranda, proclamations, and letters can be added after
the EO methodology is validated.

## 2. Core identification principle

Parent selection and authority analysis must remain separate.

The legal authority cited by an EO is the outcome of interest. It must not be used to find
the EO's parents, score their similarity, determine their topic, or adjudicate whether a
candidate is a useful precedent. Otherwise, the parent graph would be mechanically biased
toward EOs with similar authority language and would suppress the divergence the project
is designed to study.

The workflow therefore has two ordered phases:

1. Construct and freeze the precedent graph using authority-masked text.
2. Restore and compare authority information only after the graph is fixed.

No authority-derived feature may cross from the second phase into the first.

## 3. Authority masking

### 3.1 Primary representation

Replace only authority-bearing spans in the vesting clause with a neutral
`[AUTHORITY]` token. Preserve surrounding drafting language.

For example:

> By the authority vested in me as President by the Constitution and the laws of the
> United States of America, and pursuant to section 301 of title 3, United States Code,
> it is hereby ordered as follows:

should become:

> By the authority vested in me as President by [AUTHORITY], and pursuant to [AUTHORITY],
> it is hereby ordered as follows:

Words such as the following must remain visible:

- `pursuant to`;
- `under`;
- `by virtue of`;
- `by the authority vested in me`;
- `consistent with`; and
- non-authority purpose language such as `in order to`.

A contiguous list that jointly identifies one or more legal authorities should be
collapsed to one token where practical. This prevents the number, length, or formatting of
the citations from revealing the authority category indirectly.

### 3.2 Robustness representation

Create a stricter representation that masks authority-bearing spans throughout the EO,
not just in the vesting clause. Continue to preserve surrounding relational language such
as `pursuant to`.

Run the complete retrieval and graph-construction process on both representations:

- The primary graph uses vesting-authority masking.
- The robustness graph uses document-wide authority masking.

Differences between the graphs should be reported. The stricter graph is a sensitivity
analysis, not an automatic replacement for the primary graph, because statutory
references in operative provisions may be substantively useful drafting information.

### 3.3 Leakage safeguards

- Any generated summary or embedding input must be created from already-masked text.
- Cached unmasked embeddings must never be used for precedent retrieval.
- Authority category, specificity, source count, and exact authority identifiers must not
  be candidate-generation or reranking features.
- Expert reviewers judging precedent relevance must see masked text.
- Authority data should be stored separately from retrieval features after extraction.

## 4. Unit of comparison and section roles

Use the existing section segmentation as the starting point. The corpus supports
section-level retrieval: approximately 78 percent of its EOs contain more than one content
section, with a median of four content sections per EO.

Every section should remain eligible to contribute evidence, but sections should be
assigned functional roles so that the system can prefer like-for-like comparisons:

1. **Purpose, policy, or findings**
2. **Definitions**
3. **Operative action**
4. **Implementation or delegation**
5. **Reporting, monitoring, or oversight**
6. **General provisions, effective date, or severability**

Role labels should affect scoring rather than act as hard filters. For example, an
operative-action section should normally be compared most strongly with earlier operative
sections, but a purpose section may supply context needed to interpret that action.
Operative sections should receive the greatest default weight.

The current 0–3 legal-operativeness code can be tested as a derived section feature only
if it is assigned from authority-masked operative text. It must not be inferred from the
vesting authority. It should be a soft compatibility signal, not a requirement that parent
and child share the same code.

## 5. Parent types

An earlier EO can qualify as a parent through any of three independently graded forms of
drafting usefulness:

### 5.1 Substantive-policy precedent

The earlier EO addresses the same policy problem, program, institution, population, or
governmental objective.

### 5.2 Operative-mechanism precedent

The earlier EO uses a relevant legal or administrative mechanism, such as:

- delegation;
- rulemaking or rescission;
- reporting or review;
- agency coordination;
- funding conditions or restrictions;
- asset blocking or sanctions;
- entry suspension;
- land or status designation;
- institutional creation;
- personnel or succession rules; or
- amendment of an existing order.

Mechanism similarity may be useful even when the policy subjects differ.

### 5.3 Language or structural precedent

The earlier EO supplies reusable wording, organization, definitions, implementation
clauses, or other drafting architecture. This includes exact copying, light revision,
paraphrase, reordered provisions, and adaptation of a recurring template.

### 5.4 Formal relationship attributes

Separately identify formal relationships appearing in the text:

- cites;
- amends;
- revokes or replaces;
- supersedes;
- extends or continues;
- implements;
- delegates authority from; and
- reproduces or incorporates text from.

Formal relationships are high-value candidate signals but are not automatically the gold
standard for parenthood. A background citation may not be a useful drafting precedent, and
an uncited EO may be highly useful.

An EO may carry several usefulness types and several formal attributes on the same edge.

## 6. Candidate generation

Only EOs dated before the child are eligible candidates. Search the entire earlier corpus
without imposing a temporal window or recency penalty in the primary specification.

Generate a high-recall candidate pool through four parallel channels.

### 6.1 Lexical retrieval

Use BM25 over authority-masked sections. Index both:

- the section text; and
- limited masked document context, including the EO title and section heading.

Lexical retrieval should capture distinctive policy terms, institutional names, actors,
and operative phrases.

### 6.2 Dense semantic retrieval

Embed authority-masked sections with a general or legal-domain retrieval encoder. Keep
the model replaceable so that at least two plausible encoders can be compared on the
expert pilot.

Do not select the final encoder based on generic embedding benchmarks. Select it using
candidate recall and ranking quality on held-out child EOs from this project.

### 6.3 Text-reuse retrieval

Use word or character shingles with a locality-sensitive method such as MinHash, followed
by an exact overlap or alignment score. This channel should be sensitive to:

- copied passages;
- small substitutions;
- moved or reordered provisions; and
- local reuse that would be diluted in a whole-document score.

Semantic comparison should supplement this channel for paraphrased reuse.

### 6.4 Formal-reference retrieval

Extract references to numbered EOs and relation cues such as `amend`, `revoke`,
`supersede`, `continue`, and `implement`.

The existing corpus provides a strong starting signal:

- 5,225 distinct source-target EO citation pairs can be extracted;
- approximately 75 percent of cited targets resolve to another row in the corpus; and
- all 3,620 EO numbers are recoverable from their URLs.

Retain the cited EO, intervening modifiers, and other members of the formal chain as
candidates. If a child cites an original EO after another EO has modified it, both the
original and the relevant modifier should be considered possible parents. Keep the
explicit citation and the inferred effective-lineage relationship as distinct attributes.

### 6.5 Candidate fusion

Combine the four ranked lists with Reciprocal Rank Fusion or another transparent
rank-based method. Do not require topic agreement. Retain the originating channel and
channel-specific score for later ablation tests and reviewer explanations.

Topic modeling may be used to:

- describe broad policy regimes;
- stratify the annotation sample;
- find underrepresented areas; and
- visualize the resulting graph.

Topic membership must not determine which documents are allowed to be parents.

## 7. Section-pair reranking

Rerank only the fused candidate pool; do not run an expensive pairwise model over every
possible historical EO pair.

For every child-section/candidate-section pair, compute or assess:

- masked lexical overlap;
- masked semantic similarity;
- local text reuse;
- section-role compatibility;
- policy-subject similarity;
- operative-mechanism similarity;
- actor, object, and affected-entity overlap;
- structural or template similarity; and
- formal relationship evidence.

Compare a transparent feature-based reranker with a stronger semantic pairwise model.
If an LLM is tested, require structured outputs tied to quoted masked passages. LLM
judgments should not become the sole source of gold labels.

The system should retain the best section alignments rather than only a document-level
similarity score.

## 8. Aggregating sections into document-level parents

Create a document-level parent edge when either:

- one section pair provides strong drafting-precedent evidence; or
- several moderate section matches jointly demonstrate useful coverage.

Do not assign a fixed number of parents. Use an expert-calibrated absolute threshold so
that:

- a child can have multiple parents;
- different parents can support different child sections; and
- a genuinely novel or unmatched child can remain parentless.

The aggregation model should expose:

- strongest section-pair score;
- number of supporting section pairs;
- proportion and roles of child sections supported;
- usefulness type scores;
- formal relationship attributes; and
- final calibrated confidence.

Search all earlier EOs on similarity alone in the primary model. Preserve temporal
distance as metadata. A separate robustness model may add a modest recency preference,
but recency must not silently define parenthood.

## 9. Expert-annotation pilot

### 9.1 Size and sampling

Create an approximately 1,000-pair pilot consisting of roughly 60–80 child EOs and 12–15
candidate parents per child.

Stratify child selection across:

- presidential administrations and historical eras;
- EO length and number of sections;
- policy areas and section-role compositions;
- EOs with and without explicit formal references;
- apparent recurring regimes;
- likely text reuse; and
- candidate-generation channels.

Within each child, mix high-ranked candidates with hard negatives. Include candidates
unique to each retrieval channel so candidate recall can be evaluated rather than only
reranker quality.

Split training, validation, and evaluation by child EO. Section pairs or candidate parents
from the same child must never be divided across splits.

### 9.2 Reviewer presentation

Show reviewers:

- authority-masked child and candidate text;
- document titles and dates;
- proposed matched sections;
- enough surrounding masked context to understand each section; and
- visible formal amendment or citation language outside the masked authority spans.

Do not show:

- the extracted authority sources or categories;
- an unmasked vesting clause;
- model-generated parent conclusions; or
- retrieval scores that could anchor the judgment.

Shuffle candidate order within each child.

### 9.3 Labels

For each candidate pair, reviewers should record:

- substantive-policy usefulness: `0`, `1`, or `2`;
- operative-mechanism usefulness: `0`, `1`, or `2`;
- language/structure usefulness: `0`, `1`, or `2`;
- overall useful parent: `yes` or `no`;
- matched child and parent sections;
- formal relationship type, if any;
- confidence or `flag for discussion`; and
- an optional short rationale.

The scale should mean:

- `0`: not usefully similar;
- `1`: relevant supporting precedent;
- `2`: strong or central drafting precedent.

### 9.4 Reliability and adjudication

Independently double-code a stratified 25 percent of the approximately 1,000 pairs.
Measure agreement separately for:

- overall parent status;
- each usefulness dimension;
- matched section identification; and
- formal relationship type.

Use an agreement statistic appropriate to the label type, report raw agreement, and
adjudicate disagreements before creating the final evaluation labels. Oversample rare
edge types in the overlap set so their agreement estimates are not based on only a few
examples.

## 10. Evaluation

Evaluate candidate generation and final ranking separately.

### 10.1 Candidate-generation metrics

- Recall of expert-positive parents in the fused candidate pool
- Recall contributed uniquely by each retrieval channel
- Recall by usefulness type
- Recall by historical era and EO length

### 10.2 Ranking and graph metrics

- Recall@k
- Precision@k
- nDCG@k using graded expert relevance
- Average precision
- Parent-edge precision, recall, and F1 at the chosen threshold
- Accuracy of matched section pairs
- Calibration of parent confidence
- Accuracy of the no-parent decision

### 10.3 Required ablations

Compare:

- BM25 alone;
- dense retrieval alone;
- text reuse alone;
- formal references alone;
- lexical plus dense retrieval;
- all four candidate channels;
- section-aware versus whole-document retrieval;
- with and without section-role features;
- primary versus document-wide authority masking;
- with and without recency weighting; and
- transparent versus semantic reranking.

### 10.4 Error analysis

Manually audit:

- false positives caused by generic EO boilerplate;
- false positives sharing a topic but using an irrelevant mechanism;
- false negatives involving paraphrase or vocabulary change;
- false negatives involving reordered sections;
- recurring programs and institutional regimes;
- old canonical precedents displaced by recent but weak matches;
- formal citations that are merely background;
- relevant uncited precedents; and
- parentless EOs incorrectly forced into a lineage.

## 11. Graph representation

Store the final result as a typed multigraph. The edge table should contain at least:

| Field | Description |
|---|---|
| `child_id` | Corpus identifier for the later EO |
| `parent_id` | Corpus identifier for the earlier EO |
| `child_date` | Date of the child |
| `parent_date` | Date of the parent |
| `temporal_distance` | Time between parent and child |
| `child_section_ids` | Supporting child sections |
| `parent_section_ids` | Matched parent sections |
| `substantive_grade` | Expert/model grade for policy usefulness |
| `mechanism_grade` | Expert/model grade for operative usefulness |
| `language_grade` | Expert/model grade for language/structure usefulness |
| `formal_relations` | Typed formal relationship attributes |
| `retrieval_channels` | Channels that surfaced the candidate |
| `parent_confidence` | Calibrated final confidence |
| `review_status` | Unreviewed, reviewed, double-coded, or adjudicated |
| `evidence` | Masked supporting excerpts or section references |

Keep authority outcomes in a separate table joined by EO identifier only after graph
construction. This separation should be reflected in both code modules and persisted
artifacts.

## 12. Authority extraction and divergence analysis

After freezing the graph, extract and normalize:

- exact constitutional provisions or roles;
- exact statutes, U.S.C. sections, Public Laws, and named Acts;
- generic constitutional or statutory invocations; and
- the existing constitutional/statutory specificity category.

Preserve exact sources and broad categories because they answer different questions:

- **Category variation** identifies movement between generic and specific authority
  practices.
- **Source variation** identifies particular authorities added, removed, retained, or
  substituted.

Authority comparison must not alter parent selection retroactively.

### 12.1 Pairwise analysis

For every parent-child edge, record:

- exact authorities retained, added, removed, or substituted;
- change in constitutional specificity;
- change in statutory specificity;
- whether the child is more specific, less specific, differently specific, or unchanged;
- usefulness type and formal relationship type; and
- temporal distance and administration change.

Because one child may contribute several parent edges, pairwise statistical analyses must
account for dependence among edges sharing a child or parent.

### 12.2 Parent-set analysis

For each child, describe the distribution of authority practices among all parents rather
than immediately reducing them to one average.

Classify the child as:

- following the modal parent practice;
- following a minority parent practice;
- adopting an authority category absent from all parents; or
- emerging from a parent set that was already internally divided.

Report:

- the modal category;
- the full parent-category distribution;
- disagreement or entropy within the parent set;
- equal-parent results; and
- results weighted by expert relevance or calibrated edge confidence.

Pairwise and parent-set analyses are complementary. Pairwise analysis preserves distinct
transitions; parent-set analysis prevents children with many parents from dominating the
results and distinguishes departure from consensus from selection among conflicting
precedents.

## 13. Corpus and validity constraints

- The development corpus begins in 1948. Early EOs are left-censored because relevant
  earlier parents may be unavailable.
- Do not tune retrieval rules on the repository's reserved holdout IDs.
- Parent status means useful drafting precedent, not proof that the drafter actually
  consulted or copied the earlier EO.
- Similarity scores are measurement tools, not causal evidence.
- Formal citations reveal relationships but do not exhaust the possible precedents.
- The graph is many-to-many and may contain several kinds of connection between the same
  documents.
- Novelty and no adequate precedent are substantively meaningful outcomes.

## 14. Recommended implementation sequence

1. **Create authority masks**
   - Extend the existing vesting-authority extraction work to return character spans.
   - Produce primary and document-wide masked representations.
   - Add tests proving that authority text is removed while connectors remain.

2. **Create stable section records**
   - Run the existing segmenter over EOs.
   - Assign stable document and section identifiers.
   - Add section-role labels and masked context.

3. **Build interpretable baselines**
   - Extract formal-reference edges.
   - Implement BM25 and text-reuse retrieval.
   - Inspect representative results before adding learned components.

4. **Add dense retrieval and fusion**
   - Compare at least two encoders.
   - Fuse channel rankings and retain channel provenance.

5. **Build the annotation viewer and pilot**
   - Sample approximately 1,000 candidate pairs.
   - Collect graded expert labels with 25 percent overlap.
   - Adjudicate the evaluation set.

6. **Train or calibrate reranking and aggregation**
   - Compare transparent and semantic rerankers.
   - Calibrate the parent/no-parent threshold.
   - Freeze the primary and robustness graphs.

7. **Analyze authority divergence**
   - Join the frozen graph to exact authority sources and categories.
   - Produce pairwise and parent-set datasets.
   - Run robustness and error analyses.

8. **Extend document coverage**
   - After EO validation, assess memoranda, proclamations, and letters separately.
   - Do not assume EO thresholds or section-role behavior transfer unchanged.

## 15. Acceptance criteria

The initial implementation is complete when:

- authority-masked EO and section datasets are reproducible;
- tests confirm that authority sources cannot enter retrieval features;
- all candidate channels and their ablations can be run independently;
- the expert pilot contains approximately 1,000 reviewed pairs with 25 percent independent
  overlap;
- the final threshold permits both multiple-parent and no-parent outcomes;
- every graph edge is traceable to matched masked sections and typed usefulness evidence;
- primary and stricter-masking graphs are both exported;
- the graph is frozen before authority outcomes are joined;
- pairwise and parent-set authority-change datasets are generated; and
- results report retrieval quality, reviewer reliability, subgroup performance,
  left-censoring, and required robustness specifications.

## 16. Methodological references

The following work supports the major design choices:

- Hou et al., **CLERC: A Dataset for U.S. Legal Case Retrieval and
  Retrieval-Augmented Analysis Generation** (2025). Its masked-citation retrieval task is
  a close analogue to identifying relevant precedents without exposing the outcome:
  <https://aclanthology.org/2025.findings-naacl.441/>
- Reuter et al., **Towards Reliable Retrieval in RAG Systems for Large Legal Datasets**
  (2025). Supports augmenting chunks with masked document context to reduce
  document-level retrieval mismatch:
  <https://aclanthology.org/2025.nllp-1.3/>
- Wang, Reimers, and Gurevych, **DAPR: A Benchmark on Document-Aware Passage
  Retrieval** (2024). Supports combining passage-level retrieval with document context:
  <https://aclanthology.org/2024.acl-long.236/>
- Kim et al., **Learning Bill Similarity with Annotated and Augmented Corpora of Bills**
  (2021). The closest established analogue for human-labeled subsection relationships,
  paraphrase, reordering, and document-level aggregation:
  <https://aclanthology.org/2021.emnlp-main.787/>
- Rykov et al., **Fine-Grained Semantic Comparison of Legal Documents using LLMs**
  (2026). Relevant to paragraph-pair comparison and semantic-change detection:
  <https://aclanthology.org/2026.acl-srw.86/>
- Arulanandam and de Silva, **Section-Weighted Hybrid Approach for Legal Case
  Retrieval** (2026 preprint). Closely aligned with lexical/semantic fusion followed by
  like-for-like section comparison, but too recent to serve as the sole methodological
  foundation:
  <https://arxiv.org/abs/2606.03138>

The evidence base favors hybrid, section-aware retrieval with expert evaluation. Recent
graph-neural and LLM-heavy methods may be useful experimental comparisons, but the first
implementation should prioritize interpretable baselines, explicit leakage controls, and
an auditable human gold standard.
