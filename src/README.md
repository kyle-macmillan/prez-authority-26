# Source layout

- `analysis/`: downstream statistical and clustering analysis tasks
- `embeddings/`: embedding generation and provenance maintenance
- `tests/`: Python and JavaScript tests
- root modules: shared segmentation, annotation-viewer generation, and parent-retrieval pipeline code

Run the Python test suite from the repository root with `pytest src/tests`.

Build the 200-child parent-candidate pilot viewer with:

`python src/build_parent_candidate_viewer.py`

The generated viewer is written to
`data/parent_analysis/pilot/parent_candidate_viewer.html`. It is intentionally ignored
because it embeds masked source documents; the sample CSV and manifest remain trackable.
Similarity scores and channel ranks are available behind an explicit toggle. Candidate
tabs follow ascending fused RRF rank.
Extended Woolley and Peters ordering phrases are bolded in full documents and in the
aligned operative-segment excerpts.

Build the corpus-wide Candidate 1 and Candidate 2 score distributions after ranking with:

`python src/analysis/candidate_score_distributions.py`

The command writes pair-level scores, descriptive statistics, and a six-panel histogram
report under `data/parent_analysis/candidate_score_distributions/`. Candidate positions
use three-channel RRF; W&P phrase agreement remains visible as a diagnostic but is not a
fusion channel.

The separate legally operative path-dependency pilot is organized under
`src/path_dependency/` with artifacts under
`data/parent_analysis/path_dependency_pilot/`. See the README files in those directories
for the GPU classification and viewer-generation commands.
