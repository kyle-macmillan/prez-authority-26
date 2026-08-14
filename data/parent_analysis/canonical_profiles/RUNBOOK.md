# Canonical profile completion runbook

The canonical build is currently incomplete. `profile_requests.jsonl` contains only
directives whose prior profile is missing, stale, invalid, or requires confirmation after
an empty operative extraction. Existing valid profiles are not submitted again.

Use Application Default Credentials for project `prez-authority`, then resume with:

```bash
.venv-gemini/bin/python src/gemini_flash_harness.py \
  data/parent_analysis/canonical_profiles/profile_requests.jsonl \
  data/parent_analysis/canonical_profiles/profile_responses.jsonl \
  --execute --confirm-network --google-search --thinking-off --retry-unknown
```

`--retry-unknown` is needed only because the first request was ledgered before a local
missing-credentials failure. The failure occurred before an access token existed and no
model response was returned. Future missing-credential failures occur during preflight,
before a submission record is written.

After responses are saved, rebuild the registry with:

```bash
PYTHONPATH=src python3 src/build_canonical_function_profiles.py \
  --repair-responses data/parent_analysis/canonical_profiles/profile_responses.jsonl
```

If the rebuild emits zero-confirmation requests, run those requests through the same
harness into a distinct append-only response file and pass both response paths back to the
builder. Do not proceed to embeddings or parent ranking until the snapshot manifest reports
`complete: true` and `registry_equals_operative_ids: true`.
