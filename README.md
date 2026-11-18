# Reliability-Guided SRAM-PUF Reconstruction

This repository contains the research artifacts for the accompanying manuscript,
including additional software and hardware supplied in response to peer review.

## Reviewer revision artifacts

Start with the [reviewer-to-artifact guide](revision_20261118/REVIEWER_GUIDE.md).
It connects R2.3, R3.2, R3.3 and R4.Archive to the selected sources, frozen
results, configuration details and reproduction commands. The revision adds:

- same-channel NR-LDPC (MS, 10000 frames/point), Polar SC (1000 frames/point),
  and Turbo (10 iterations, 100000 frames/point) software baselines;
- the current five-bit Proposed RTL (1440 LUTs and 160 registers), with its
  frozen matrices, ROMs, reference model and functional tests;
- hardware scaling for N=1024, 2048 and 4096;
- the local Polar and Turbo hardware versions used in the resource comparison,
  with exact synthesis reports and explicit implementation boundaries.

The immutable revision tag is `reviewer-artifacts-20261118`. Run the lightweight
integrity/configuration check without launching full Monte Carlo simulations:

```bash
python revision_20261118/scripts/verify_package.py
```

The revised leakage diagnostic is not included in this addition. The original
artifact directories below remain available independently.

## Requirements

- GCC with OpenMP and GNU Make
- Python 3 with NumPy and Matplotlib
- Vivado 2022.2 for FPGA synthesis

## Scope

The artifact is limited to manuscript-facing code. Development history, failed
matrix candidates, third-party datasets, Vivado caches, and complete SoC/board
integration are excluded. Public SRAM-PUF data must be obtained from its
original source.

The earlier `hardware/` directory contains a scaling core; the current full
decoder RTL is under `revision_20261118/`. The decoder artifacts start from
already formed LLRs and do not include PUF acquisition or a complete fuzzy
extractor system, helper-data generation, system bus, or KDF.

## Original Software: Quick Verification

The default configuration is intentionally small. From Git Bash, run:

```bash
./run_quick.sh
```

This compiles the N=256 configuration and runs at most 1000 frames per noise
point. It checks the simulation path but is not intended to reproduce the
paper's low-FER statistics.

## Original Software: Full Reproduction

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
licenses. Current decoder releases and the earlier scaling core are identified
separately in the reviewer guide. Third-party software licenses are retained
inside each baseline's directory.
