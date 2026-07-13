# Retained Matrix Search Result

Only the selected seed-7001 candidate is retained. Intermediate seeds and
obsolete batch-search outputs were removed.

- `best_9pct_candidate/base_shifts.csv`: 16-by-32 QC shift matrix.
- `best_9pct_candidate/full_matrix/`: parity-check matrix and full orthogonal
  generator exported for nonzero-codeword use.
- `best_9pct_candidate/puf_profile_long.h`: budget-limited search profile with
  128 mapped hotspots and 640 clustered hotspots outside the mapping budget.
- `best_9pct_candidate/01_generate.log`--`03_screen.log`: generation, build,
  and screening logs.
- `best_9pct_candidate/confirm_100k.csv` and `04_confirm_100k.log`: longer
  confirmation result.

At 9.036% measured raw BER, the 103,980-frame confirmation observed 3 proposed
failures, corresponding to FER 2.89e-5. This candidate therefore demonstrates
operation near 9% raw BER but does not establish the 1e-6 empirical target.
