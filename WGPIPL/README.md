# Presidential directive distribution

This analysis counts executive orders, memoranda, letters, and proclamations by
president-term administration and produces publication-ready line charts by directive
type and by the eight substantive vesting-authority categories.

## Run

From the repository root, create or activate a Python environment and install the
plotting dependencies:

```sh
python3 -m pip install -r WGPIPL/requirements.txt
python3 WGPIPL/directive_distribution.py
python3 WGPIPL/insert_authority_figure.py
```

The script writes both sets of aggregated counts to
`WGPIPL/directive_counts_by_administration.csv` and
`WGPIPL/authority_category_counts_by_administration.csv`. It writes each plot to PDF
and PNG files in the same directory.

The insertion script places the authority-category figure and a referenceable Word
caption at the beginning of section III in the WGPIPL manuscript, then renumbers the
existing appendix figure and its cross-reference. It refuses to run a second time if
the figure bookmark is already present.

## Method

The input corpus is the union of `data/4_28_2026_build_dev.csv` and
`data/4_28_2026_build_holdout.csv`. These files contain 20,232 unique URLs.
Administrations are defined by the source data's `president` and `term` fields and
ordered by their earliest document date. The x-axis labels show presidential surnames;
two-term presidents therefore appear twice in succession.

The analysis excludes the November 5, 1994 Reagan letter announcing his Alzheimer's
disease diagnosis because it was issued after his presidency, as well as 6,771
codebook-defined ceremonial directives. The current second Trump administration is
retained; the dataset ends March 12, 2026. The resulting analysis contains 13,460
directives.

The authority-category figure uses the eight mutually exclusive constitutional and
statutory specificity combinations. It omits the bookkeeping categories for directives
with no extracted vesting clause and other/unclassified vesting authority.

The baseline-change figure converts each category count to a share of all directives in
that administration and plots the percentage-point change from the Truman
administration. Positive values represent a larger share than Truman and negative
values a smaller share.
