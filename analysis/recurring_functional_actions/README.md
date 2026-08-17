# Recurring functional actions

This project identifies recurring **governance actions** in presidential directives.
The unit is an operative function, not a statute or a broad policy topic.  Authority
citations are retained for later description but are excluded from family discovery.

The first build is deliberately a pilot.  It combines three auditable seed families
(`emergency_action`, `property_blocking`, and `national_monument_designation`) with a
bottom-up review queue derived from the existing authority-masked canonical function
profiles.  Seed matches are proposals, not final labels.

Run from the repository root:

```bash
python3 analysis/recurring_functional_actions/build.py
python3 -m unittest analysis/recurring_functional_actions/test_build.py
```

Outputs are written to `outputs/`:

- `pilot_documents.csv`: deterministic president-by-document-type pilot.
- `pilot_functions.csv`: authority-blind operative functions and discovery signatures.
- `seed_family_assignments.csv`: high-recall assignments requiring review.
- `family_review_queue.csv`: representative and boundary cases for codebook development.
- `family_summary.csv`: provisional family coverage by documents and administrations.
- `manifest.json`: input hashes, counts, and parameters.

`family_codebook.csv` is the working codebook.  A family becomes final only after its
definition, exclusions, and boundary cases are reviewed.  `emergency_action` requires
an action that declares, continues, modifies, or terminates an emergency; merely
mentioning an emergency or citing IEEPA is insufficient.
