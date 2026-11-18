# Reviewer-to-artifact guide

## R2.3 / R3.2: same-channel end-to-end software comparison

All four configurations use 4096 observations and 2048 information bits. The
frozen enrollment profile has 768 cells at 0.15 and 3328 at 0.01. The channel is
`p_aged[i] = min(2*p_enrollment[i] + noise_floor, 0.5)`, with floors 0.001--0.055.
The external decoders receive enrollment-derived continuous LLRs. The comparison
is between complete configurations. The Proposed curve uses its masking,
placement and quantization; it is not a claim that one isolated decoder
algorithm accounts for the entire difference.

| Curve | Program and selected frozen output | Actual paper configuration |
|---|---|---|
| NR-LDPC | `nr_ldpc_same_channel/run_nr_ldpc_same_channel.py`; `results_5g_nr_ldpc_ms_early_stop_10000/fer_summary.csv` | BG2, CRC16, RV0, MS, maximum 20 iterations, full-syndrome early stopping, 10000 frames/point |
| Polar SC | `polar_same_channel/polar_sc_same_channel.cpp`; `fixed_scale2_profile768_profile_construct_rate_1_2_1000/fer_summary.csv` | N=4096, K=2048, enrollment-profile frozen-set construction, continuous LLRs, 1000 frames/point |
| Turbo | `turbo_same_channel/run_turbo_same_channel.py`; `results_turbo_lte_qpp_100000_iter10/fer_summary.csv` | LTE QPP K=2048, RV0 E=4096, floating Max-Log-MAP, fixed 10 iterations, 100000 frames/point |
| Proposed | `../results/main_rate12_long.csv`; original implementation in `../software/core/` | Frozen manuscript result; no new run is substituted here |

The Proposed FER counts nonconvergence or any full-codeword error. External
FERs count any recovered payload error; the Proposed FER upper-bounds its own
payload-error FER. Different sample budgets are retained in their metadata.
Linear-interpolated raw-BER limits at FER=1e-3 are approximately 8.08% (NR),
8.41% (Turbo), 9.85% (Proposed); Polar does not cross that level in the sweep.
`python scripts/plot_software_comparison.py` regenerates a comparison from frozen
CSVs and writes interpolation results, without launching a Monte Carlo sweep.

### Windows reproduction commands

Run these from this revision folder; install `requirements.txt` first.
The vendored py3gpp (0.6.0 with the local early-stop extension) and srsLTE
sources include their license and provenance. A C/C++ compiler is needed.

```
python nr_ldpc_same_channel/tests/test_early_termination.py -v
powershell -File turbo_same_channel/native/build_native.ps1 -Compiler gcc
python turbo_same_channel/tests/test_reference.py -v
g++ -O3 -std=c++17 -DPOLAR_K=2048 -o polar_same_channel/polar_sc_rate12.exe polar_same_channel/polar_sc_same_channel.cpp
```

Short smoke runs (functional checks, NOT paper-sized FER estimates):
```
python nr_ldpc_same_channel/run_nr_ldpc_same_channel.py --decoder ms --smoke --output nr_ldpc_same_channel/smoke_revision
python turbo_same_channel/run_turbo_same_channel.py --frames 2 --iterations 10 --workers 1 --noise-floors 0.001 --output turbo_same_channel/smoke_revision
polar_same_channel/polar_sc_rate12.exe --frames=2 --fixed-scale=2 --noise-floors=0.001 --construction=profile-enrollment --profile=nr_ldpc_same_channel/puf_profile_long.h --output=polar_same_channel/smoke_revision
```

Full paper-budget runs (explicitly opt in; may be expensive):
```
python nr_ldpc_same_channel/run_nr_ldpc_same_channel.py --decoder ms --frames 10000 --workers 8 --output nr_ldpc_same_channel/rerun_paper
python turbo_same_channel/run_turbo_same_channel.py --frames 100000 --iterations 10 --workers 8 --output turbo_same_channel/rerun_paper
```
For Polar, compile with `-DPOLAR_K=2048`, pass the supplied profile explicitly,
set `--frames=1000 --fixed-scale=2 --construction=profile-enrollment` and supply
the 55 comma-separated floors from 0.001 through 0.055 via `--noise-floors=...`.
Seeds and all other selected run settings are recorded in each frozen
`provenance.json` (seed 20260916). Do not replace MS with NMS or the selected
Polar profile construction with the legacy homogeneous construction.

## R3.3: current hardware comparison (Table VII)

| Implementation | Frozen source | Reference resources | Reproduction entry |
|---|---|---|---|
| Proposed | `proposed_hw_formal_5bit_message_bram/rtl/` | 1440 LUT, 160 FF, 3.5 BRAM tiles, 0 DSP | From its directory: `python tests/verify.py`, then `vivado -mode batch -source scripts/synth.tcl` |
| Polar | `polar_hw_kestel_512_64/rtl/` | 2755 LUT, 2314 FF, 2 BRAM tiles, 0 DSP | From its directory: `python tests/verify_architecture.py --frames 8`, then `vivado -mode batch -source comparison_2048_no_clock/synth.tcl -tclargs optimized` |
| Turbo | `turbo_hw_lte_belov_mosin/rtl/` | 6493 LUT, 5461 FF, 21 BRAM tiles, 1 DSP | From its directory: `vivado -mode batch -source scripts/synth_paper.tcl`; simulation: `powershell -File scripts/sim_paper.ps1 -VivadoBin PATH_TO_VIVADO_BIN` |

Vivado 2022.2 and Icarus Verilog are used. Set tool paths/PATH for the local
installation. Proposed and Polar use OOC synthesis; Turbo uses standard
top-level synthesis. No timing-closure or measured-throughput claim follows.
The reference reports preserve exact target part/package and tool version.
Polar hardware is an 8-bit (512,64) core reused 32 times, accepting 16384 LLRs;
it is distinct from the 4096-bit software Polar curve. Proposed uses five-bit
arithmetic and a 32x64-bit output stream. Differences in rates, output storage
and synthesis flows remain explicit, rather than being normalized away.
Khosroshahi and Narayanan are literature comparisons, not local reproduced RTL.

Behavioral START-to-DONE figures in the paper are 88993/527593 cycles for the
Proposed success vectors, 195904 for Polar and 258993 for Turbo. Counter
endpoints matter: the Proposed regression includes input bubbles, and the Turbo
reset-to-DONE counter is 258995. Those counters must not silently replace the
paper's START-to-DONE endpoint. Functional vectors do not measure channel FER.

## R3.3 / hardware scaling (Table VIII)

`proposed_hw_length_scaling/` contains the actual N=1024, 2048, 4096 matrices,
RTL, ROM exports, reference tests and synthesis scripts. Run from that directory:
```
python scripts/prepare.py
python scripts/verify.py
python scripts/run_synthesis.py --vivado PATH_TO_VIVADO_BAT
```
`reference_reports/scaling_resources.json` and its per-length subdirectories contain frozen
resources. The local path configuration is adapted to use included snapshots;
the matrix/RTL contents and the decoding arithmetic are unchanged. These are
three actual paper configurations, not a fixed-base-matrix Z-only experiment.

## R4.Archive: inspect and identify the exact artifact

`python scripts/verify_package.py` checks file hashes, selected software budgets,
profile consistency, FER counts and hardware-report values. The command is
lightweight and never launches long simulations. The revision is identified by
its Git commit and the `reviewer-artifacts-20261118` tag. Original artifacts remain
in their earlier locations. The revised leakage-check files are not part of
this upload. Third-party data and publisher PDFs are not redistributed.
