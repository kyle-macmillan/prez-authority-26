# Comparison with the prior presidential-delegation estimate

## Bottom line

The prior review and this recipient-focused analysis point in the same direction:
formal vesting-clause citations overwhelmingly involve presidential authority. They do
not yet establish the same, final corpus-wide percentage because they use different
units, coding rules, and historical-source coverage.

The important conceptual refinement is that a statute can confer authority on the
President **and** independently assign a relevant function to an agency or officer.
Accordingly, a citation that supports presidential action is not necessarily a
President-only delegation.

## Side-by-side methods

| Feature | Prior estimate | Recipient-focused analysis |
|---|---|---|
| Core question | Whether the cited provision confers, requires, conditions, or otherwise structures a presidential function | Who receives affirmative statutory power: the President, an agency/officer, both, or neither? |
| Primary unit | Pinpoint textual citation occurrence in a vesting clause | Normalized pinpoint authority unit per clause |
| Parallel Act/U.S.C. forms | Treatment not fully documented | Count once when the forms identify the same provision in one clause |
| Clause population | 4,036 directives with recognized section-specific clauses | 3,808 directives with parsed pinpoint authority units |
| Pinpoint denominator | 4,130 occurrences | 5,405 authority-unit occurrences |
| Broad references | 756, held out of the pinpoint estimate | 1,056, held out of the primary recipient result |
| Statutory source work | Primarily current Code; contemporaneous audit acknowledged as incomplete | Official OLRC XML current-text extraction, amendment screening, and documented manual overrides; unsupported historical cases remain unresolved |
| Status | Preliminary 96% estimate | Coverage-qualified recipient census, not a complete historical census |

The differing raw counts do not themselves show disagreement. They reflect different
clause filters, corpus state, citation parsing, subsection normalization, and the
recipient method's deliberate collapse of parallel citation forms.

## Results compared

The prior review estimated that roughly 3,950–4,000 of 4,130 pinpoint citations
(about 96%) conferred, required, conditioned, or structured a presidential function.
It described that figure as provisional because a complete contemporaneous statutory
audit had not been completed.

The recipient-focused analysis has currently resolved 2,834 of 5,405 pinpoint
authority-unit occurrences (52.4%). Of the 2,756 resolved occurrences that confer
affirmative power:

| Recipient classification | Occurrences | Share of resolved power conferrals |
|---|---:|---:|
| President only | 2,413 | 87.6% |
| Agency/officer only | 25 | 0.9% |
| Both President and agency/officer | 318 | 11.5% |

Two derived comparisons are useful:

- If the question is whether a provision contains **any** presidential power,
  President-only plus shared provisions equal 99.1% of resolved power conferrals.
  This is directionally consistent with the prior conclusion that presidential
  authority dominates these citations.
- If the question is whether a provision confers power on the **President rather
  than an agency**, the relevant President-only figure is 87.6%; 11.5% are shared
  rather than President-only. Restricting the comparison to exclusive recipient
  grants yields 99.0% President-only and 1.0% agency/officer-only.

Thus, the two analyses are not directly competing estimates. The earlier 96% figure
uses a broad presidential-function category. The recipient-focused analysis identifies
the subset that is President-only and preserves shared authority as its own category.

## Why some citations remain unresolved

The 2,571 unresolved pinpoint occurrences do **not** mean that they are likely agency
authority. They lack enough provision-specific and contemporaneous support for a
recipient classification:

| Reason | Occurrences |
|---|---:|
| Act-section citation not yet mapped to a U.S. Code or Statutes at Large provision | 1,259 |
| Current U.S. Code section missing, generally because repealed, transferred, or renumbered | 392 |
| U.S. Code subsection locator not yet matched in the OLRC XML | 79 |
| Current text exists but historical timing or actor-power interpretation remains unresolved | 841 |

The largest examples are historical/repealed provisions (for example, former 16 U.S.C.
§§ 431 and 471), historical Internal Revenue Code provisions, and ambiguous shorthand
such as “section 7 of the Act.” Broad references are held out separately and are not
included in this unresolved count.

Because unresolved occurrences are concentrated in historical and ambiguous references,
they are not a random missing sample. It would be unsound to extrapolate the resolved
87.6%, 99.0%, or 99.1% figures to the entire corpus.

## Defensible current statement

> The source-supported portion of the recipient census indicates that nearly all
> statutory provisions conferring power on an exclusive executive recipient confer it
> on the President. A meaningful minority of resolved power-conferring citations also
> assign an independent agency or officer function. The evidence supports the broader
> conclusion that presidential authority predominates in formal vesting-clause
> citations, but it does not yet establish an exact corpus-wide recipient percentage.

## Remaining work for a final census

1. Map named and shorthand Act-section citations through OLRC classification tables
   and contemporaneous Statutes at Large text.
2. Trace repealed, transferred, and renumbered U.S. Code citations to the text in
   force on each directive date.
3. Resolve unmatched subsection locators and review the conservative parser queue.
4. Complete the provision-version census, then rerun the occurrence mapping and
   report the final recipient shares without unresolved-coverage caveats.
