# Day 1 and Week 1 substantive policy

This project compares substantive policy actions at the start of newly elected
administrations.  It does **not** classify actions as flip-flops.

- Day 1 is the inauguration calendar date.
- Week 1 is Day 1 plus the following six calendar days.
- Nonconsecutive returns (Donald Trump in 2025) are new starts.
- Consecutive second terms and mid-term successions are excluded.

Run from the repository root:

```bash
python3 analysis/day_one_week_one/build.py
python3 -m unittest analysis/day_one_week_one/test_build.py
```

The build creates a complete cohort inventory and a review queue.  Keyword matches are
high-recall issue proposals only.  Reviewers decide substantive-policy eligibility,
issue labels, position summaries, and evidence before analysis.  `archive_check_status`
remains `pending` until each administration-window inventory is checked against an
authoritative archive; missing local records must not be interpreted as inaction.
Both local corpus partitions are included by default and document IDs must be unique
across them.
