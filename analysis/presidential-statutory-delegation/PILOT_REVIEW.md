# Blind pilot review instructions

Code the 30 rows in `outputs/pilot_human_gold.csv` before running GPT. The sheet contains
the authority identity, all observed dates, literal citation aliases, sample vesting
clauses, and any current OLRC source material already available. The vesting clauses
identify what was cited; do not infer the statutory answer from what the directive did.

Enter a JSON list in `human_classifications_json`. Use one object for every controlling
historical version needed to cover the observed dates:

```json
[
  {
    "version_start": "1951-10-31",
    "version_end": null,
    "presidential_authorization": true,
    "presidential_required_duty": false,
    "presidential_condition_precedent": false,
    "standalone_presidential_constraint": false,
    "classification": "delegation",
    "confidence": "high",
    "operative_excerpt": "The President of the United States is designated and empowered...",
    "rationale": "The provision expressly permits the President to delegate an assigned function.",
    "official_sources": ["https://uscode.house.gov/..."]
  }
]
```

The fields are multi-label. `classification` is `delegation` exactly when authorization
or condition precedent is true. A required-duty-only or constraint-only provision is
`nondelegation`. Use `too_broad` when the cited scope cannot support a provision-level
answer and `cannot_verify` when a sufficiently specific historical provision cannot be
reliably located. For either unresolved class, the excerpt may be empty, but explain the
problem and include any official sources consulted.

Put uncertainties or source conflicts in `human_notes`. Do not inspect model output until
all 30 human JSON cells are complete.
