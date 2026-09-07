# Research questions and current answers

This document separates five stages that must not be conflated.  All text-based inputs
exclude the vesting clause.

## (a) How well can we identify the high-confidence categories?

The final small category-blind confirmatory diagnostic agreed in 10/10 cases after two
explicit-link cases were replaced.  Subsequent parent-review error analysis exposed and
removed additional incidental IEEPA, emergency, and hypothetical-blocking matches.  Those
narrow changes improve face validity but mean that 10/10 is not a precision estimate for
the exact current rule.  The defensible conclusion is that category identification is
promising and auditable, but its population precision/recall is not estimated by the small,
stratified review.

## (b) What proportion of the corpus do these categories make up?

The corrected deterministic union contains **1,577 directives**:

- 11.72% of all 13,461 nonceremonial directives;
- 12.05% of the 13,086 scoped directives;
- 456 (28.9% of the union) have a resolved direct-transition parent; and
- 1,121 (71.1%) have no resolved direct-transition link and require parent inference.

These are category-coverage figures, not estimates of path-dependency prevalence.

## (c) Can we identify parents for HC directives?

The current scorable HC pilot contains 236 no-explicit-link children.  Under 5-word
distinctive reuse:

- 192/236 (81.4%) have a same-family candidate ranked first; and
- 213/236 (90.3%) have a same-family candidate somewhere in the top five.

This is strong mechanical face validity, but a same-family predecessor is not necessarily
the true drafting parent.  The earlier 20-pair human review cannot supply a clean answer:
it used the pre-correction classifier, included scope false positives, and reviewed only
one candidate per child.  Thus parent identification is currently demonstrated as
candidate retrieval, not validated parent assignment.

## (d) Are there deterministic signals that help identify those parents?

Yes, as an enrichment result.  The 236 HC pilot children are deterministically matched to
non-HC pilot controls on document type, president where possible, date, and approximate
text length.  HC children show stronger signals:

| Signal | HC median | Control median | AUC |
|---|---:|---:|---:|
| 5-word distinctive reuse | 0.221 | 0.0966 | 0.652 |
| Top-1 versus top-2 reuse margin | 0.0209 | 0.00875 | 0.610 |
| Cross-method consensus | 2 methods | 1 method | 0.573 |

The masked 200-edge engineering benchmark independently finds that 5-word reuse is the
best tested retrieval method, recovering a known parent at rank 1 in 50%, the top five in
70%, and the top ten in 75%.  Together these results show that distinctive short-phrase
reuse is useful.  They do not yet establish a threshold at which an implicit candidate is
known to be a real drafting parent.

## (e) How many outside-HC directives meet a validated path-dependency signal?

**Not yet estimable as path dependency.** There are 9,583 scoped, no-explicit-link
directives outside the HC union.  The exact full-corpus 5-word calculation finds that
**3,480/9,583 (36.3%)** exceed the HC-pilot median best-earlier reuse score of 0.22067.
This is a useful descriptive count of HC-like reuse, with an auditable parent candidate for
every case; it is not a path-dependency classification. Applying the cutoff as if it were
one would turn positive-control enrichment into an unsupported prevalence estimate.

The remaining gate is a small, category-correct parent-candidate validation: review the
top-five set for sampled HC children and determine whether at least one is a plausible
drafting template.  If that validates a deterministic rule, freeze it and apply it to the
9,583 outside-HC directives.  If it does not, report the descriptive 3,480 count, (b), and
the observed-link counts but do not manufacture a path-dependency estimate.

## Reproducible artifacts

- `outputs/research_question_summary.csv`: machine-readable answers and statuses.
- `outputs/hc_matched_signal_pairs.csv`: deterministic matches.
- `outputs/hc_matched_signal_summary.csv`: signal enrichment.
- `outputs/top5_candidate_sets.csv`: three methods and five candidates per pilot child.
- `outputs/deterministic_method_benchmark_summary.csv`: auxiliary known-edge retrieval.
