# Results

## Validation

The frozen text-only rules correctly classified **62 of 93 directives (66.7%)**. The frozen Flash-profile-only rules correctly classified **63 of 93 (67.7%)**. The development-set majority-class baseline was **60 of 93 (64.5%)**.

Supported-class macro-F1 was 0.343 for text and 0.359 for profiles. Validation has no code-4 example, so neither figure measures code-4 generalization. Full confusion matrices and per-class metrics are in `outputs/metrics.json`.

The aggregate figures are driven by Code 0. Text correctly identified 52/60 Code-0 and 10/15 Code-1 directives, but 0/1 Code-2 and 0/17 Code-3 directives. Profiles correctly identified 51/60 Code-0, 11/15 Code-1, 0/1 Code-2, and 1/17 Code-3 directives. Thus neither system is reliable for the legally consequential minority classes despite narrowly beating the majority baseline. Every error is listed in `outputs/validation_errors.csv`.

## Generic Constitution + Generic Statute population

After applying the repository's existing ceremonial exclusion and authority classifier, the target contains **1369 directives** across the development and holdout corpus. Canonical Flash profiles are available for **1319 (96.3%)**. The classifiers agree on **779 (56.9%)**.

| Code | Text count | Text share | Profile count | Profile share |
|---:|---:|---:|---:|---:|
| 0 | 458 | 33.5% | 119 | 8.7% |
| 1 | 847 | 61.9% | 1054 | 77.0% |
| 2 | 61 | 4.5% | 180 | 13.1% |
| 3 | 3 | 0.2% | 15 | 1.1% |
| 4 | 0 | 0.0% | 1 | 0.1% |

The text rules provide the complete-population view. The profile results are a deliberately separate robustness check: missing profiles receive the frozen `P0_NO_PROFILE` result, and no raw directive text is used as fallback. `content_summary.csv` provides document-type breakdowns, while `representative_directives.csv` supplies deterministic examples and matched evidence for reading the substantive content behind each category.

The dominant text result is internal/discretionary executive management (`T1_EXECUTIVE_MANAGEMENT`: 847 directives). Its largest Code-0 groups are unmatched governance signals (230), congressional reports (143), and observances (80). The profile view likewise is dominated by profiled executive functions (`P1_PROFILED_EXECUTIVE_FUNCTION`: 1054), followed by mandated rule or guidance changes (`P2_MANDATED_LEGAL_INSTRUMENT`: 168). These patterns suggest the generic-authority population is principally managerial, but the 43.1% classifier disagreement and poor minority-class recall make the precise category shares provisional.

## Interpretation limits

These are transparent rule-based measurements, not new human annotations. Code 2 and code 4 have only two and one gold documents respectively, and code 4 is absent from validation. The Flash profiles were generated upstream by Gemini 3.6 Flash; only the classification of the frozen profiles is deterministic. Validation errors were measured after the rules were frozen and were not used to revise them.
