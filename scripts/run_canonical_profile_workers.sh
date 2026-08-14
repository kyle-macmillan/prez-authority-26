#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
shard_dir="${1:-data/parent_analysis/canonical_profiles/shards12}"
retry_args=()
if [[ "${RETRY_UNKNOWN:-0}" == "1" ]]; then
  retry_args+=(--retry-unknown)
fi

for n in {01..12}; do
  .venv-gemini/bin/python src/gemini_flash_harness.py \
    "$shard_dir/requests_${n}.jsonl" \
    "$shard_dir/responses_${n}.jsonl" \
    --execute \
    --confirm-network \
    --thinking-off \
    "${retry_args[@]}" \
    --attempt-log "$shard_dir/responses_${n}.jsonl.attempts.jsonl" \
    >"$shard_dir/worker_resume_${n}.log" 2>&1 &
done

wait
