# Reliability-Guided SRAM-PUF Reconstruction

This repository contains a minimal research artifact for the accompanying
manuscript. It covers the LDPC reconstruction experiments, spatial residual
analysis, helper-data leakage check, public-readout evaluation scripts, and the
folded FPGA scaling core.

## Requirements

- GCC with OpenMP and GNU Make
- Python 3 with NumPy and Matplotlib
- Vivado 2022.2 for FPGA synthesis

## Scope

The artifact is limited to manuscript-facing code. Development history, failed
matrix candidates, third-party datasets, Vivado caches, and complete SoC/board
integration are excluded. Public SRAM-PUF data must be obtained from its
original source.

The FPGA files implement a decoder scaling core, not a complete PUF interface,
helper-data store, system bus, or KDF.

## Quick Verification

The default configuration is intentionally small. From Git Bash, run:

```bash
./run_quick.sh
```

This compiles the N=256 configuration and runs at most 1000 frames per noise
point. It checks the simulation path but is not intended to reproduce the
paper's low-FER statistics.

## Full Reproduction

The N=4096 sweep uses the paper settings (`scale=2.0`, seed 12345, 50 target
frame errors, and at most $10^7$ frames per noise point):

```bash
./run_full.sh --confirm
```

This run may require several days depending on the CPU. The confirmation flag
prevents an accidental long run. The equivalent executable syntax is
`scale seed target_errors max_tests max_noise`.

The frozen aggregate output is in `results/main_rate12_long.csv`. Run
`python results/plot_precomputed.py` to plot it without rerunning Monte Carlo.

Matrix search is randomized. Exact numerical reproduction requires the frozen
matrix used by the manuscript; a newly generated candidate need not be
identical.

## Availability

This repository is provided as the manuscript's minimal research artifact.
Third-party datasets are not redistributed and remain subject to their original
licenses. The released FPGA design is limited to the decoder scaling core.
