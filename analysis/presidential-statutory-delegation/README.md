# Presidential statutory delegation

This analysis measures whether specific statutory authorities cited in formal vesting
clauses affirmatively authorize presidential action or assign the President a legal
condition precedent.  Required-duty-only provisions and standalone constraints are
tracked separately and do not enter the headline delegation numerator.

The population is the 13,461 nonceremonial directives in the combined development and
holdout corpora. Citation occurrences are the primary unit; parallel source forms for
one legal provision within one clause count once. Broad statutory references remain in
the inventory and may be coded `too_broad`.

## Workflow

```bash
# Network-free inventory and blinded 30-authority human-gold sheet.
python3 analysis/presidential-statutory-delegation/build.py
python3 analysis/presidential-statutory-delegation/build_equivalence_review_html.py
python3 analysis/presidential-statutory-delegation/build_equivalence_candidates.py
python3 analysis/presidential-statutory-delegation/run_equivalence_gpt56.py
python3 analysis/presidential-statutory-delegation/compile_equivalence_results.py
python3 analysis/presidential-statutory-delegation/workflow.py prepare-pilot

# Only after the human_classifications_json column is complete:
python3 analysis/presidential-statutory-delegation/run_gpt56.py --phase pilot --execute
python3 analysis/presidential-statutory-delegation/workflow.py evaluate-pilot

# After disagreements are reviewed and prompt_candidate.md is revised as agreed:
python3 analysis/presidential-statutory-delegation/workflow.py freeze-prompt
python3 analysis/presidential-statutory-delegation/run_gpt56.py --phase full --execute
python3 analysis/presidential-statutory-delegation/run_gpt56.py --phase targeted --execute
python3 analysis/presidential-statutory-delegation/workflow.py compare-reruns
python3 analysis/presidential-statutory-delegation/workflow.py compile-results
```

The runners are dry-run by default. Each request uses a fresh ephemeral `codex exec`
process with `gpt-5.6-sol`, low reasoning, a read-only sandbox, schema-constrained JSON,
and auditable event logs. Web search is permitted for official historical sources;
shell, filesystem, MCP, computer-use, and other tools invalidate a response.

The full run is intentionally blocked until the blind human pilot is complete, all 30
pilot calls are valid, and the reviewed prompt has been frozen with hashes of both.

`outputs/citation_equivalence_review.csv` and its searchable HTML rendering list
every occurrence-level consolidation, the printed forms involved, the preferred
canonical authority, and the explicit textual basis. Whole Acts are not merged
with separately cited Act sections, and proximity alone is never an equivalence.
