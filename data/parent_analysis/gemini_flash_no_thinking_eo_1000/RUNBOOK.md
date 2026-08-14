# Gemini Flash no-thinking EO 1,000

This run is downstream of the canonical full-corpus function-profile snapshot. Do not run
any step until `../canonical_profiles/snapshot_manifest.json` reports `complete: true` and
exactly 9,762 canonical profiles.

The production sequence is:

1. Build the fixed random EO sample with `src/build_eo_parent_production_sample.py`.
2. Embed the canonical profiles with `src/embed_function_profiles.py --snapshot-dir
   data/parent_analysis/canonical_profiles`.
3. Build the candidate pool with `src/build_function_candidate_pool.py`, passing the
   canonical snapshot, `data/parent_analysis_all_corpus`, this run's `sampled_children.csv`,
   and this run's `candidate_pool.csv` as the explicit output.
4. Build ranking requests with `src/build_gemini_function_rank_requests.py`, passing the
   canonical profile JSONL and this run's candidate pool explicitly.
5. Execute the requests with `src/gemini_flash_harness.py --execute --confirm-network
   --google-search --thinking-off` and validate all 1–25 rankings.
6. Build and execute the separate rank-1 acceptance requests with the same Search and
   thinking settings.

All inferred relationships remain `provisional_unreviewed`. A rejected rank-1 candidate
does not establish that ranks 2–25 are implausible; the complete ranking is retained for
later human review.
