# Minimal Public Artifact Manifest

This staging package is intentionally limited to artifacts needed to inspect or
reproduce claims made in the manuscript. It is not a mirror of the development
workspace.

## Included

| Manuscript claim | Public artifact |
|---|---|
| Rate-1/2 FER, ablation, and block-length experiments | `software/core/` and `results/main_rate12_long.csv` |
| Frozen scale-2.0 result tables and fitted curves | `results/test_results_staircase_scale_2.000/` |
| Residual PSD and normalized ACF controls | `software/psd/` |
| Rate-2/3 operating-boundary experiment | `software/high_rate/` |
| Public-readout import and Wang-calibrated mild-drift augmentation | `software/real_readout/` |
| Conditional helper-data leakage check | `security/` and its frozen profile fixture |
| Earlier folded N=4096 scaling-core synthesis | `hardware/` (historical; not the current five-bit RTL) |
| Same-channel NR-LDPC, Polar SC and Turbo comparison | `revision_20261118/nr_ldpc_same_channel/`, `polar_same_channel/`, `turbo_same_channel/` |
| Current five-bit Proposed implementation | `revision_20261118/proposed_hw_formal_5bit_message_bram/` |
| N=1024/2048/4096 hardware scaling | `revision_20261118/proposed_hw_length_scaling/` |
| Local Polar/Turbo hardware comparison | `revision_20261118/polar_hw_kestel_512_64/`, `turbo_hw_lte_belov_mosin/` |
| Reviewer-facing configurations, frozen outputs and execution guide | `revision_20261118/REVIEWER_GUIDE.md` |

The revision addition excludes the revised leakage diagnostic. Its selected
source/result hashes are recorded independently in `revision_20261118/`.

## Intentionally excluded

- abandoned matrices, failed candidates, and parameter-search directories;
- obsolete matrix-construction prototypes and failed search outputs;
- server logs, executable files, Vivado caches, generated runs, and GUI projects;
- local copies of third-party SRAM-PUF datasets;
- manuscript source, private notes, patents, presentations, and unrelated code;
- complete SoC, NVM, PUF-interface, and board-level integration logic;
- historical result folders not cited by the manuscript.

## Reproduction and version identification

The reviewer revision supplies selected frozen outputs, original-source hashes,
packaged-file hashes and explicit reproduction commands. The revision tag and
lightweight verification entry are documented in `revision_20261118/README.md`.
Full Monte Carlo reproduction is an explicit separate operation.

Third-party software retains its included licenses and provenance. Public
SRAM-PUF datasets must be obtained from their original providers and are not
redistributed here. Exact experiments use the supplied frozen matrices;
exploratory matrix-search programs are not part of this minimal release.
