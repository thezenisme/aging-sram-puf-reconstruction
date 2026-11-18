> For the exact manuscript configuration and portable commands, see
> [the reviewer guide](../REVIEWER_GUIDE.md). Historical notes below
> may describe other development configurations; only the guide selects the paper run.

# Polar-SC same-channel baseline

This directory contains the second soft-decision baseline for the SRAM-PUF
revision experiments. It follows the Polar-based SRAM-PUF secret-generation
setting of Kestel et al., but uses matched-length configurations for the
external comparison:

- Polar SC with `N=4096`; evaluated dimensions include `K=512` (rate `1/8`)
  and `K=2048` (rate `1/2`);
- the rate preserves Kestel et al.'s published `(1024,128)` Polar-SC setting while
  matching the manuscript's 4096-bit response length;
- the manuscript-facing rate-1/2 baseline constructs its frozen set from the
  enrollment profile only; the legacy Kestel-inspired configuration uses a
  homogeneous BSC design BER of `0.15`;
- manuscript-result profile: 768 cells at `p=0.15`, 3328 cells at `p=0.01`;
- aged channel: `p_aged=min(scale*p_enrollment+noise_floor, 0.5)`;
- decoder LLR magnitude from enrollment `p_i`, with no post-aging labels,
  hotspot mask, hash, or KDF; the command-line LLR mode can be continuous or
  use the manuscript's eight-level staircase quantizer;
- FER means that the decoded `K`-bit message is not the transmitted message.

The baseline is an adapted same-channel Polar-SC implementation, not a literal
run of the Kestel authors' code. Its encoder and SC traversal follow the
`py-polar-codes` 1.2.2 `Encode`/`SCD` semantics (MIT) and were independently
cross-checked against that package. The helper-data/hash boundary is
intentionally outside this decoder-only comparison.

## Build

From PowerShell:

```powershell
Set-Location D:\program\polar_same_channel
g++ -O3 -std=c++17 -Wall -Wextra -o polar_sc_same_channel.exe polar_sc_same_channel.cpp
```

The default build uses `K=512` (`R=1/8`). Compile the rate-sweep variants with:

```powershell
g++ -O3 -std=c++17 -Wall -Wextra -DPOLAR_K=1024 -o polar_sc_rate_1_4.exe polar_sc_same_channel.cpp
g++ -O3 -std=c++17 -Wall -Wextra -DPOLAR_K=2048 -o polar_sc_rate_1_2.exe polar_sc_same_channel.cpp
g++ -O3 -std=c++17 -Wall -Wextra -DPOLAR_K=2048 -o polar_sc_profile_rate_1_2.exe polar_sc_same_channel.cpp
```

## Fixed-scale smoke run

```powershell
.\polar_sc_rate_1_8.exe --frames=2 --fixed-scale=2 --noise-floors=0.001,0.017 --construction=homogeneous-bsc --output=D:\program\polar_same_channel\smoke_fixed_scale_profile768
```

## Strict paper-comparison run

The manuscript-facing run fixes `scale=2` first and then sweeps exactly the
same 55 noise-floor values (`0.001` through `0.055`) as
`paper_artifact_minimal/results/main_rate12_long.csv`. This preserves the full
per-position channel rather than merely matching its average BER.

```powershell
$floors = ((1..55) | ForEach-Object { ($_ / 1000).ToString('0.000') }) -join ','
.\polar_sc_rate_1_8.exe --frames=1000 --fixed-scale=2 --noise-floors=$floors --construction=homogeneous-bsc --output=D:\program\polar_same_channel\fixed_scale2_profile768_rate_1_8_1000
.\polar_sc_rate_1_4.exe --frames=1000 --fixed-scale=2 --noise-floors=$floors --construction=homogeneous-bsc --output=D:\program\polar_same_channel\fixed_scale2_profile768_rate_1_4_1000
.\polar_sc_profile_rate_1_2.exe --frames=1000 --fixed-scale=2 --noise-floors=$floors --construction=profile-enrollment --output=D:\program\polar_same_channel\fixed_scale2_profile768_profile_construct_rate_1_2_1000
```

The rate-1/8 decoder observed zero failures at all 55 points. The rate-1/4
decoder observed one failure at noise floors `0.050`, `0.053`, and `0.055` and
zero failures at the other points. The old rate-1/2 folder used a homogeneous
BSC(0.15) construction. That design channel has capacity about `0.390`, below
rate 1/2, so its 938/1000 first-point failures are retained only as a diagnostic
result. The profile-enrollment construction supersedes it for manuscript
comparison. It uses no aged probabilities or post-aging labels. Its first-point
FER is 23/1000 at actual raw BER `0.07357`; FER reaches 302/1000 near raw BER
`0.08962`.

The key point near 9% raw BER was confirmed with 100,000 frames:

```powershell
.\polar_sc_rate_1_8.exe --frames=100000 --fixed-scale=2 --noise-floors=0.017 --output=D:\program\polar_same_channel\fixed_scale2_profile768_rate_1_8_noise0017_100k
```

It produced actual raw BER `0.089491` and zero failures in 100,000 frames. This
is a one-sided 95% zero-failure upper bound of approximately `3.0e-5`, not proof
that the true FER is zero.

## Profile-aware rate-1/2 staircase-quantized experiment

This is a separate ablation that keeps the rate-1/2 frozen set, channel,
profile, random seed, frame count, and SC decoder unchanged. It changes only
the decoder input from the continuous enrollment LLR
`log((1-p_i)/p_i)` to the manuscript-defined staircase mapping:

```text
thresholds = [0, 0.5, 1.0, 1.5, 2.0, 2.8, 3.5, 4.5, infinity]
magnitudes = [2, 4, 6, 9, 14, 20, 28, 35]
```

The quantizer uses enrollment-time `p_i`, not the simulated post-aging
probability. No mask or UEP mechanism is added. With the current two-valued
profile, the experiment uses magnitude 9 for `p_i=0.15` and magnitude 35 for
`p_i=0.01`; the remaining six reconstruction levels are not exercised.

```powershell
g++ -O3 -std=c++17 -Wall -Wextra -DPOLAR_K=2048 -o polar_sc_profile_quantized_rate_1_2.exe polar_sc_same_channel.cpp
$floors = ((1..55) | ForEach-Object { ($_ / 1000).ToString('0.000') }) -join ','
.\polar_sc_profile_quantized_rate_1_2.exe --frames=1000 --fixed-scale=2 --noise-floors=$floors --construction=profile-enrollment --llr-mode=staircase-enrollment --output=D:\program\polar_same_channel\fixed_scale2_profile768_profile_construct_staircase_rate_1_2_1000
```

Representative paired results are:

| Actual raw BER | Continuous FER | Staircase FER |
|---:|---:|---:|
| 0.073570 | 0.023 | 0.021 |
| 0.082416 | 0.106 | 0.109 |
| 0.089617 | 0.302 | 0.298 |
| 0.090317 | 0.346 | 0.331 |
| 0.095260 | 0.562 | 0.516 |
| 0.100317 | 0.768 | 0.743 |
| 0.107508 | 0.964 | 0.952 |
| 0.127597 | 1.000 | 1.000 |

The staircase result is lower at 34 of 55 points, equal at 13, and higher at
8, but both curves have nearly the same waterfall. With only 1000 frames per
point, small differences should be treated as pilot estimates rather than a
statistically established gain.

## Legacy homogeneous-BSC expanded scan through 0.20 actual raw BER

The extended fixed-scale scan keeps the same per-position channel law and uses
129 noise-floor points: `0`, `0.001`, ..., `0.127`, and `0.1275`. With the
768-hotspot profile and `scale=2`, these points cover approximately `0.0725`
through `0.20` actual raw BER. The plot axis starts at zero for context; no
artificial points are inserted below the minimum BER implied by the fixed
profile and scale.

```powershell
$floors = (@((0..127) | ForEach-Object { ($_ / 1000).ToString('0.000') }) + '0.1275') -join ','
.\polar_sc_rate_1_8.exe --frames=1000 --fixed-scale=2 --noise-floors=$floors --construction=homogeneous-bsc --output=D:\program\polar_same_channel\fixed_scale2_profile768_ber_to020_rate_1_8_1000
.\polar_sc_rate_1_4.exe --frames=1000 --fixed-scale=2 --noise-floors=$floors --construction=homogeneous-bsc --output=D:\program\polar_same_channel\fixed_scale2_profile768_ber_to020_rate_1_4_1000
.\polar_sc_rate_1_2.exe --frames=1000 --fixed-scale=2 --noise-floors=$floors --construction=homogeneous-bsc --output=D:\program\polar_same_channel\fixed_scale2_profile768_ber_to020_rate_1_2_1000
```

At the highest point, the observed FERs are `1.000` for rate `1/2`, `0.852`
for rate `1/4`, and `0/1000` for rate `1/8`. Across the full scan, rate `1/8`
has zero observed failures in 129,000 frames; this is a finite-sample result,
not proof of zero true FER.

These directories are retained as legacy diagnostics only. They use a
homogeneous BSC design channel (`design_channel_ber=0.15`) and must not be
merged with the profile-enrollment curves below.

## Profile-enrollment expanded scan through 0.20 actual raw BER

The manuscript-facing expanded scan uses the same 129 noise-floor points and
the same position-dependent channel law, but constructs the Polar frozen set
from the enrollment profile rather than from a homogeneous BSC. All three
rates use `N=4096`, `scale=2`, seed `20260916`, and 1,000 frames per point.

```powershell
$floors = (@((0..127) | ForEach-Object { ($_ / 1000).ToString('0.000') }) + '0.1275') -join ','
.\polar_sc_profile_rate_1_8.exe --frames=1000 --fixed-scale=2 --noise-floors=$floors --construction=profile-enrollment --output=D:\program\polar_same_channel\fixed_scale2_profile768_profile_construct_ber_to020_rate_1_8_1000
.\polar_sc_profile_rate_1_4.exe --frames=1000 --fixed-scale=2 --noise-floors=$floors --construction=profile-enrollment --output=D:\program\polar_same_channel\fixed_scale2_profile768_profile_construct_ber_to020_rate_1_4_1000
.\polar_sc_profile_rate_1_2.exe --frames=1000 --fixed-scale=2 --noise-floors=$floors --construction=profile-enrollment --output=D:\program\polar_same_channel\fixed_scale2_profile768_profile_construct_ber_to020_rate_1_2_1000
```

The new profile-enrollment curves cover actual BER approximately `0.0724` to
`0.2001`. At the final point, observed FER is `1.000` for rate `1/2`,
`0.999` for rate `1/4`, and `0.014` for rate `1/8`. The rate-1/8 result is a
finite-sample estimate from 1,000 frames per point, not a proof of zero FER.

## Rate-1/8 comparison boundary

Kestel et al.'s implemented design uses two `P(512,64)` SC codewords for a
128-bit key, four-bit quantized runtime soft information, and an input-BER
design point of 15%. The paper reports fewer than 100 failed noisy codewords in
`10^8` samples. The present `P(4096,512)` experiment preserves only the `1/8`
rate and the same-channel comparison boundary; it is not a literal reproduction
of that hardware configuration. All former target-mean-BER runs and the code
path that solved for scale have been removed.
