# Revision-package validation (2026-11-18)

The packaged programs were checked in Windows with Python 3.12, GCC, Icarus
Verilog and Vivado 2022.2. These checks exercise the released programs; they
do not replace the frozen Monte Carlo data or claim a new full FER run.

| Check | Observed outcome |
|---|---|
| NR early-stop/reference tests | 10 tests passed |
| NR selected-MS smoke | Noiseless self-test and 3 points x 2 frames completed |
| Turbo native library rebuilt from included source | Exhaustive constituent checks, rate-map checks and 48 noiseless frames passed |
| Turbo independent reference tests | 11 tests passed |
| Turbo selected 10-iteration smoke | Self-test and 1 point x 2 frames completed |
| Polar N=4096,K=2048 software | Compiled, encoder/SC self-test and short channel run completed |
| Polar hardware references | Original/exact/fast at 8/4 bits passed; 32-block fast wrapper measured 195904 cycles |
| Current Proposed RTL | 12 vectors passed C/Python reference and cycle-by-cycle baseline checks; 3 backpressure cases passed; 7746080 prefetch checks |
| N=1024/2048/4096 hardware | 10 vectors per length passed full-codeword checks, with stalled-input/output cases; N=4096 production lockstep passed |
| Paper Turbo synthesis entry | Fresh top-level synthesis reproduced 6493 LUTs, 5461 FFs, 21 BRAM tiles and 1 DSP |
| Paper Turbo functional simulation | Four frozen noiseless vectors passed; each START-to-DONE count was 258993 cycles |
| Frozen software comparison | CSV interpolation reproduced approximately 8.08%, 8.41% and 9.85%; Polar did not cross FER=1e-3 |

`scripts/verify_package.py` checks the released file hashes, frozen software
budgets, error-count arithmetic, shared profile and hardware reports. The exact
staged Git archive was extracted into a clean temporary directory and checked
with that same command before publication. RTL resources refer to synthesis;
simulation cycle counts are not post-route frequency or measured throughput.
