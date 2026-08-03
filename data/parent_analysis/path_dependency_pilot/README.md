# Path-dependency pilot artifacts

This directory keeps the path-dependency parent-child pilots separate from the general
parent-analysis pipeline.

## Comparison pilot

The original reproducible random sample remains in `data/parent_analysis/pilot/`. It is
not changed by the legally operative pilot.

## Automated legally operative pilot

`operative/` is generated in two steps:

```bash
PYTHONPATH=src .venv-parent-analysis/bin/python -m path_dependency.classify_operative_children
PYTHONPATH=src python -m path_dependency.build_operative_viewer
```

The first command requires a CUDA GPU with at least 11 GB VRAM. It validates two
codebook-grounded Qwen classification prompts against the existing Round 2 majority
labels, selects the highest-coverage policy meeting the precision requirement, and
materializes 50 disjoint unresolved children. No new human Code 3 review is performed.

Small manifests, validation summaries, and the selected-child table may be committed.
The model prediction cache and self-contained HTML viewer are ignored and should be moved
with SCP.
