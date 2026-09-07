# Frozen decision lists

Both classifiers stop at the first matching rule. Exact regular expressions and
rationales are in `build.py`; this file states their substantive order.

The main features are active verbs plus their objects. Policy topic, administration,
date, and document type are excluded. Context is retained only where the same verb can
have different legal posture—for example, `review regulations` is Code 1, while
`rescind regulations` is Code 2, and `regulation X is hereby suspended` is Code 3.

## Text-only

1. Flag the inseparable federal-office closure/employee leave/statutory holiday pattern
   as Code 4.
2. Treat public observances, congressional reports or transmissions, diplomatic
   recognition, veto messages, non-operative support letters, succession designations,
   and pure prior-order revocation/housekeeping patterns as Code 0.
3. Treat direct waivers, emergency continuations, funds made available by presidential
   determination, entry or asset restrictions, legal-status designations, pay schedules,
   tariff changes, and direct prohibitions as Code 3.
4. Treat mandatory agency funding conditions, rule changes, enforcement consequences,
   and contract clauses as Code 2.
5. Treat remaining executive organization, review, study, reporting, coordination,
   prioritization, consultation, and delegation signals as Code 1.
6. Default to Code 0 when no governance signal matches.

## Flash-profile-only

1. Default missing profiles to the explicit Code-0 `P0_NO_PROFILE` state.
2. Flag the mixed office-closure/leave/holiday function as Code 4.
3. Treat structured reporting, recognition, veto, succession, and prior-order
   housekeeping functions as Code 0.
4. Treat structured waiver, emergency-continuation, funding determination, entry/asset,
   legal-status, pay, and tariff functions as Code 3.
5. Treat structured funding/eligibility conditions, mandatory legal instruments,
   sanctions, and contract requirements as Code 2.
6. Classify any other nonempty policy or operative profile as Code 1.

The profile input is formed only from `actor`, `action`, `target`, `mechanism`, `effect`,
`condition`, `timing`, and `label`. In particular, it never reads the raw-text `evidence`
field.
