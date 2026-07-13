# Matrix Search

This directory contains the minimum randomized search code needed to inspect
the QC/UEP matrix-construction procedure used by the study.

- `generate_rate12_long.py`: N=4096, K=2048, Z=128, normal degree 3,
  strong degree 12, with one strong base column (128 lifted variables).
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
