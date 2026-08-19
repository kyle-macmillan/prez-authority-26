# Child–Parent Directive Method (Pilot Specification)

## Objective and definition

For a later presidential directive, identify the earlier directive(s) that an OLC lawyer
or other drafter would most likely have treated as substantive drafting precedent. This
is an expected-precedent relationship, not proof that the drafter actually consulted or
copied the earlier document.

A candidate parent must:

1. predate the child;
2. address the same **specific policy problem**; and
3. use a **materially similar operative action or mechanism**.

Shared subject words, actors, boilerplate, structure, or copied text are supporting
signals, not sufficient conditions. A child may have several parents when different
earlier directives supply precedent for different provisions.

## Eligibility and information separation

- Analyze executive orders, memoranda, proclamations, and letters together.
- Exclude codebook-defined ceremonial directives.
- Similarity-retrieval targets are directives that contain no reference to another
  directive of any type. Referencing documents remain eligible as parents.
- Any non-ceremonial earlier directive type may be a parent; same-type matching is not
  required.
- Require a strictly earlier date. Same-day documents are excluded because their true
  drafting order is not reliably observed across directive types.
- Remove the complete vesting clause and mask residual legal-authority citations before
  synthesis, embeddings, lexical retrieval, reuse detection, reranking, or review.
- Do not compare vesting-clause authorities until parent judgments and the graph are
  frozen.

## Representations

Each directive has three linked, authority-blind representations:

1. cleaned full text;
2. stable operative-action segments; and
3. a grounded LLM synthesis containing a policy card and action records.

The policy card records the specific problem, subject matter, affected entities,
geographic scope, triggers, programs, and institutional actors. Each action record
describes actor, action, object, mechanism, conditions, timing, and intended effect.
Every synthesis claim must cite a supplied operative segment ID. The synthesis model is
not asked to identify a parent.

Syntheses are cached with the document ID, source hash, prompt version, schema version,
and model. During development, synthesize only the 20 pilot children and the deduplicated
parents returned by the initial authority-blind retrieval. After prompts and schema are
frozen, synthesize every non-ceremonial directive once to build the evaluation index.

## Hybrid retrieval and ranking

For every child, retrieve the top four eligible earlier documents independently from:

- cleaned-text embeddings;
- synthesis embeddings;
- word/bigram TF–IDF (the lexical/word-importance channel); and
- distinctive exact ten-word reuse, ignoring phrases appearing in more than 25
  documents.

Deduplicate the union (normally at most 16; hard cap 20). The existing provision-level
pipeline then scores operative embeddings, word 3-grams, and sustained text reuse and
combines those rankings with unweighted RRF (`k=20`). Preserve all component ranks,
scores, and segment alignments.

The resulting candidate set is reranked four ways on identical, authority-blind inputs:

1. no LLM (RRF baseline);
2. Qwen3-Reranker 0.6B;
3. Qwen3-Reranker 4B; and
4. one selected frontier model.

The rubric is conjunctive: same specific policy problem **and** materially similar
operative mechanism. Frontier and general instruct-model responses separately score
policy match, mechanism match, and expected precedent from 0–3 and cite segment IDs.
The smaller Qwen rerankers use the same conjunctive language in their binary scoring
instruction. The comparison determines whether the frontier reranker adds enough value
to justify its cost. TopicGPT or a refinement may be added only as a retrieval ablation;
it is not required by the main method.

## Pilot and validation

Freeze two deterministic samples:

- **Development (20 children):** four random eligible children per directive type plus
  four additional trade proclamations.
- **Evaluation (40 untouched children):** eight random eligible existing-holdout
  children per type plus eight trade proclamations reserved from the non-holdout frame
  before development begins. (The existing holdout has only eight eligible
  proclamations total, so it cannot supply both strata.)

Trade proclamations are a known-parent genre and therefore a diagnostic stratum, not a
positive parent label. Trade-to-trade similarity is never automatically parenthood.

Reviewers see cleaned text and operative segments, but no authority text, retrieval
scores, method labels, or candidate ranks. Candidate display order is deterministically
randomized. For every pair they assign `no`, `plausible`, or `strong` separately to:

- the policy-problem match;
- the operative-mechanism match; and
- the overall expected-precedent relationship.

They also record supporting segment IDs and a short explanation. Formal earlier-
directive references form a separate hidden benchmark; they are not tuning examples.

Report nDCG@10, precision@5 and @10, MRR, and Success@5/@10/@20 for every reranker,
overall and for the trade-proclamation stratum. Also audit cross-type parents, policy-
only false positives, mechanism-only false positives, generic-language matches,
left-censoring, and failures where no retrieved candidate is adequate.

## Implemented workflow

The implementation reuses the existing segmenter, embedding cache, segment-level
ranking, Qwen runner, and HTML-review conventions.

```bash
# Rebuild eligibility and authority-blind source artifacts.
python3 src/parent_analysis.py

# Freeze the development and evaluation samples.
python3 src/build_parent_method_pilot.py

# Initial development retrieval without synthesis, then synthesize only its union.
python3 src/hybrid_candidate_pool.py \
  --children data/parent_analysis/method_pilot/development_children.csv
python3 src/synthesize_directives.py --scope pilot \
  --pilot-manifest data/parent_analysis/method_pilot/pilot_manifest.json \
  --candidates data/parent_analysis/hybrid_candidate_pool.csv

# Run the frozen requests through candidate synthesis models, then validate/import the
# selected model's JSONL responses and embed the resulting cards.
python3 src/synthesize_directives.py --scope pilot \
  --pilot-manifest data/parent_analysis/method_pilot/pilot_manifest.json \
  --candidates data/parent_analysis/hybrid_candidate_pool.csv \
  --responses RESPONSES.jsonl
python3 src/embeddings/embed_parent_analysis.py --artifact syntheses

# Rebuild the union and apply the existing provision-level ranker.
python3 src/hybrid_candidate_pool.py \
  --children data/parent_analysis/method_pilot/development_children.csv
python3 src/rank_candidate_pool.py \
  --candidate-pool data/parent_analysis/hybrid_candidate_pool.csv \
  --output data/parent_analysis/ranked_hybrid_candidates.csv

# Run Qwen twice by changing model path/label; generate/import frontier pair requests
# with parent_reranker_protocol.py. Repeated imports accumulate in one comparison CSV.
python3 src/rerank_qwen_candidates.py \
  --candidates data/parent_analysis/ranked_hybrid_candidates.csv \
  --model-path PATH_TO_QWEN_0.6B --model-label qwen3-reranker-0.6b \
  --output data/parent_analysis/qwen_0.6b.csv
python3 src/rerank_qwen_candidates.py \
  --candidates data/parent_analysis/ranked_hybrid_candidates.csv \
  --model-path PATH_TO_QWEN_4B --model-label qwen3-reranker-4b \
  --output data/parent_analysis/qwen_4b.csv
python3 src/parent_reranker_protocol.py \
  --candidates data/parent_analysis/ranked_hybrid_candidates.csv

# Build blinded review material and evaluate exported judgments.
python3 src/build_parent_method_viewer.py \
  --sample data/parent_analysis/method_pilot/development_children.csv \
  --candidates data/parent_analysis/ranked_hybrid_candidates.csv \
  --output data/parent_analysis/method_pilot/development_viewer.html
python3 src/evaluate_parent_retrieval.py \
  --rankings data/parent_analysis/reranker_comparison.csv \
  --judgments JUDGMENTS.json --output RESULTS.json
```

After development choices are frozen, repeat synthesis with `--scope all`, rebuild the
full synthesis embedding index, and run only the untouched evaluation children. Parent
edges and authority divergence are joined only after that evaluation graph is fixed.
