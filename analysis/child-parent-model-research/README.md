# Model choices for child-parent directive inference

**Research memo — August 17, 2026**

## Executive conclusion

The intuition that a frontier model could improve the child-parent decisions is
plausible, especially for the final judgment, but the evidence does not support replacing
every component with one frontier model or selecting a model from general legal
benchmarks.

The best next design is a **stage-specific bakeoff**:

1. retain Gemini 3.6 Flash as the historical baseline;
2. test the current Gemini successor and the strongest general reasoning models on the
   project's own blinded parent labels;
3. evaluate function-profile extraction separately from parent ranking and acceptance;
4. test legal-specialized models only in retrieval/reranking ablations; and
5. defer fine-tuning until there are several hundred high-quality reviewed cases and a
   genuinely untouched test set.

My quality-first shortlist is:

| Pipeline stage | Primary challengers | Why |
|---|---|---|
| Function-profile extraction | Gemini 3.7 Flash (medium), GPT-5.6 Sol (high), Claude Fable 5 | Compare the baseline's direct successor with the strongest current general models; score schema validity and evidence faithfulness, not eloquence. |
| Joint top-25 ranking | GPT-5.6 Sol (xhigh), Claude Fable 5, Gemini 3.7 Flash (high) | This is the stage where additional reasoning capacity is most likely to help distinguish generic similarity from reusable drafting machinery. |
| Candidate-or-none | The same three, in separate calls | Absolute plausibility is a different decision from relative ranking and should remain separately calibrated. |
| Retrieval/reranking ablation | Qwen3-Reranker-8B and one legal retrieval model | A larger cross-encoder and a legal-domain alternative test whether the current 0.6B reranker or embeddings constrain the candidate pool. |

I would **not** adopt a legal generative model or fine-tuned model now. The project's
task-specific labels are much more valuable than a model's generic exposure to statutes,
cases, or legal QA.

## Literature-supported summary by alternative

The table below separates what the computer-science literature actually establishes from
the inference for this project. “Supported” does not mean that an exact 2026 model has
already been validated on presidential directives. GPT-5.6 Sol, Claude Fable 5, and
Gemini 3.7 Flash are too new for independent peer-reviewed evidence on this task.

| Alternative | Finding from peer-reviewed CS literature | Implication for this project | Strength of support |
|---|---|---|---|
| **Frontier/reasoning model** | Reasoning-specialized models consistently beat general-purpose counterparts when relevant precedents are supplied in the [Korean Canonical Legal Benchmark](https://aclanthology.org/2026.eacl-short.17/) (EACL 2026). Test-time-scaled models also perform strongly across Chinese and English legal tasks in [Hu et al.](https://aclanthology.org/2025.findings-emnlp.742/) (EMNLP Findings 2025). [LawBench](https://aclanthology.org/2024.emnlp-main.452/) (EMNLP 2024) found the then-frontier GPT-4 stronger overall than the evaluated legal-specific LLMs, although specialized models led some memorization tasks. | A high-reasoning frontier model is the leading hypothesis for comparative ranking and candidate-or-none judgment, where all relevant text is supplied. Test the exact current models; do not infer a winner from older benchmarks. | **Moderate for the model class; absent for the exact current models and task.** |
| **Legal-specialized generative model** | Domain adaptation can improve legal NLP: [LEGAL-BERT](https://aclanthology.org/2020.findings-emnlp.261/) (EMNLP Findings 2020), [LexGLUE](https://aclanthology.org/2022.acl-long.297/) (ACL 2022), and [LawInstruct](https://aclanthology.org/2025.findings-naacl.7/) (NAACL Findings 2025) report gains on legal downstream tasks. But the gains are task-dependent: [Barale et al.](https://aclanthology.org/2023.nllp-1.4/) (NLLP 2023) found inconsistent behavior among law-oriented models, and LawBench found that stronger general foundations could outperform specialized legal LLMs. | Legal specialization is not a sufficient reason to replace a frontier generator. Because authority is masked and the task is grounded structural analogy rather than doctrinal recall, admit a legal generator only if it wins the same blinded evaluation. | **Strong that specialization can help matched legal tasks; weak that it helps this task or beats a frontier model.** |
| **Legal/domain-specific retrieval or reranking** | Legal precedent retrieval remains difficult: [CLERC](https://aclanthology.org/2025.findings-naacl.441/) (NAACL Findings 2025) reports only 48.3% Recall@1000 for zero-shot IR and finds that generic cross-encoder reranking can *degrade* performance under domain and document-length mismatch. COLIEE 2025's [competition analysis](https://pubmed.ncbi.nlm.nih.gov/42023121/) reports the strongest systems as multi-stage combinations of lexical retrieval, reranking, and LLM decisions rather than a single model. | Test a larger generic reranker and a legal-specific retriever, but only as frozen-pool ablations. Measure Recall@25 first; do not assume “legal” or “cross-encoder” means better. The current hybrid BM25, semantic, and text-reuse design is consistent with successful multi-stage IR practice. | **Strong for multi-stage evaluation and domain-mismatch caution; limited for any named legal retriever on directives.** |
| **Different ranking method** | [RankGPT](https://aclanthology.org/2023.emnlp-main.923/) (EMNLP 2023) and [ListT5](https://aclanthology.org/2024.acl-long.125/) (ACL 2024) show that listwise reranking can outperform pointwise baselines. [Found in the Middle](https://aclanthology.org/2024.naacl-long.129/) (NAACL 2024) demonstrates positional bias in listwise LLM ranking and improves results by aggregating shuffled permutations. | Keep listwise ranking as the main method, but evaluate deterministic candidate-order permutations. Compare it with pairwise or cross-encoder ranking on a reduced top set; preserve candidate-or-none as a separate absolute judgment. | **Strong for listwise effectiveness and position-bias controls; transfer to this 25-document task must be measured.** |
| **Fine-tuning/domain adaptation** | [Don't Stop Pretraining](https://aclanthology.org/2020.acl-main.740/) (ACL 2020) shows gains from both domain- and task-adaptive pretraining. LawInstruct obtains large legal-benchmark gains, but uses 12 million examples across 58 datasets—not tens of labels. Legal-domain work also warns that adaptation recipes do not transfer uniformly across tasks. | Fine-tuning is scientifically plausible later, but 20 reviewed EOs are an evaluation set, not a training corpus. First collect several hundred stratified, family-disjoint parent/none labels with hard negatives. Then compare a task-specific ranker or acceptance classifier against prompted frontier baselines on an untouched test set. | **Strong that sufficiently matched adaptation can help; strong that results are data- and task-dependent; no support for tuning on the present sample size.** |
| **One model for extraction and judgment** | The literature distinguishes information extraction, retrieval, reranking, and reasoning as different objectives. CLERC shows that strong generation does not imply strong retrieval, while legal-domain studies find architecture- and task-specific effects. | Select function-profile extraction separately from ranking and acceptance. Extraction should be judged on grounded completeness and schema/evidence validity; ranking on top-1/MRR; acceptance on candidate and abstention precision. | **Strong methodological support for task-specific evaluation; no evidence that one model is optimal across all stages.** |

The most defensible overall finding is therefore narrower than “frontier models are
better”: **reasoning-focused frontier models deserve priority for the final grounded
decision, while domain adaptation deserves a separate test in retrieval and later
task-specific tuning.** The CS literature also strongly supports evaluating each pipeline
stage and guarding listwise ranking against order effects.

## What the model is actually being asked to do

The current pipeline contains three distinct prediction problems:

1. **Extraction.** Gemini Flash converts an authority-masked directive and its operative
   segments into policy and operative functions, with actors, actions, targets,
   mechanisms, effects, evidence, offsets, and confidence.
2. **Relative ranking.** After hybrid retrieval, Gemini jointly orders 25 strictly
   earlier candidates.
3. **Absolute acceptance.** A separate call decides whether the rank-1 candidate is a
   plausible whole-document, structural-framework, or material-provision parent—or
   whether to abstain.

This decomposition matters. Extraction rewards literal grounding, complete coverage,
stable segmentation links, and valid structured output. Ranking rewards comparative
reasoning over many long candidates. Acceptance rewards calibration and the ability to
reject merely topical or boilerplate overlap. There is no reason to expect the same
model or reasoning setting to be best at all three.

The task is also unusual for a “legal” problem. Authority citations are deliberately
masked, outside legal knowledge is unnecessary for most comparisons, and the model is
asked to reason from supplied text about policy function and reusable administrative
machinery. It resembles grounded analogical retrieval more than legal research or legal
question answering.

## What the project already establishes

The repository's current method is unusually well positioned for a fair comparison:

- retrieval is frozen before the final model decision;
- every model can receive the same authority-blind profiles and top-25 pool;
- ranking and acceptance are separate;
- outputs have local schema and evidence validation; and
- model winners are reviewed blind.

The completed second EO pilot provides evidence that inference effort matters, but not a
decisive model-selection result. On 20 executive orders, Gemini 3.6 Flash thinking-medium
achieved 16/20 exact outcomes against the blinded review, versus 15/20 for thinking-off.
It also made fewer candidate decisions. A one-case difference on a single-type sample is
too uncertain to establish either a production model or an optimal reasoning level.

The larger unreviewed run cannot answer the quality question. Its 2,436 valid decisions
and 74.2% candidate rate measure throughput, validation success, and model behavior—not
ground-truth accuracy.

## Finding 1: frontier reasoning models are the leading hypothesis

Current vendor documentation identifies [GPT-5.6 Sol](https://developers.openai.com/api/docs/models)
as OpenAI's flagship model for complex professional work and exposes reasoning levels
through `max`. Anthropic describes [Claude Fable 5](https://platform.claude.com/docs/en/about-claude/models/overview)
as its most capable generally available model. Google now describes
[Gemini 3.7 Flash](https://ai.google.dev/gemini-api/docs/latest-model) as its most capable
Flash model and supports low, medium, and high thinking levels. These are vendor
capability descriptions, not evidence on this project, but they define the appropriate
quality-first challengers.

Independent legal-NLP evidence supports testing reasoning capacity. The
[Korean Canonical Legal Benchmark](https://aclanthology.org/2026.eacl-short.17/) supplies
the relevant precedents with each problem to separate reasoning from memorized legal
knowledge; across more than 30 models, reasoning-specialized models consistently
outperformed their general-purpose counterparts. A separate 2025 study of
[test-time scaling on legal reasoning](https://aclanthology.org/2025.findings-emnlp.742/)
also found strong results from reasoning models, while documenting persistent
interpretation and hallucination errors.

Those tasks are not presidential-directive parent inference, so the inference is limited:
when the necessary source material is supplied, extra reasoning appears more relevant
than memorized legal doctrine. That makes a frontier bakeoff well motivated, not already
decided.

### Recommended frontier configurations

- **GPT-5.6 Sol:** use `high` for extraction and `xhigh` for ranking/acceptance. Add `max`
  only as a within-model ablation; more reasoning should not be assumed to improve
  calibration.
- **Claude Fable 5:** use its documented adaptive reasoning behavior and pin the exact
  model ID used in the run.
- **Gemini 3.7 Flash:** use `medium` for extraction and `high` for ranking/acceptance.
  Preserve Gemini 3.6 Flash thinking-medium as the historical control rather than
  silently treating 3.7 as equivalent.

The first comparison should use no web search. Search is not needed to compare supplied,
authority-masked documents and introduces an uncontrolled external-information channel.
If there is a substantive reason to retain Search, evaluate it as a separately named
method, as the existing pipeline already does.

## Finding 2: legal specialization is most promising before the final judge

Legal-domain adaptation can help. [LexGLUE](https://aclanthology.org/2022.acl-long.297/)
found that legal-oriented language models consistently improved over generic models on
its English legal-understanding tasks. [LawInstruct](https://aclanthology.org/2025.findings-naacl.7/)
reported a 15-point aggregate LegalBench improvement for its base-size legal instruction
tune over the corresponding Flan-T5 baseline. These results establish that domain
adaptation can matter; they do not establish that a legal model beats a much newer
frontier model or that it transfers to parent inference.

The mismatch is substantial:

- LegalBench's 162 tasks evaluate forms of English legal reasoning, while this project
  has its own narrow definition of `plausible_precedent`.
- Many legal models are optimized for doctrine, case outcomes, contracts, legal QA, or
  citation behavior. The project intentionally masks authority and prohibits authority
  from driving the match.
- A smaller specialized generator can know more legal vocabulary yet reason less well
  across 25 long, subtly overlapping candidates.

For those reasons, a legal generator should not be a primary production candidate without
winning a task-specific blinded test.

Legal specialization is more plausible in **retrieval**. The recent
[Legal RAG Bench preprint](https://huggingface.co/papers/2603.01710) found that retrieval
choice had a larger effect than the choice between two frontier generators, and reported
large gains from a legal embedding model. That is useful directional evidence, but it is
a vendor-involved preprint, covers Australian criminal-law RAG rather than presidential
directives, and should not be generalized directly. It justifies an ablation—not a
pipeline replacement.

The most informative retrieval comparison is therefore:

1. current four-channel RRF and Qwen3 0.6B baseline;
2. the official [Qwen3-Reranker-8B](https://huggingface.co/Qwen/Qwen3-Reranker-8B) on the
   same frozen candidates; and
3. one legal embedding/reranker on the same corpus and evaluation labels.

Candidate generation must be evaluated with Recall@25 before final-judge accuracy. A
frontier judge cannot recover a true parent that retrieval omitted.

## Finding 3: the decision method may matter as much as the model

Jointly ranking all 25 candidates is attractive because the model sees the alternatives
and can make fine distinctions. Work on [LLM reranking](https://aclanthology.org/2023.emnlp-main.923/)
supports listwise methods, but research on
[permutation self-consistency](https://aclanthology.org/2024.naacl-long.129/) shows that candidate
position can affect listwise LLM rankings. The present design should therefore be tested
for order sensitivity rather than accepted as neutral.

For each model, compare:

- **Current listwise ranking:** all 25 candidates in one prompt.
- **Permutation-consistent listwise ranking:** run at least three deterministic input
  permutations and aggregate ranks. This directly tests position sensitivity.
- **Pairwise top-set comparison:** use a cross-encoder or frontier model to compare a
  smaller top set after first-stage reranking, then derive a ranking from pairwise wins.

The candidate-or-none call should remain separate in every condition. A relative winner
always exists; a plausible parent may not. Combining these stages would mechanically
increase false positives and erase the meaning of abstention.

Do not use one frontier model to generate labels and then declare another model correct
based on agreement with it. Human review remains the gold standard. An ensemble or
frontier adjudicator should be considered only after each constituent model has been
scored independently against blinded human decisions.

## Finding 4: fine-tuning is premature

Fine-tuning is useful when a project has enough examples of the exact input-output
behavior and a stable error pattern. Google's own
[tuning guidance](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/tune-models)
recommends first optimizing prompting and notes that tuning depends on sizable,
high-quality labeled data representative of production. Legal-domain studies such as
LawInstruct likewise use datasets vastly larger and broader than this project's reviewed
sample.

Twenty reviewed EOs are not a defensible training corpus. Fine-tuning on them would:

- overfit document type, era, policy area, candidate-pool construction, and reviewer
  idiosyncrasies;
- consume the only current gold set needed for unbiased evaluation;
- teach output style more readily than the substantive parent standard; and
- make it difficult to tell whether an apparent gain comes from memorizing recurring
  directive families.

Before fine-tuning, accumulate at least several hundred independently reviewed cases,
including accepted parents, true abstentions, hard topical negatives, material-provision
parents, and every directive type. Split by directive family or near-duplicate cluster,
not by random row, so close relatives cannot leak across training and test sets. Freeze
the test set before tuning.

When that evidence exists, tune a **task-specific ranker or acceptance classifier** first,
not a general “legal LLM.” The training objective should learn the project's explicit
parent rubric and hard negatives. A compact cross-encoder could then handle most pairs,
with a frontier model reserved for uncertain cases. This is more targeted and auditable
than continued pretraining on undifferentiated legal text.

## Recommended experiment and decision rule

The next experiment should be a model bakeoff, not a migration.

1. Freeze one complete profile snapshot, candidate pools, prompt versions, and a human
   review protocol.
2. Preserve the existing 20 reviewed EOs as an audit set. Add a larger blinded sample
   stratified by executive order, memorandum, proclamation, and letter; include policy
   areas and retrieval-margin bands.
3. For extraction, blind reviewers to model identity and score function completeness,
   unsupported functions, missed operative actions, evidence/offset correctness, schema
   validity, and downstream retrieval effect.
4. For ranking, report candidate-pool Recall@25 separately from top-1 exact accuracy and
   MRR. Test shuffled candidate orders.
5. For acceptance, report exact outcome accuracy, candidate precision, abstention
   precision, and errors by relationship scope and directive type.
6. Require every candidate method to beat Gemini 3.6 Flash on the same cases, with paired
   uncertainty intervals and no material loss in validation reliability. Prefer the
   simpler method when differences are statistically or substantively indistinguishable.
7. Keep all model IDs, reasoning settings, raw responses, validation errors, prompts,
   snapshot hashes, and review decisions in the existing provenance structure.

The production architecture should be selected only after those results. The leading
hypothesis is a strong frontier reasoner for ranking and acceptance, with a separately
selected structured extractor and a task-specific retrieval stack. The evidence is not yet
strong enough to choose the winner in advance.

## Bottom line

Using frontier models is more likely to help the **final grounded analogy and abstention
decision** than generic legal specialization is. The best legal-specific opportunity is
in embeddings or cross-encoder reranking, where domain language can improve which
candidates reach the judge. Fine-tuning becomes attractive only after the project owns a
large, carefully split set of reviewed parent and none cases.

Accordingly: test GPT-5.6 Sol, Claude Fable 5, and Gemini 3.7 Flash against the frozen
Gemini 3.6 baseline; keep extraction and judgment evaluations separate; add retrieval and
candidate-order ablations; and let blinded project-specific accuracy—not model branding
or generic legal benchmarks—determine the production method.

## Sources and evidentiary weight

### Project evidence

- [`methodology/child_parent_analysis_plan.md`](../../methodology/child_parent_analysis_plan.md)
- [`data/parent_analysis/FUNCTION_PROFILE_PARENT_PIPELINE.md`](../../data/parent_analysis/FUNCTION_PROFILE_PARENT_PIPELINE.md)

### Current official model documentation

- [OpenAI model catalog and GPT-5.6 family](https://developers.openai.com/api/docs/models)
- [Anthropic model overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- [Google Gemini 3.7 Flash guidance](https://ai.google.dev/gemini-api/docs/latest-model)
- [Google model-tuning guidance](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/tune-models)

Official model pages establish availability, configuration, and vendor-stated positioning;
they do not establish comparative performance on this project.

### Research evidence

- Guha et al., [LegalBench](https://hazyresearch.stanford.edu/legalbench/)
- Fei et al., [LawBench](https://aclanthology.org/2024.emnlp-main.452/)
- Chalkidis et al., [LEGAL-BERT](https://aclanthology.org/2020.findings-emnlp.261/)
- Chalkidis et al., [LexGLUE](https://aclanthology.org/2022.acl-long.297/)
- Niklaus et al., [LawInstruct](https://aclanthology.org/2025.findings-naacl.7/)
- Hu et al., [Evaluating Test-Time Scaling LLMs for Legal Reasoning](https://aclanthology.org/2025.findings-emnlp.742/)
- Oh et al., [Korean Canonical Legal Benchmark](https://aclanthology.org/2026.eacl-short.17/)
- Barale et al., [Do Language Models Learn about Legal Entity Types during Pretraining?](https://aclanthology.org/2023.nllp-1.4/)
- Gururangan et al., [Don't Stop Pretraining](https://aclanthology.org/2020.acl-main.740/)
- Hou et al., [CLERC](https://aclanthology.org/2025.findings-naacl.441/)
- Sun et al., [Is ChatGPT Good at Search?](https://aclanthology.org/2023.emnlp-main.923/)
- Yoon et al., [ListT5](https://aclanthology.org/2024.acl-long.125/)
- Tang et al., [Found in the Middle](https://aclanthology.org/2024.naacl-long.129/)
- COLIEE organizers, [The COLIEE 2025 Competition on Legal Information Extraction and Entailment](https://pubmed.ncbi.nlm.nih.gov/42023121/)
- Butler et al., [Legal RAG Bench](https://huggingface.co/papers/2603.01710), a recent
  preprint whose legal-retrieval findings should be treated as provisional and
  task-specific.

These external benchmarks motivate hypotheses and experimental controls. None substitutes
for blinded evaluation on the presidential-directive parent definition.
