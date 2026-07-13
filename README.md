# Reliability-Guided SRAM-PUF Reconstruction

This repository contains a minimal research artifact for the accompanying
manuscript. It covers the LDPC reconstruction experiments, spatial residual
analysis, helper-data leakage check, public-readout evaluation scripts, and the
folded FPGA scaling core.

## Requirements

- GCC with OpenMP and GNU Make
- Python 3 with NumPy
- Vivado 2022.2 for FPGA synthesis

## Scope

The artifact is limited to manuscript-facing code. Development history, failed
matrix candidates, third-party datasets, Vivado caches, and complete SoC/board
integration are excluded. Public SRAM-PUF data must be obtained from its
original source.

The FPGA files implement a decoder scaling core, not a complete PUF interface,
helper-data store, system bus, or KDF.

## Reproducibility

Short smoke-test configurations are provided for code inspection. The exact
paper points may require long Monte Carlo runs. Frozen reference outputs and
their command lines will be included in the archival release.

Matrix search is randomized. Exact numerical reproduction requires the frozen
matrix used by the manuscript; a newly generated candidate need not be
identical.

## Availability

This repository is provided as the manuscript's minimal research artifact.
Third-party datasets are not redistributed and remain subject to their original
licenses. The released FPGA design is limited to the decoder scaling core.
