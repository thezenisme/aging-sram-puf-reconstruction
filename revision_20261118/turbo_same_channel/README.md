> For the exact manuscript configuration and portable commands, see
> [the reviewer guide](../REVIEWER_GUIDE.md). Historical notes below
> may describe other development configurations; only the guide selects the paper run.

# Turbo ECC on the canonical SRAM-PUF stress channel

This is an independent software comparison. No Proposed, Polar, or NR-LDPC
implementation is replaced or edited. The user confirmed the main profile
with **768 enrollment probabilities 0.15 and 3328 probabilities 0.01**, not
the separate NR hotspot-0.25 diagnostic.

## Configuration fixed before observing the FER sweep

| Item | Setting |
|---|---|
| Payload / physical observations | 2048 / 4096 bits |
| Effective payload rate | 1/2 |
| Code | Parallel concatenation of two LTE 8-state recursive systematic convolutional codes |
| QPP interleaver | K=2048, f1=31, f2=64 |
| Trellis termination | Both constituents start and end at state zero; 12 total tail bits |
| Mother code | 3K+12 = 6156 bits |
| Rate matching | LTE subblock interleaving, full circular buffer, RV0, E=4096 |
| Decoder | Original srsLTE floating-point Max-Log-MAP |
| Iterations | 10 complete iterations = 20 constituent MAP decodes per frame (paper configuration) |
| Early stopping | None; no ground-truth stopping, no CRC stopping |
| CRC | None; this is a Turbo code-block baseline, not a full LTE transport-block chain |
| Scan | noise_floor = 0.001 through 0.055, step 0.001; 55 points |
| Frames | 100000 per point; 5,500,000 total (paper configuration) |
| Aging scale | Fixed at 2, never reverse-solved from target average BER |
| Metric | Payload FER: at least one wrong bit among 2048 decoded payload bits |

The absence of transport CRC differs from the NR baseline (which adds CRC16).
Both nevertheless use the same 2048-bit payload and 4096 physical observations;
the CRC overhead and fixed Turbo iteration policy must be stated in a paper.
One Turbo iteration is not computationally equivalent to one LDPC iteration.
No equal-latency or equal-hardware-cost claim follows from these software results.

## Exact channel and LLR boundary

```text
p_aged[i] = min(2 * p_enrollment[i] + noise_floor, 0.5)
error[i] ~ independent Bernoulli(p_aged[i])
received[i] = transmitted[i] XOR error[i]
LLR[i] = (1 - 2*received[i]) * log((1-p_enrollment[i])/p_enrollment[i])
```

These are spatially heterogeneous independent flips, not a jointly correlated
burst-event model. The measured mean raw BER is the plot x-axis. The expected
mean BER spans 0.0735 to 0.1275. The original profile is snapshotted for each run.
Hotspot ordering is preserved in physical channel coordinates after rate matching.
The Turbo internal QPP interleaver is not an extra physical interleaver that
rearranges the profile.

Only registration reliability reaches the decoder; aging probabilities generate
errors, not LLR magnitudes. Neither Proposed's mask nor UEP mapping is imported.
Untransmitted mother-code positions get **zero LLR**. The native wrapper reverses
the external log(P0/P1) sign to match srsLTE's log(P1/P0) convention.

The RV0 mapping contains 4096 unique mother-code positions: 1920 data systematic,
1084 parity-1, 1084 parity-2, and 8 tail positions. It is not an ad hoc policy
that preserves all systematic/tail bits.

The channel is implemented as C XOR e, which is algebraically the ECC portion
of helper-data reconstruction: W=X XOR C, X'=X XOR e, W XOR X'=C XOR e.
Hashing/KDF and hardware implementation are outside this experiment.

## Source and reproducibility

Upstream: [srsRAN_4G / former srsLTE](https://github.com/srsran/srsRAN_4G/tree/8f9ce13b1cb1892ba971dba66f49f6e4e579ecaa)

- Tag: `release_17_12`
- Commit: `8f9ce13b1cb1892ba971dba66f49f6e4e579ecaa`
- Original files: `vendor/srslte_17_12/`
- License: **AGPL-3.0-or-later**; retain the upstream license, copyright,
  native integration sources, and attribution when sharing the artifact.
- This older source was selected because it exposes an existing floating-point
  Max-Log-MAP decoder, not based on observed comparative FER.
- Local wrappers and compatibility shims integrate the upstream code; they are
  not claimed to be a byte-for-byte execution of an entire LTE software stack.

Standard basis: 3GPP TS 36.212, sections 5.1.3.2 (Turbo encoding/QPP) and 5.1.4.1
(Turbo rate matching). Upstream original source and local source hashes are
recorded with results.

## Run

Build the native library with the accompanying build script, then run:

```powershell
& .\native\build_native.ps1
python -m unittest discover -s tests -v
python -u run_turbo_same_channel.py --frames 1000 --iterations 8 --workers 8 --output results_turbo_lte_qpp_1000
```

The runner refuses to overwrite a nonempty result directory. It writes each
completed point to `point_NNN.json`, refreshes `fer_summary.csv`, and records
the complete configuration and completion status in `provenance.json`.
Small smoke runs are functional checks only and stored separately.

The seed schedule and random-generation order match the NR runner. With the
same point grid, seed, profile, and 1000 frames, the physical error patterns
are paired even though the encoded codewords differ.

Zero failures out of 1000 frames means only **no failures observed**; the
one-sided 95% binomial upper bound is approximately 0.00299. These data cannot
establish a FER of 1e-6.

## Completed run

The completed 55-point scan is in `results_turbo_lte_qpp_1000/`.
See `RESULTS.md` for selected measured results and verification details.
