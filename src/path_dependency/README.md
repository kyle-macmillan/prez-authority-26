# Path-dependency pilot

This package contains the focused pilots used to identify drafting-parent relationships
between presidential directives.

- The original random comparison pilot is materialized in
  `data/parent_analysis/pilot/`.
- The automated Code 3 pilot is materialized in
  `data/parent_analysis/path_dependency_pilot/operative/`.
- Both pilots use the same candidate pool and retrieval rankings; the Code 3 pilot changes
  only how child directives are selected.

Run the automated Code 3 classification and selection from the repository root:

```bash
PYTHONPATH=src .venv-parent-analysis/bin/python -m path_dependency.classify_operative_children
```

The model snapshot is stored in the project-local ignored Hugging Face cache.
