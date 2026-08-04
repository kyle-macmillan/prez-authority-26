# Methodological Plan for the Child–Parent Analysis

## Research objective

The child–parent analysis will identify the most relevant earlier executive order (EO)
or orders for each later EO and then assess whether the child invokes different legal
authority from its parent set.

- A **child** is the later EO being evaluated.
- A **parent** is an earlier EO that has a qualifying explicit or similarity-based
  relationship to the child.
- A child may have multiple parents or no parent. An EO with no identified parent is an
  **orphan**.
- The initial analysis is limited to EOs. Other presidential documents are outside its
  scope.

Parenthood is evidence that an earlier EO is a useful substantive and drafting
precedent; it does not establish that the child's drafter actually consulted or copied
the earlier order.

## Definition of a parent

There are two routes to parent status.

### Explicit-reference parent

Any resolved reference to an earlier EO creates an automatic parent edge. References
will be labeled, where possible, as amendments, revocations, supersessions,
modifications, continuations, replacements, delegations of authority under an earlier
EO, or general citations/discussions.

### Similarity-based parent

When a child has no automatic parent, a candidate must satisfy both:

1. **Substantive-policy similarity:** the earlier EO addresses the same substantive
   policy problem.
2. **Operative-mechanism similarity:** the earlier EO uses a similar legal directive,
   directed action, or legal or administrative mechanism.

Shared language, structure, or drafting architecture is supplementary evidence. It may
strengthen a match but cannot establish parenthood by itself because EOs contain
substantial recurring boilerplate. One highly similar operative segment can support a
document-level parent relationship; it need not account for a minimum share of the
child's text.

## Parent-identification procedure

### Stage A: explicit relationships

Stage A uses the original, unmasked EO text to:

1. extract every reference to an EO;
2. resolve the reference to an EO in the corpus;
3. confirm that the candidate precedes the child, ordering same-day EOs by EO number;
4. identify nearby relationship language; and
5. create a labeled automatic edge.

Only earlier EOs are eligible, and no maximum temporal distance is imposed. In the
initial specification, a child with at least one automatic edge does not proceed to
similarity retrieval for additional uncited parents.

### Stage B: similarity relationships

Only children without an automatic edge enter Stage B. For each unresolved child:

1. create cleaned, authority-masked full-document and operative-segment
   representations;
2. use a full-document embedding to retrieve the 25 most similar earlier EOs;
3. independently rank those 25 candidates using:
   - operative-segment embeddings;
   - lexical similarity, such as BM25;
   - n-gram similarity; and
   - sustained text reuse;
4. combine the four within-pool rankings using unweighted Reciprocal Rank Fusion
   (RRF); and
5. retain the fused top 10 for manual review.

The lexical, n-gram, text-reuse, and operative-embedding channels rerank only the
embedding-derived pool; they do not introduce candidates outside the top 25.

## Preprocessing and representations

Authority information is a later outcome and must not influence similarity-based parent
selection. All Stage B retrieval and review materials will therefore mask cited legal
authority throughout the document, including constitutional authority, statutes and
U.S.C. provisions, Public Laws, named Acts, earlier EOs, and other identifiable legal
citations.

The shared cleaned text will also remove severability clauses and recurring
general-provisions limitations, while retaining EO-specific provisions, findings,
purposes, definitions, preambles, and other substantive material. An entire section
will not be removed merely because it is titled “General Provisions.”

Each EO will have two linked representations:

1. **Cleaned full-document text**, used for the initial policy-and-action retrieval
   gate.
2. **Operative-action segments**, generated with the extended Woolley and Peters
   ordering-phrase approach and used for mechanism comparison.

The operative method will be applied consistently whether or not an EO contains formal
section headings. Stable document and segment identifiers will preserve links between
candidate edges and their supporting text.

The planned embedding model for the pilot is `Qwen/Qwen3-Embedding-0.6B`, using its full
1,024-dimensional output. Model and tokenizer revisions, package versions, embedding
instructions, preprocessing version, token counts, and creation dates will be recorded;
overlength documents will not be silently truncated.

## Manual pilot

A reproducible random sample of 50 unresolved children will be drawn after Stage A.
Reviewers will assess the 10 fused candidates for each child, yielding 500 candidate
comparisons.

The review interface will show titles, dates, EO numbers, complete cleaned text, and
highlighted proposed operative-segment matches. It will conceal authority text,
extracted authority outcomes, the vesting clause, the fused candidate order, and any
model-generated parent conclusion.

For each child, the reviewer will select a qualifying parent or `none` and provide a
short explanation. If several candidates qualify, the default is the most recent one.
Multiple parents may be retained when different earlier EOs meaningfully support
different operative segments, with the exception documented.

## Validation and orphan analysis

The pilot will report:

- the share of children with a qualifying parent in the reviewed top 10;
- the share classified as orphans;
- the fused ranks and component-channel ranks of selected parents;
- cases where segment evidence changes the full-document ranking;
- false positives from generic language;
- policy matches without a matching mechanism and mechanism matches without a matching
  policy problem; and
- apparent retrieval failures.

An orphan classification will not automatically be treated as an error. Qualitative
review will distinguish genuine novelty from left-censoring, failure of the top-25
embedding gate, failure of within-pool ranking, and preprocessing or masking errors.
The pilot will inform choices that are deliberately left open, including segment-score
aggregation, BM25 fields, n-gram specification, text-reuse measurement, rank weights,
and any eventual automated parent threshold.

## Graph and authority-divergence analysis

The final parent structure will be stored as a directed graph with typed edges. Edge
records will preserve child and parent identifiers and dates, temporal distance, edge
source and formal relation, supporting segment identifiers and excerpts, channel scores
and ranks, fused rank, review decision, and reviewer explanation.

Authority outcomes will remain in a separate table until parent identification is
fixed. The later authority comparison will then record, for every child–parent
relationship, authorities retained, added, removed, or substituted and whether any
authority divergence occurred. The final divergence summaries and statistical models
will be specified after the parent-identification pilot.

## Current implementation status

Stage A extraction, chronological eligibility, relation labeling, initial authority
masking and boilerplate removal, operative segmentation, and stable intermediate
artifacts have been implemented. Their outputs remain provisional pending manual
validation, especially for reference recall, relation labeling, masking accuracy,
boilerplate removal, and segment quality.

Embedding generation, top-25 retrieval, the four within-pool rankings, RRF fusion, the
50-child sample, manual review, orphan assessment, and authority-divergence modeling
remain to be completed.
