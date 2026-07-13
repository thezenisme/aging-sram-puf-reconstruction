# Minimal Public Artifact Manifest

This staging package is intentionally limited to artifacts needed to inspect or
reproduce claims made in the manuscript. It is not a mirror of the development
workspace.

## Included

| Manuscript claim | Public artifact |
|---|---|
| Rate-1/2 FER, ablation, and block-length experiments | `software/core/` and `results/main_rate12_long.csv` |
| Residual PSD and normalized ACF controls | `software/psd/` |
| Rate-2/3 operating-boundary experiment | `software/high_rate/` |
| Randomized QC/UEP matrix candidate search | `matrix_search/` |
| Public-readout import and Wang-calibrated mild-drift augmentation | `software/real_readout/` |
| Conditional helper-data leakage check | `security/` and its frozen profile fixture |
| Folded N=4096 scaling-core synthesis | `hardware/` |

## Intentionally excluded

- abandoned matrices, failed candidates, and parameter-search directories;
- obsolete matrix-construction prototypes and failed search outputs;
- server logs, executable files, Vivado caches, generated runs, and GUI projects;
- local copies of third-party SRAM-PUF datasets;
- manuscript source, private notes, patents, presentations, and unrelated code;
- complete SoC, NVM, PUF-interface, and board-level integration logic;
- historical result folders not cited by the manuscript.

## Before publication

1. Confirm that every copied source file is the frozen version used for the
   corresponding manuscript table or figure.
2. Add further compact reference outputs only when required for a published figure or table.
3. Add third-party dataset download links, versions, and checksums; do not
   redistribute data unless its license permits it.
4. Select a software license and add citation metadata (`CITATION.cff`).
5. Run the path/privacy audit and smoke tests described in `README.md`.
6. Verify that the matrix-search description in the manuscript matches the
   released randomized candidate generators. Exact experiments use the supplied
   frozen matrices because a new randomized search need not select the same
   candidate.
