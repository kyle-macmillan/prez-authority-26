# Corpus partitions

The repaired corpus contains 20,232 directives from the historical
`4_28_2026_build.csv` master at Git revision `5b128d9`.

- `4_28_2026_build_dev.csv`: 18,418 directives that appeared in at least one of the
  previously used development or malformed-holdout CSVs. They are treated as exposed.
- `4_28_2026_build_holdout.csv`: 1,814 directives that appeared in neither previously
  used CSV. These are held out from segmentation and vesting-clause development.
- `holdout_ids.json`: the exact identifiers of those 1,814 task-specific holdout directives.
- `corpus_partition_manifest.json`: counts, identifier hashes, provenance, and split
  invariants.

Segmentation and vesting-clause development tools must load the development CSV only.
Parent-relationship analysis is a separate task and may explicitly load both partitions;
its full-corpus artifacts live under `data/parent_analysis_all_corpus` and must not be fed
back into segmentation or vesting development. The split can be reproduced without the
obsolete pre-repair CSVs by using the historical master and durable holdout-ID registry:

```bash
python3 src/rebuild_strict_holdout.py \
  --master-git-spec 5b128d9:data/4_28_2026_build.csv \
  --master-label git:5b128d9:data/4_28_2026_build.csv \
  --holdout-ids data/holdout_ids.json \
  --dev-output data/4_28_2026_build_dev.csv \
  --holdout-output data/4_28_2026_build_holdout.csv \
  --holdout-ids-output data/holdout_ids.json \
  --manifest-output data/corpus_partition_manifest.json
```
