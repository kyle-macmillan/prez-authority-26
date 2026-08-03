# Source layout

- `analysis/`: downstream statistical and clustering analysis tasks
- `embeddings/`: embedding generation and provenance maintenance
- `tests/`: Python and JavaScript tests
- root modules: shared segmentation, annotation-viewer generation, and parent-retrieval pipeline code

Run the Python test suite from the repository root with `pytest src/tests`.

Build the blinded 200-child parent-candidate pilot viewer with:

`python src/build_parent_candidate_viewer.py`

The generated viewer is written to
`data/parent_analysis/pilot/parent_candidate_viewer.html`. It is intentionally ignored
because it embeds masked source documents; the sample CSV and manifest remain trackable.
