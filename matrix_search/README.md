# Matrix Search

This directory contains the minimum randomized search code needed to inspect
the QC/UEP matrix-construction procedure used by the study.

- `generate_qcpeg_screen.py`: lightweight N=4096 candidate construction with
  base-graph PEG distance selection and QC 4-cycle screening.
- `search_9pct.py`: isolated generation, compilation, and screening near 9%
  measured raw BER.
- `materialize_selected.py`: re-exports a selected H with a full orthogonal G.
- `generate_rate12_long.py`: full-matrix export support for N=4096, K=2048,
  Z=128, normal degree 3, strong degree 12, and three distributed strong base
  columns.
- `generate_multirate.py`: candidate generation for the evaluated multi-rate
  configurations, including the rate-2/3 operating-boundary experiment.

The search places edges with row-load balancing, gives strong columns priority
according to their current per-row occupancy, and screens circulant shifts for
QC 4-cycles. The per-row strong-anchor count is a ranking objective, not a hard
"at most one strong anchor per row" constraint.

These scripts generate candidate matrices and may produce different outputs
between runs. The exact matrices used for manuscript figures and tables are
provided as fixed constants under `../software/core` and
`../software/high_rate`. Search outputs should be written to a separate working
directory so they do not overwrite the frozen constants.

Requirements: Python 3 and NumPy.

## Isolated 9% Search

`search_9pct.py` uses `generate_qcpeg_screen.py` to generate, compile, and
screen fresh N=4096 candidates
without copying them into `software/core`. Candidate matrices and full logs are
written to `../search_results`:

```bash
python matrix_search/search_9pct.py --seed-start 5001 --count 8
```

New searches write their selected screening candidate to
`../search_results/latest_screening_candidate`; they do not overwrite the
retained seed-7001 result.

The default screening profile contains 128 mapped hotspots and 640 spatially
clustered hotspots outside the mapping budget. The default noise point targets
a measured raw BER of 8.8%--9.2%. A
screening result is a ranking measurement, not evidence of a $10^{-6}$ FER.
The screening generator emits a zero generator matrix because the Monte Carlo
test uses the all-zero codeword. A selected parity-check matrix must be
re-exported with its full orthogonal generator before nonzero-codeword use.
Use `materialize_selected.py <candidate-directory>` for that final export.

The retained seed-7001 matrix and its logs are under
`../search_results/best_9pct_candidate`. Its 103,980-frame confirmation at
9.036% raw BER observed 3 proposed failures (FER 2.89e-5). It is retained as
the best candidate found in this local search, not as evidence for the
manuscript's 1e-6 empirical target.
