# High-confidence parent-child pilot

## Next-session handoff: run the frozen Sol sample

The immediate next step is to run the already-frozen 100-child balanced HC sample; do not
rebuild or resample it. The package contains 20 children from each HC category and is
documented in `SOL_HC_PARENT_100_RUNBOOK.md`. No model calls have been made yet.

On the run machine, use an authenticated `codex` CLI and run:

```bash
python3 analysis/hc-parent-child/validate_sol_hc_parent_100.py
python3 analysis/hc-parent-child/run_sol_hc_parent_100.py --dry-run --limit 2
python3 analysis/hc-parent-child/run_sol_hc_parent_100.py --case-id SHC001
python3 analysis/hc-parent-child/run_sol_hc_parent_100.py
python3 analysis/hc-parent-child/score_sol_hc_parent_100.py --require-complete
```

The runner is resumable and pins `gpt-5.6-sol` with low reasoning. Web search is disabled
because this is a controlled comparison over the supplied, blinded candidate sets. Before
running the remaining 99 cases, inspect the SHC001 response and logs as described in the
runbook. Do not expose `sampled_children.csv`, `candidate_pool_key.csv`, or `manifest.json`
to the model; those files restore hidden labels only during scoring.

## Executive summary: methods, work completed, and preliminary findings

### Objective

The project asks what proportion of presidential directives show sufficiently strong
evidence of path-dependent drafting to be counted with confidence.  The analysis never
uses the vesting clause to identify directive categories, retrieve parents, score text
reuse, or conduct human review.

The interview-supported recurring categories—IEEPA actions, property blocking, formal
emergency-status actions, national-monument actions, and operative trade
proclamations—are **positive controls**.  They are not themselves the final
path-dependency estimate.  They provide an independently motivated place to test whether
non-vesting text reuse and parent retrieval behave as a path-dependency measure should.

### Methods implemented

1. **Authority-safe preprocessing.** Formal vesting clauses and generic directive
boilerplate are removed before any matching or review. A robustness version additionally
masks remaining authority references.
2. **Deterministic HC-category rules.** The five overlapping categories are assigned using
titles and non-vesting text only. Rules require an action rather than a topic mention; the
current codebook excludes, for example, emergency aid/funding, emergency recitals,
incidental IEEPA mentions, hypothetical asset freezing, and ceremonial trade language.
3. **Observed links.** Amendments, modifications, continuations, replacements,
revocations, and supersessions with resolved earlier directives are recorded as observed
parent-child edges and excluded from inferred-parent scoring.
4. **Parent candidate retrieval.** For no-explicit-link children, the pipeline ranks all
strictly earlier eligible directives using distinctive IDF-weighted word reuse and frozen
semantic similarity. It now preserves the top five candidates under three specifications:
5-word reuse, the original 10-word/semantic hybrid, and a 5-word/semantic hybrid.
5. **Category validation.** Development, family holdout, targeted IEEPA, and
category-blind HC-union reviews were completed. Raw decisions, scope adjudications, and
all replacements are retained. Rules revised using a review are labeled development
evidence rather than independent validation.
6. **Parent and method validation.** A preliminary parent-pair review, a 200-child masked
known-edge retrieval benchmark, and a matched HC-versus-non-HC signal comparison test
different parts of the design. They are not pooled or treated as interchangeable evidence.

### Work completed

- Built the deterministic HC-union classifier and executable codebook.
- Created browser-based, full-text, vesting-blinded review forms and preserved all review
decisions and hidden keys.
- Identified and corrected several rule false positives revealed in review: incidental
emergency assistance/relief, emergency-program language, hypothetical asset freezing,
incidental IEEPA references in arms-transfer policy, and delegated-but-withheld emergency
authority.
- Separated observed direct-transition links from inference candidates.
- Generated top-five candidate sets for every current pilot child under the three retained
methods.
- Benchmarked retrieval methods after masking directive identifiers and references:
5-word distinctive reuse is the strongest tested standalone method.
- Built machine-readable answers to the five research questions in
`outputs/research_question_summary.csv` and a plain-language account in
`RESEARCH_QUESTIONS.md`.

### Preliminary results

| Quantity | Result | Interpretation |
|---|---:|---|
| Nonceremonial corpus | 13,461 | Requested full denominator |
| Scoped corpus | 13,086 | Excludes narrow personal/diplomatic correspondence scope |
| HC-union directives | 1,577 | 11.72% of full corpus; 12.05% of scoped corpus; category coverage, not path-dependency prevalence |
| HC directives with observed direct-transition parents | 456 | 28.9% of HC union |
| HC directives requiring inference | 1,121 | 71.1% of HC union |
| Pilot HC children with same-family top-one candidate | 192/236 (81.4%) | Mechanical face-validity result, not confirmed parentage |
| Pilot HC children with same-family candidate in top five | 213/236 (90.3%) | Candidate-set retrieval result, not confirmed parentage |
| HC median 5-word reuse / matched-control median | 0.221 / 0.0966 | HC controls show moderate reuse enrichment (AUC 0.652) |
| Masked known-edge retrieval with 5-word reuse | R@1 50%; R@5 70%; R@10 75% | Auxiliary retrieval benchmark, not a substantive HC benchmark |
| Observed direct-transition children | 2,382 | 17.7% of full nonceremonial corpus; observed lineage lower bound only |
| Outside-HC directives above HC-median 5-word reuse | 3,480/9,583 (36.3%) | Exact descriptive HC-like-reuse count; not a path-dependency estimate |

The reduced-review pilot does **not** yet support a high-confidence inferred numerator for
path dependency outside observed links. A predeclared 90%-precision parent-selection rule
failed on development data: the best rule selecting at least 20 known-edge cases achieved
21/24 (87.5%). Consequently, no inferred corpus-wide path-dependency estimate is currently
claimed. The full non-HC 5-word reuse calculation described below is descriptive: exceeding
the HC median is evidence of HC-like reuse, not proof of path dependency.

### Current analytical sequence

```text
HC positive-control categories → candidate-set and reuse validation
                                      ↓
                       validate plausible drafting parents in HC cases
                                      ↓
                 freeze a substantive path-dependency rule, if supported
                                      ↓
               apply it outside HC categories and estimate the final proportion
```

Until the parent-validation gate is met, category coverage, observed links, and reuse
enrichment are reported separately rather than combined into a path-dependency prevalence
claim.

The exact descriptive full-corpus calculation for the current HC-median reuse threshold is
generated with:

```bash
.venv-parent-analysis-local/bin/python \
  analysis/hc-parent-child/score_full_nonhc_word5.py
```

It scores all scoped, no-explicit-link directives outside the HC union against strictly
earlier scoped directives and writes `full_nonhc_word5_reuse.csv` plus a summary.  The
threshold is the HC-pilot median best-earlier 5-word reuse score (0.22067); exceedance is
reported as HC-like reuse, never as a path-dependency classification.

`0.22067` is calculated from the 236 no-explicit-link HC pilot children.  For each child,
the pipeline compares its non-vesting text with every strictly earlier eligible directive,
finds the best 5-word distinctive-reuse candidate, and records that candidate's score.  The
median of those 236 best-candidate scores is 0.2206716686.  Thus, half of the HC pilot has
a best earlier candidate above this value and half below it.  The score is the share of the
child's IDF-weighted unique 5-word phrases that occur in the best earlier candidate.  It is
neither a probability of path dependency nor a threshold learned from confirmed
path-dependent cases; it is a descriptive reference point for asking whether an outside-HC
directive has at least as much reuse as the typical HC pilot directive.

## Research question

This analysis looks for presidential directives with unusually strong evidence of
path-dependent drafting.  The motivating hypothesis is that recurring actions are often
drafted from a prior example, so a later directive should resemble an earlier directive
in both its operative function and its non-generic language.

The five categories identified in White House/OLC interviews define a single
high-confidence (HC) union:

1. IEEPA actions;
2. property blocking;
3. declarations, continuations, modifications, and terminations of emergencies;
4. national-monument actions; and
5. operative trade proclamations.

The primary estimand is whether a directive belongs to **any** of these categories, not
which category is the best description.  The categories overlap substantially: the same
sanctions action may be an IEEPA, blocking, and emergency action.  Individual labels are
retained only as descriptive and rule-development tags.  The union validates the parent
metric; it does not define that metric.

More precisely, HC-union membership is an intermediate positive-control designation, not
the study's ultimate dependent measure.  The principal estimand is the proportion of the
eligible corpus for which non-vesting evidence supports path-dependent drafting.  The
research design is: identify interview-supported recurring controls; validate and freeze a
parent-retrieval/evidence rule on those controls and known explicit edges; apply that rule
to the full eligible corpus; and then describe recurring functions among qualifying
directives outside the original controls.  Corpus accounting must separately report
observed explicit links, inferred qualifying controls, and inferred qualifying directives
outside the controls, without double counting.

## Non-negotiable leakage rule

The vesting clause is never an input.  It is removed before family matching, shingling,
embedding lookup, sampling, or human review.  Review exports contain only the resulting
text.  References to authority elsewhere in the directive are permitted.

For reporting letters, a statute-led authority formula immediately preceding a presidential
performative is also treated as a formal clause: for example, `Pursuant to …, I hereby
report` becomes `I hereby report`.  This prevents authority recitations from entering a
review merely because the document uses a reporting-letter format.

Two specifications are retained:

- **primary:** remove the vesting clause and generic similarity boilerplate, retaining
  authority references elsewhere;
- **authority-masked robustness:** additionally mask all residual authority citations.

Titles may help identify positive-control families, but title text is not included in the
copying score.  Boilerplate such as general-provisions limitations is removed because its
reuse is evidence of directive form, not a distinctive drafting parent.

## Population and existing assets

The combined corpus contains 20,232 directives.  The existing ceremonial codebook removes
6,771, leaving the requested denominator of **13,461 non-ceremonial directives**.

The parent-analysis artifacts supply:

- cleaned non-ceremonial documents and operative segments;
- 9,762 directives with at least one extracted operative segment;
- 9,640 validated Gemini function profiles, with 122 operative profiles still unresolved;
- pinned Qwen function embeddings for those profiles; and
- an older full-document Qwen cache covering 12,265 development-corpus documents.

The profile snapshot is incomplete, so this is a pilot rather than a final population
estimate.  Operative children with profiles use the function-profile score.  Documents
without profiles use the older full-document embedding only when it is available and are
reported in a separately calibrated `document_semantic` stratum.  Missing holdout document
embeddings remain explicitly unscored; they are never silently treated as negative cases.

Earlier work in `analysis/recurring_functional_actions/` used a 560-document sample and
proposed emergency, property-blocking, and monument families.  Its labels were explicitly
provisional.  This package leaves that analysis intact, expands the controls to IEEPA and
trade, uses the combined non-ceremonial population, and separates family validation from
the general parent score.

## Family codebook

Family labels can overlap.  A sanctions order may be both an IEEPA action, an emergency
action, and a property-blocking action.  A match on any label places the directive in the
HC union.  Exact-label performance is secondary because disagreement between two
applicable labels is not substantively important for this project.

The deterministic rules use titles, permitted body text, and frozen function-profile
fields.  They require an action, not a topic mention:

- IEEPA requires a stated IEEPA-linked restriction, status action, report, notice, or
  transmittal;
- blocking includes property blocking/freezing and operative sanctions-related import,
  export, transaction, investment, trade, entry, or dealings restrictions;
- emergency requires a formal declaration, continuation, renewal, modification, or ending
  of emergency status—not preparedness, response, funding, or reporting activity;
- monuments require establishing, reserving, enlarging, or modifying a national monument;
- trade proclamations require an operative adjustment involving tariffs, duties, quotas,
  preferences, imports, or the tariff schedule.

`family_codebook.csv` contains the substantive definitions and exclusions.  The regular
expressions in `build.py` are the executable version.  The first 100 judgments are a
rule-development round.  The first 50-case holdout was subsequently used as exploratory
evidence when the focused parent review exposed additional false family assignments.  The
v2 rules are frozen before a fresh holdout of up to 50 judgments, disjoint from the
development round, the first holdout, and the focused parent-review children; only that
v2 holdout supplies post-revision family validation.  If a family has fewer remaining
hard-boundary documents, the holdout records the shortfall rather than reusing reviewed
documents or substituting weaker negatives.

### V2 family-holdout results

The completed v2 holdout contains 46 judgments.  This review originally asked about the
sampling category rather than the HC union, so the table is retained as rule-development
evidence, not as the primary validation result.  In particular, a case judged to be an
emergency rather than IEEPA is not an HC-union error.  Rates below are descriptive agreement
within the deterministic stratified holdout; they are not population precision or recall
estimates.  Uncertain judgments are excluded from rate denominators.

| Family | Proposed members | Proposed agreement | Boundary members | Boundary member rate |
|---|---:|---:|---:|---:|
| IEEPA action | 5/5 | 100% | 4/4 (1 uncertain) | 100% |
| Property blocking | 4/5 | 80% | 0/5 | 0% |
| Emergency action | 4/5 | 80% | 0/5 | 0% |
| National monument action | 4/5 | 80% | 0/1 | 0% |
| Trade proclamation | 5/5 | 100% | 0/5 | 0% |

The trade rule has no sampled disagreement.  Property, emergency, and monument each have
one proposed false positive.  The IEEPA rule has strong false-negative evidence: its hard
boundaries include reporting letters whose IEEPA/action evidence appears in separate text
windows.  Revising any rule using these judgments converts v2 into development evidence
and requires a new disjoint holdout before making post-revision validation claims.

The targeted v3 rule permits the report/transmittal and outside-vesting IEEPA reference to
appear in separate text windows only for first-person reporting letters.  A 10-case
IEEPA-only v3 holdout (5 proposed and 5 hard boundaries) is disjoint from all prior family
development, v1/v2 holdouts, and reviewed family-parent children.

The completed v3 decisions are also scored against the primary HC-union estimand.  Raw
category-specific judgments are never overwritten.  When a contemporaneous review note
explicitly identifies another HC category, the separate union adjudication counts the case
as a member; unexplained uncertain cases remain uncertain.  This yields 5/5 union members
in the proposed stratum and 3/3 among adjudicated boundary cases, with 2 boundary cases
still uncertain.  These are targeted diagnostics, not population accuracy estimates.

Reproduce the join and summary with:

```bash
.venv-parent-analysis-local/bin/python \
  analysis/hc-parent-child/score_family_holdout.py

.venv-parent-analysis-local/bin/python \
  analysis/hc-parent-child/score_hc_union_holdout.py
```

## Parent metric

For each pilot child, all strictly earlier eligible documents are possible parents.
Same-day documents are excluded because their drafting order is not observable.  Parent
document type is unrestricted.

### 1. Distinctive text reuse

The body is tokenized into unique 10-word shingles.  A shared shingle receives inverse
document-frequency weight

`log((N + 1) / (df + 1)) + 1`,

where `N` is the 13,461-document population.  The raw reuse score is the shared weighted
mass divided by the child's total weighted shingle mass.  Common language therefore
contributes less than family-specific phrases, and scores are length-normalized.

### 2. Function or document similarity

For an operative-profile child, every child operative function is compared with every
parent operative function using the frozen query/document Qwen embeddings.  The best
parent match for each child function is retained and those maxima are averaged.  This
directed score asks how well the parent covers the child's actions without requiring the
child to reproduce everything in a longer parent.

For a child without a function profile, the pilot uses frozen full-document query/document
cosine similarity when both embeddings exist.  This is a separate stratum because it is
not interchangeable with function similarity.

### 3. Combined score

Within each child's eligible parent set, both raw signals are converted to midrank
percentiles.  The combined score is their equal-weight arithmetic mean.  The selected
parent has the highest combined score; exact ties break on numeric document ID.

The inference analysis is restricted to children with **no resolved explicit
direct-transition link** to an earlier directive.  A resolved amendment, modification,
continuation, replacement, revocation, or supersession is instead recorded as an observed
parent-child edge in `explicit_parent_child_edges.csv`; it receives no copying score and
never enters the blinded parent review or score calibration.  A bare citation/discussion
of another directive remains eligible because reference alone is not a direct lineage
claim.  Explicit-link directives may still be candidate parents for a later child with no
such link.

## Reduced human review

The reduced design begins with about 120 new judgments and permits at most 270.

### Family review

The current primary validation is a 20-case, category-blind HC-union holdout: 10 proposed
union members and 10 hard boundary cases, disjoint from all earlier family and parent-pair
review material.  The reviewer decides only whether each directive belongs to any HC
category.  The triggering category and proposed/boundary stratum remain in the hidden key.

The completed review confirmed 8/10 proposed cases.  Among boundary cases, 3/9
adjudicated cases were union members and one was uncertain.  This is both false-positive
and false-negative evidence for the current deterministic rules.  Because the sample is
deliberately concentrated on proposed and difficult boundary cases, these rates are rule
diagnostics—not estimates of population precision, recall, prevalence, sensitivity, or
specificity.  After the two narrow false-positive corrections described below, the current
1,621-document union count remains provisional.

Error analysis found two unambiguous emergency-rule false positives.  One directive only
recounted that a prior presidential action `was to declare` an emergency while proclaiming
an awareness month; another expressly excluded the `authority to declare` an emergency
from a delegation.  The revised rule removes those two non-action constructions before
applying the historical formal-action grammar.  This narrow correction preserves older
termination letters, reporting letters, Stafford declarations, and proclamations whose
performative syntax differs from modern orders.

The three reviewed boundary members are not mechanical misses under the stated
formal-national-emergency codebook: they concern the Emergency Refugee and Migration
Assistance Fund, an emergency-budget designation, and a COVID entry restriction reciting
a WHO public-health emergency.  Adding them would broaden the substantive HC union beyond
declarations, continuations, modifications, and terminations of emergency status.  They
are retained as a separate taxonomy question rather than silently added to the rule.  The
remaining uncertain case is an immigration-enforcement order loosely triggered by
`block` language and supplies no basis for a rule change.

The substantive scope decision is now frozen: these broader emergency-related actions
remain outside the HC union.  The original reviewer decisions are preserved, while
`hc_union_scope_adjudications.csv` records the separate codebook adjudication.  After the
two mechanical corrections and this scope decision, the revised rules agree with all 19
adjudicated cases; one case remains uncertain.  Because both the rule and scope were
revised using this sample, that 19/19 figure is development evidence—not fresh holdout
validation.

A final 10-case confirmatory union holdout is frozen after these revisions.  It contains
5 proposed and 5 hard-boundary cases, excludes every document shown in prior family,
union, and parent-pair review material, and hides both sampling category and stratum.  It
is the post-revision validation sample; no further rule adjustment should be evaluated on
it without relabeling it as development evidence.

The initial confirmatory draw inadvertently included two proposed cases with resolved
amendment/revocation edges.  They are genuine HC actions but are outside the stipulated
no-explicit-link inference universe, and the review task was consequently ambiguous.  The
raw judgments are preserved and the cases are excluded—not scored as family-rule errors.
`confirmatory_scope_adjudication.csv` records the correction.  Two frozen, unseen proposed
replacements are drawn after excluding every resolved direct-transition child; the other
eight original confirmatory judgments remain usable.

Both replacement cases were judged HC-union members.  The final corrected confirmatory
diagnostic therefore agrees with the frozen rule in all 10 cases: 5/5 proposed members and
0/5 boundary members.  The two replacement judgments were supplied directly by the
reviewer in chat on August 23, 2026; that provenance is recorded in the decision file and
final manifest.  This stratified result supports the revised rule but is not a population
precision, recall, or prevalence estimate.

### Preliminary parent-pair result

The frozen 20-pair review yielded 3 plausible parents, 10 nonparents, 3 uncertain
relationships, and 4 scope/family exclusions.  The observed plausible-parent rate is
therefore 3/13 (23.1%) among relationship-adjudicated pairs.  Scope exclusions and
uncertain cases are not coded as failed parent retrievals.  This is a deliberately
stratified preliminary diagnostic, not a population success rate or a calibrated
precision estimate.

The parent screen also supplies additional family-rule development evidence.  Several
documents entered through incidental emergency language, a hypothetical asset-freezing
discussion, or Red Cross emergency-relief language rather than an HC action.  These cases
do not invalidate the separately frozen 10-case confirmatory family diagnostic, but they
show that the proposed population union count remains sensitive to rule false positives
outside that small sample and should not be presented as a validated prevalence estimate.

### Deterministic method comparison

Seven reproducible rankings are compared on 200 children with known explicit parents.
Directive-number and named-order references are masked before scoring, and vesting text is
already absent.  This prevents trivial recovery from a citation.  The benchmark measures
whether the known parent ranks first or within the top 5/10; it tests retrieval mechanics,
not whether explicit transitions are substantively identical to implicit drafting ancestry.

| Method | R@1 | R@5 | R@10 | MRR |
|---|---:|---:|---:|---:|
| 5-word distinctive reuse | **50.0%** | **70.0%** | **75.0%** | **0.594** |
| 10-word reuse + semantic | 43.0% | 61.5% | 69.5% | 0.522 |
| 5-word reuse + semantic | 42.0% | 63.0% | 71.5% | 0.524 |
| 10-word distinctive reuse | 46.0% | 62.0% | 67.0% | 0.534 |
| Semantic only | 38.0% | 57.0% | 65.0% | 0.468 |
| Section headings only | 17.0% | 30.0% | 34.0% | 0.233 |
| 10-word + semantic + headings | 40.0% | 57.0% | 65.0% | 0.483 |

Five-word distinctive reuse is the strongest standalone alternative and the best method by
mean reciprocal rank.  The existing 10-word/semantic hybrid ties its top-1 recovery but is
weaker at rank 5.  Section headings can be persuasive case-specific evidence but are too
generic as a general ranking signal and slightly reduce hybrid benchmark performance.

### Exploratory text-OR-function calibration

The first function-OR baseline uses the canonical authority-blind operative-function
embeddings.  For each unique HC or matched-control child with a usable profile, it compares
the child's functions with every strictly earlier scoped profiled directive.  The function
score is the mean, across child functions, of the best parent-function embedding match; the
margin is the best directive score minus the second-best score.  Reused matched controls are
collapsed before calibration, leaving 236 unique HC children and 98 unique controls.  Of
these, 221 HC children and 82 controls have usable operative profiles and earlier candidates.

This broad function score provides only weak HC/control separation: the HC median is 0.716,
the control median is 0.684, and AUC is 0.572.  A provisional development search held the
five-word cutoff fixed at 0.22067 and allowed the function-only branch to add no more than 5%
of development controls.  Its selected function threshold (0.82624) and margin (0.01920)
added 2/115 development HC cases beyond text, but **0/106 held-out HC cases**; it added one
control in each split.  This baseline therefore does not justify a functional OR branch.
The next test should use structured action/mechanism/effect alignment and function rarity,
then repeat branch-specific parent review.  No cutoff in this exploratory artifact is frozen
for prevalence estimation.

Reproduce the calibration with:

```bash
.venv-parent-analysis-local/bin/python \
  analysis/hc-parent-child/calibrate_function_or_rule.py
```

The script writes unique-child signals, an exhaustive candidate-cutoff grid, a summary, and
a hash manifest under `outputs/`.

The 10 reviewed nonparents separate into three HC-family false positives, one missed
explicit/reporting link, one likely and two possible ranking failures, one left-censored
case, one case with no visible same-topic parent, and one high-similarity template rejection
that exposes a parent-rubric question.  `nonparent_case_audit.csv` records the evidence and
`nonparent_alternative_rankings.csv` preserves the ranked candidates.

### High-confidence rule result

The 200 masked explicit-edge cases are deterministically split into 100 development and
100 untouched holdout children.  The predeclared rule search requires agreement among the
three preferred methods plus minimum 5-word reuse and top-candidate-margin cutoffs.  A
qualifying rule must select at least 20 development cases at at least 90% known-parent
precision.  No rule meets both requirements, so no inferred high-confidence tier is frozen
and holdout outcomes are not used for retuning.

The best post-run development trade-off selecting at least 20 cases reaches 21/24 (87.5%).
More selective post hoc rules can exceed 90% on only 13–15 development cases, but those
samples are too small to substantiate a 90%-confidence claim and have wide uncertainty.
They are not applied corpus-wide.  Consequently, the presently defensible corpus statistic
is an observed-link lower bound: 2,382 direct-transition children, or 17.7% of all 13,461
nonceremonial directives and 18.2% of the 13,086 scoped directives.  This is not evidence
that no additional directives are path dependent; it means the pilot does not yet support
a high-confidence inferred numerator.

Build its queue and browser form with:

```bash
.venv-parent-analysis-local/bin/python \
  analysis/hc-parent-child/build_hc_union_holdout.py
.venv-parent-analysis-local/bin/python \
  analysis/hc-parent-child/build_review_html.py \
  --output analysis/hc-parent-child/outputs/hc_union_holdout \
  --family-only \
  --family-download-name hc_union_holdout_decisions.csv
.venv-parent-analysis-local/bin/python \
  analysis/hc-parent-child/score_hc_union_validation.py
```

The initial queue contains 12 proposed matches and 8 boundary cases for each control
family: 100 family judgments.  Add 10 cases for a family only when its first review finds
more than one false positive among proposed members or more than two family members among
the boundary cases.  The maximum is 150.

The reviewer-facing queue asks whether the directive belongs to any HC category.  It hides
both the category used to sample the case and whether the document was a rule match or a
boundary case.  It shows the complete preprocessed non-vesting text, rather than a keyword
excerpt, so union membership can be judged in context.  The sampling assignment is kept separately in
`family_review_key.csv` and should not be opened until decisions are frozen.

### Parent-pair review

The preliminary blinded queue contains 20 no-explicit-link pairs whose children fall in at
least one current high-confidence family.  It asks whether the selected earlier directive
is a plausible drafting parent for that family member.  Non-family directives are not
negative cases: they belong to a later family-discovery workflow and are not sampled here.
This is a directional screen for obvious false positives, not a basis for 90%/95%
precision claims.  Add 20-pair batches near prospective thresholds only if needed for
within-family diagnostic evidence, up to 120 new pair judgments.  Existing reviewed pairs
may be reused only when the exact child-parent pair and substantive rubric agree.

The 20-row preliminary queue is a deterministic prefix of the 40-, 60-, 80-, 100-, and 120-row
queues.  Additional batches can therefore be generated without changing already assigned
pair IDs:

```bash
.venv-parent-analysis-local/bin/python analysis/hc-parent-child/build.py \
  --parent-review-count 60
```

The reviewer sees no score, family label, method label, or vesting text.  `Not an HC-family
case` flags a false-positive family assignment; it is excluded from calibration rather than
treated as a negative parent relationship.  The legacy `Out of scope` choice is retained
only to preserve earlier decision files.  Explicitly personal or diplomatic
correspondence—identified conservatively from titles—is excluded as both a child and a
candidate parent.  Formal congressional/statutory correspondence remains in scope.
This is not a claim that every letter is out of scope: a letter remains eligible unless it
has an explicit personal/diplomatic cue.
The family-focused parent screen is never used to fit population-wide score thresholds.
Family membership is assessed through the separate family review and holdout.

The completed non-family 40-pair scope-development screen is retained as
`parent_pair_noncontrol_scope_screen.csv`.  It established that non-family directives are
not suitable negatives for this stage; it is not pooled with the family-focused review.

After review, the build reports the most inclusive score cutoffs attaining at least 90%
and 95% observed precision within each stratum, provided at least 25 reviewed pairs lie
above the cutoff.  These are **pilot-calibrated tiers**, not proof of population precision.
Reviewed counts and uncertainty must accompany them.

Before review, summary tables use the 90th, 95th, and 97.5th percentiles of selected-parent
scores only as descriptive diagnostics.  These score quantiles are not precision tiers.

### Trade-offs from the smaller review

Reducing review produces wider precision intervals, makes thresholds more sensitive to a
few judgments, weakens evidence for rare family subtypes and older administrations, and
is particularly limiting for the document-semantic stratum.  Continuous scores, review
counts, exact decisions, and unused queues are preserved so later review can extend the
same frozen design.  No threshold is adjusted merely to make the controls look successful.

## Validation and interpretation

For the primary analysis, an eligible child is an HC-union member with at least one
strictly earlier HC-union member.  The earliest observed union member is left-censored and
excluded from the recovery denominator.

Primary recovery requires that the child's unrestricted selected parent:

1. clears the relevant score tier; and
2. independently belongs to any HC category.

`hc_union_summary.csv` reports this primary result.  Exact same-family recovery remains in
`family_validation.csv` as a secondary diagnostic only; cross-category recovery is not an
error.  The best within-family parent is also retained for diagnosis.
Administration counts and years spanned describe regularity; they are not hard gates and
need not imply that literally every president used the action.

The principal coverage statistic is reported three ways:

`number of tier-qualified children / 13,461`, using the full non-ceremonial universe;
the same numerator over the universe after the explicitly scoped-out personal/diplomatic
correspondence is removed; and the primary inferential rate over the remaining
no-explicit-link child universe.  The manifest records all denominators, the scope
exclusion count, and the observed direct-edge totals by relationship type.

Operative-profile, document-semantic, and unscored counts are always shown separately.
Until profile and embedding gaps are closed and human review is complete, all coverage
figures are provisional.

## Reproduction

From the repository root:

```bash
.venv-parent-analysis-local/bin/python analysis/hc-parent-child/build.py
.venv-parent-analysis-local/bin/python -m unittest analysis/hc-parent-child/test_build.py
```

To apply completed parent reviews:

```bash
.venv-parent-analysis-local/bin/python analysis/hc-parent-child/build.py \
  --reviewed-pairs /path/to/parent_pair_decisions.csv
```

## Browser review forms

The generated standalone forms are [family_review.html](outputs/family_review.html)
and [parent_pair_review.html](outputs/parent_pair_review.html).  Open each in a browser.
They show one blinded case at a time, save choices and notes in that browser while you
work, and download a compact decisions CSV.

Regenerate the forms after rebuilding the queues:

```bash
.venv-parent-analysis-local/bin/python analysis/hc-parent-child/build_review_html.py
```

Download the parent-pair decisions as `parent_pair_decisions.csv` and pass that file to
`--reviewed-pairs` using the command above.  The family download is a coding record for
freezing or revising the deterministic family rules; keep it with the study materials.
Do not open `family_review_key.csv` or `parent_pair_review_key.csv` until the relevant
review decisions are frozen.

After revising the family rules from the 100-case development review, build the disjoint
50-case post-revision holdout and its reviewer page:

```bash
.venv-parent-analysis-local/bin/python analysis/hc-parent-child/build_family_holdout.py
.venv-parent-analysis-local/bin/python analysis/hc-parent-child/build_review_html.py \
  --output analysis/hc-parent-child/outputs/family_holdout \
  --family-only \
  --family-download-name family_holdout_decisions.csv
```

The holdout excludes every directive seen in the development review and contains five
proposed and five boundary cases for each family.  Its key must remain closed until those
50 decisions are frozen.  The completed development queue, key, and decisions are retained
under `outputs/family_development/` so a later full pilot rebuild cannot overwrite them.

The build writes only beneath `analysis/hc-parent-child/outputs/`.  `manifest.json` freezes
input hashes, snapshot identity, parameters, samples, score strata, missingness, and output
hashes.
