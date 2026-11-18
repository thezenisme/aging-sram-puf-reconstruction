> For the exact manuscript configuration and portable commands, see
> [the reviewer guide](../REVIEWER_GUIDE.md). Historical notes below
> may describe other development configurations; only the guide selects the paper run.

# 5G NR LDPC same-channel baseline

This directory is an independent software baseline for the SRAM-PUF aging
comparison. It does not modify the existing Polar or Proposed experiments.

The implementation uses `py3gpp==0.6.0`, which provides the 3GPP NR LDPC base
graphs, encoder, rate matcher, rate recovery, and layered min-sum-family
decoder.
The package is vendored under `vendor/` so the exact implementation used by
the run is retained with the experiment. See `requirements.txt` and the
upstream project for licensing and source information. `py3gpp` is distributed
under AGPL-3.0; retain its license and attribution when sharing this artifact.

## Configuration

The experiment uses a standard NR transport-block chain:

- payload: `A=2048` bits;
- transport-block CRC: CRC16;
- base graph: BG2;
- lifting factor: `Zc=208`;
- native punctured LDPC codeword: `10400` bits;
- rate matching: `E=4096` bits, `rv=0`, BPSK, one layer;
- effective payload rate: `2048/4096=1/2`;
- decoder: layered min-sum (`--decoder ms`, the default) or layered normalized
  min-sum (`--decoder nms`), **at most 20 iterations**. MS uses scaling factor
  `1.0`; NMS uses `0.75`;
- termination: after each complete layered iteration, stop if every check in
  the full mother-codeword syndrome `H*c=0` passes. The check includes the
  recovered punctured positions and filler bits, not just the payload.

The vendored decoder has a local `Termination="early"` extension, enabled by
this runner. `Termination="max"` retains the original fixed-iteration mode.
CRC and the known transmitted payload are **not** used to stop decoding.
A zero syndrome can still correspond to an incorrect codeword, so payload
FER remains measured against the transmitted payload. `mean_iterations`
averages actual iterations over **all** frames, including failed frames.

The physical channel has exactly the canonical `N=4096` profile used by the
same-channel Polar experiment. For each rate-matched bit,

```text
p_aged[i] = min(scale * p_enrollment[i] + noise_floor, 0.5)
```

The received bit is flipped with `p_aged[i]`. The decoder LLR magnitude uses
the enrollment profile only:

```text
abs(LLR[i]) = log((1-p_enrollment[i]) / p_enrollment[i])
```

No post-aging labels, Proposed UEP placement, or Proposed soft-erasure mask is
provided to the baseline.

## Self-test

The script runs a no-noise encoder/decoder self-test before starting a sweep:

```powershell
Set-Location D:\program\nr_ldpc_same_channel
python .\run_nr_ldpc_same_channel.py --decoder ms --smoke --output .\results_smoke_ms
```

The smoke run uses three points and two frames per point and writes to
`results_smoke_ms`. Run the regression tests with
`python -m unittest discover -s tests -v`.

The default `--decoder ms` path uses ordinary min-sum through the same layered
implementation (scaling factor 1.0). Use `--decoder nms` to reproduce the
earlier normalized-min-sum path. The two options keep the same profile, code
graph, channel, and stopping rule; both are layered schedules, not flooding
schedules.
The Python helper functions retain their previous `decoder="nms"` defaults
for audit-script compatibility; CLI runs explicitly pass the selected option
through the self-test and every worker. Each new provenance file records the
selected family, scaling factor and layered schedule.

When reusing commands recorded before this MS option was added (including
the hot025 and hot5 scans), explicitly append `--decoder nms` to reproduce
their decoder. Their old provenance hashes identify the historical runner;
they are not expected to match the runner after this CLI extension.

## Paper-comparison scan

The default scan uses the same fixed `scale=2` and noise-floor values
`0.001,...,0.055` as the manuscript-facing Polar scan. With 1,000 frames per
point:

```powershell
Set-Location D:\program\nr_ldpc_same_channel
python .\run_nr_ldpc_same_channel.py `
  --frames 1000 `
  --scale 2 `
  --workers 8 `
  --decoder ms `
  --output .\results_5g_nr_ldpc_ms_early_stop_1000
```

The output contains:

- `fer_summary.csv`: actual raw BER and end-to-end payload FER;
- `provenance.json`: exact code, channel, decoder, and run parameters.

The default output directory is `results_5g_nr_ldpc_ms_early_stop`. The runner
refuses to overwrite an existing result CSV or provenance file. Historical
`results_5g_nr_ldpc_1000` results and plots still describe **fixed 20-round**
decoding; they are not relabeled as early-stop results. A fresh full sweep is
required for the early-stop FER and mean-iteration curves. The completed
55-point, 1,000-frame-per-point early-stop sweep is available in
`results_5g_nr_ldpc_early_stop_1000/`; see its `RESULTS_SUMMARY.md` for the
verified comparison with fixed 20-round decoding. The small smoke
test is only a functional check, not a replacement paper dataset.
These archived full sweeps are NMS results; changing the CLI default to MS
does not relabel them or create a new full MS result set.

FER is one when the decoded 2048-bit payload differs from the transmitted
payload in any bit. Use `message_fer` as the primary reported metric;
`crc_failures` is only a transport-block diagnostic and is not a second FER.
The experiment stops at the ECC reconstruction boundary;
hash/KDF processing is intentionally outside this software comparison.

The direct `rate-matched codeword XOR channel-error` implementation is
algebraically equivalent to the helper-data form `W=X_enrollment XOR C`,
`X_aged=X_enrollment XOR e`, and `W XOR X_aged=C XOR e`. The equivalence and
selected results are recorded in `RESULTS_SUMMARY.md`.

This is a standard-code baseline, not a claim that 5G NR LDPC is an FPGA
implementation equivalent to the Proposed folded core.
