# Qwen sub-directive benchmark

This directory contains the implementation plan, runner, live status artifacts,
and evaluation results for the Round 2 Qwen classification benchmark.

`WORK_STATUS.md` is the living record of completed work, the active task, and
the remaining steps.  It is updated as the benchmark advances.

Runtime artifacts are written below `outputs/`; the source implementation is
kept in this directory so the complete experiment is self-contained.

Usage (from the repository root):

```bash
python3 analysis/qwen_subdirective_benchmark/qwen_benchmark.py prepare
python3 analysis/qwen_subdirective_benchmark/qwen_benchmark.py run --smoke
python3 analysis/qwen_subdirective_benchmark/qwen_benchmark.py run
python3 analysis/qwen_subdirective_benchmark/qwen_benchmark.py status --watch
python3 analysis/qwen_subdirective_benchmark/qwen_benchmark.py evaluate
```
