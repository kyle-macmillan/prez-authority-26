# Vesting-clause categories over time

This analysis plots raw counts of mutually exclusive vesting-clause authority
categories across presidential administration-terms. It uses the current development
and holdout corpus, applies the project's existing ceremonial-directive exclusion,
and preserves the vesting categories defined by the existing authority-specificity
analysis.

The final administration, Donald Trump's second, is partial through the latest
directive in the corpus: March 12, 2026.

## Outputs

`outputs/figures/` contains twenty figures in both PNG and PDF form:

- all directives and each of the four directive types (executive orders, memoranda,
  letters, and proclamations); and
- an all-plotted-category, frequency-filtered, and core-authority version of each
  population.

Five additional figures separately plot all directives, executive orders, memoranda,
letters, and proclamations. Their left axes show each core category as a percentage of that
administration's output of the specified directive type—not of all directives—and
their right axes show the absolute number of that directive type. The memorandum
figure also plots the percentage containing any vesting clause. Each figure now
also includes an “Other vesting clause types” residual line: all vesting categories
outside the three core categories, excluding directives with no vesting clause.

No-vesting-clause and other/unclassified-vesting-authority lines are omitted from
every figure. Administration labels omit term numerals; the final Trump term remains
marked with an asterisk because it is partial.

The filtered figures use a single global rule so categories remain comparable across
directive types. A category is retained when its non-ceremonial all-directive count,
averaged across all 22 administrations including zeros, is at least 50. The retained
categories are Specific Statute only, Generic Constitution + Generic Statute, and
Generic Constitution + Specific Statute.

The core-authority figures contain only Specific Statute only, Generic Constitution +
Generic Statute, and Generic Constitution + Specific Statute. Once the two omitted
non-vesting buckets are removed, this is the same three-category set as the
frequency-filtered figures; both file variants are retained for explicit comparison.

`outputs/counts_by_administration.csv` contains the plotted counts in tidy form.
`outputs/manifest.json` records source paths, corpus and exclusion totals, global
category means, plotting parameters, and the complete output inventory.

## Reproduce

From the repository root, install the local plotting dependency and run the build:

```bash
python3 -m venv /tmp/vc-overtime-venv
/tmp/vc-overtime-venv/bin/pip install -r analysis/vc-overtime/requirements.txt
/tmp/vc-overtime-venv/bin/python analysis/vc-overtime/build.py
```

Run the focused and existing vesting-authority tests with:

```bash
/tmp/vc-overtime-venv/bin/python -m unittest analysis/vc-overtime/test_build.py
/tmp/vc-overtime-venv/bin/python -m pytest "Authority Vagueness Analysis/test_vesting_authority_breakdown.py"
```
