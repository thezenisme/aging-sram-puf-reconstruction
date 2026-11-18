# Paper Turbo FPGA implementation (Table VII)

This snapshot comes from the active Vivado top-level project producing the
reported **6493 LUTs, 5461 registers, 21 BRAM tiles and 1 DSP**. It is a local
Belov--Mosin architecture adaptation (upstream MIT license included).
The complete comparison top accepts 4096 LLRs, decodes 2048 information bits
and performs ten complete iterations with five-bit internal arithmetic.

Run from this folder with Vivado 2022.2:
```
vivado -mode batch -source scripts/synth_paper.tcl
powershell -File scripts/sim_paper.ps1 -VivadoBin PATH_TO_VIVADO_BIN
```
Target: xczu3eg-sfvc784-1-i. The synthesis is standard top-level synthesis,
not OOC; no clock constraints are supplied. Reference reports are preserved
in `reference_reports/`. A separate development OOC run produced 7496 LUTs
and is deliberately not used for the paper's 6493-LUT result.

The archived testbench reports START-to-DONE = 258993 cycles. Its reset-to-DONE
counter is 258995 and is a different endpoint. These are behavioral-simulation
cycle counts, not post-route timing, measured throughput or channel FER.
The frozen test vectors are noiseless encoder/decoder functional checks.
The RTL excludes PUF readout, helper-data generation and hashing/KDF.
