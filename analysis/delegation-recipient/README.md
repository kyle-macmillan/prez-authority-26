# Statutory delegation recipients

This analysis asks a narrower question than whether a statutory citation somehow
relates to presidential action: **to whom does the cited provision confer an
affirmative legal power—the President, an agency or officer, both, or neither?**

## Current result

The clean-room extraction finds 5,405 pinpoint authority units in formal vesting
clauses of the 13,461 non-ceremonial directives. Parallel Act-section and U.S.-Code
forms in one clause count once. Another 1,056 broad references are held out.

The current source-supported coding resolves 2,834 occurrences (52.4%):

| Recipient | Occurrences | Share of resolved power conferrals |
|---|---:|---:|
| President only | 2,413 | 87.6% |
| Agency/officer only | 25 | 0.9% |
| Both | 318 | 11.5% |
| No affirmative power | 78 | not a power conferral |
| Unresolved | 2,571 | excluded from resolved shares |

Among provisions that clearly confer power on exactly one of the two executive
recipients, 99.0% confer it on the President. Including shared grants, 99.1% of
resolved power-conferring occurrences include presidential power, but only 87.6%
are President-only. This distinction is the central result: a citation can support
presidential action while also assigning an independent statutory role to an agency.

These are **coverage-qualified findings**, not a completed historical census. On all
5,405 pinpoint occurrences, confirmed President-only provisions account for 44.6%
and confirmed provisions containing any presidential power account for 50.5%. With
47.6% unresolved, the mechanically possible President-only range is 44.6%–92.2%; the
range for provisions containing any presidential power is 50.5%–98.1%. The evidence
therefore does not yet justify replacing the earlier 96% estimate with one exact
corpus-wide percentage.

## Method

1. Combine the development and holdout corpora and apply the repository's existing
   ceremonial classifier (20,232 total; 6,771 excluded).
2. Extract only formal authority spans from vesting clauses. Preceding recitals and
   later operative citations are excluded.
3. Normalize pinpoint U.S.C. and Act-section references. Lists produce separate
   authority units; parallel citations to the same provision are collapsed.
4. Extract operative provision/subsection text from the official OLRC XML release
   current through Public Law 119-102 (except 119-101).
5. Apply conservative explicit actor–power rules. A provision is automatically
   resolved only when the operative text names the recipient and its amendment record
   supports use across the observed dates. High-frequency exceptions in
   `reviewed_overrides.csv` have a documented source and recipient rationale.
6. Keep repealed, renumbered, uncodified, ambiguous, or historically unstable
   provisions unresolved rather than applying current text retroactively.

`both` requires independent operative authority for both recipients. An agency that
merely implements a presidential decision does not create a shared grant. Conversely,
a statutory investigation, threshold finding, rulemaking, or delegation authority
assigned to an agency is not converted into presidential power by executive supervision.

## Files

- `COMPARISON_WITH_PRIOR_METHOD.md`: side-by-side comparison with the prior 96%
  presidential-function estimate, including the unresolved-citation explanation.
- `provision_census.csv`: currently resolved provision-version decisions and evidence.
- `outputs/citation_occurrences.csv`: occurrence-level mapping and recipient result.
- `outputs/current_uscode_sources.csv`: extracted OLRC operative text and amendment notes.
- `outputs/recipient_review_queue.csv`: complete U.S.C. review inventory.
- `outputs/unmatched_specific_signals.csv`: clauses needing citation-parser review.
- `outputs/recipient_breakdowns.csv`: overall, directive-type, and administration results.
- `outputs/manifest.json`: hashes, population transitions, counts, and percentages.

## Reproduce

Download the official OLRC archive, then run from the repository root:

```bash
curl -fL -o /tmp/olrc-usc-119-102.zip \
  'https://uscode.house.gov/download/releasepoints/us/pl/119/102not101/xml_uscAll@119-102not101.zip'
python3 analysis/delegation-recipient/build.py
python3 analysis/delegation-recipient/import_olrc.py /tmp/olrc-usc-119-102.zip
python3 analysis/delegation-recipient/build_review_queue.py
python3 analysis/delegation-recipient/classify_current_sources.py
python3 analysis/delegation-recipient/build.py
python3 -m unittest analysis/delegation-recipient/test_build.py
```

The first build refreshes the occurrence universe; the final build maps the sourced
census back to occurrences. The official archive itself is not committed.
