# First 100 days of new administrations

This project inventories every directive in the local corpus from the first 100
calendar days of newly elected administrations and supports review of their
substantive-policy content. It does **not** classify actions as flip-flops.

- Administration Day 1 is the inauguration calendar date; Day 100 is 99 days later.
- Day 1 and first-week membership are retained as useful subsets.
- Nonconsecutive returns (Donald Trump in 2025) are new starts.
- Consecutive second terms and mid-term successions are excluded.
- Executive orders, memoranda, proclamations, and letters are all retained.

Run from the repository root:

```bash
python3 analysis/first_100_days/build.py
python3 -m unittest analysis/first_100_days/test_build.py
```

The build writes:

- `directive_inventory.csv`: the complete 100-day cohort, ordered by administration,
  date, and document ID, with Day 1/Week 1 markers and policy-review fields;
- `administration_summary.csv`: Day 1, Week 1, and Day 1–100 counts;
- `proposed_issue_summary.csv`: high-recall keyword proposal counts;
- `archive_audit.csv`: one reconciliation record per administration window; and
- `manifest.json`: input hashes, window definition, and build totals.

Keyword matches are proposals only. Reviewers decide substantive-policy eligibility,
issue labels, position summaries, and evidence before analysis. Archive audit rows
remain `pending` until each window is checked against an authoritative archive; missing
local records must not be interpreted as inaction. Both local corpus partitions are
included by default, and document IDs must be unique across them.
