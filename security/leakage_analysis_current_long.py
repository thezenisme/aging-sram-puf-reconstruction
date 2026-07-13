#!/usr/bin/env python3
"""
Current long-code helper-data leakage sanity check.

This script matches the current paper-reproduction experiment more closely than
the older leakage_analysis.py:
  - N=4096, A=Z=128
  - top-A profile entries are soft-erased (LLR=0)
  - remaining cells use the current 8-level staircase thresholds
  - response polarity is sampled independently from reliability buckets

It tests whether public helper categories {mask, unsigned magnitude bucket}
carry response polarity information under the usual SRAM-PUF assumption that
cell reliability is independent of the enrolled response bit.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np


N = 4096
K = 2048
Z = 128
A = Z
SCALE = 2.0
NOISE_FLOOR = 0.001
PROFILE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "puf_profile_long.h"
)

THRESHOLDS = [0.0, 0.5, 1.0, 1.5, 2.0, 2.8, 3.5, 4.5, math.inf]
QUANT_VALUES = [2, 4, 6, 9, 14, 20, 28, 35]

N_TRIALS = 20000
SEED = 20260623


def load_profile(path: Path) -> np.ndarray:
    text = path.read_text(encoding="ascii", errors="ignore")
    match = re.search(r"REAL_PUF_ERROR_RATES\[[^\]]+\]\s*=\s*\{(.*?)\};", text, re.S)
    if not match:
        raise ValueError("could not find REAL_PUF_ERROR_RATES array")
    values = [float(x) for x in re.findall(r"\b0\.\d+\b", match.group(1))]
    if len(values) != N:
        raise ValueError(f"expected {N} profile values, got {len(values)}")
    return np.array(values, dtype=np.float64)


def build_top_a_mask(profile: np.ndarray) -> np.ndarray:
    # Sort by descending p, then ascending index for deterministic tie-breaks.
    order = np.lexsort((np.arange(N), -profile))
    mask = np.zeros(N, dtype=bool)
    mask[order[:A]] = True
    return mask


def assign_categories(profile: np.ndarray, erased: np.ndarray) -> np.ndarray:
    # category 0 is the public erased-mask category; 1..8 are magnitude buckets.
    categories = np.zeros(N, dtype=np.int16)
    for i, p_puf in enumerate(profile):
        if erased[i]:
            categories[i] = 0
            continue
        p_total = min(max(p_puf * SCALE + NOISE_FLOOR, 0.001), 0.49)
        llr = math.log((1.0 - p_total) / p_total)
        for k in range(len(THRESHOLDS) - 1):
            if THRESHOLDS[k] <= llr < THRESHOLDS[k + 1]:
                categories[i] = k + 1
                break
    return categories


def summarize(profile: np.ndarray, erased: np.ndarray, categories: np.ndarray) -> None:
    print("=== Current Long Helper-Data Leakage Sanity Check ===")
    print(f"Profile: {PROFILE_PATH}")
    print(f"N={N}, K={K}, A=Z={A}, scale={SCALE}, noise_floor={NOISE_FLOOR}")
    print(f"profile-hot p>=0.10: {int(np.sum(profile >= 0.10))}")
    print(f"top-A erased: {int(np.sum(erased))}")
    print(f"erased inside [0..127]: {int(np.sum(erased[:Z]))}/{A}")
    print()

    print("Category distribution:")
    print("  cat  helper       count")
    for cat in range(9):
        count = int(np.sum(categories == cat))
        if cat == 0:
            label = "ERASE/LLR=0"
        else:
            label = f"q={cat-1}, mag={QUANT_VALUES[cat-1]}"
        print(f"  {cat:>3}  {label:<12} {count:>6}")
    print()


def leakage_trial(categories: np.ndarray, rng: np.random.Generator) -> list[dict]:
    counts = np.zeros((9, 2), dtype=np.int64)
    for _ in range(N_TRIALS):
        response = rng.integers(0, 2, size=N, dtype=np.int8)
        for cat in range(9):
            m = categories == cat
            total = int(np.sum(m))
            if total == 0:
                continue
            ones = int(np.sum(response[m]))
            counts[cat, 0] += total - ones
            counts[cat, 1] += ones

    rows = []
    for cat in range(9):
        total = int(counts[cat].sum())
        n_cells = int(np.sum(categories == cat))
        if total == 0:
            rows.append({"cat": cat, "n": n_cells, "empty": True})
            continue
        p1 = counts[cat, 1] / total
        maxp = max(p1, 1.0 - p1)
        rows.append({
            "cat": cat,
            "n": n_cells,
            "p1": p1,
            "bias": abs(p1 - 0.5),
            "hbit": -math.log2(maxp),
            "empty": False,
        })
    return rows


def main() -> None:
    profile = load_profile(PROFILE_PATH)
    erased = build_top_a_mask(profile)
    categories = assign_categories(profile, erased)
    summarize(profile, erased, categories)

    rows = leakage_trial(categories, np.random.default_rng(SEED))

    h_cond = 0.0
    max_bias = 0.0
    print("Polarity leakage by public helper category:")
    print("  cat   count    Pr(R=1|cat)      bias    Hinf/bit")
    for row in rows:
        if row["empty"]:
            print(f"  {row['cat']:>3}  {row['n']:>6}       empty")
            continue
        h_cond += row["n"] * row["hbit"]
        max_bias = max(max_bias, row["bias"])
        print(
            f"  {row['cat']:>3}  {row['n']:>6}       {row['p1']:.6f}  "
            f"{row['bias']:.6f}    {row['hbit']:.6f}"
        )

    after_syndrome = h_cond - (N - K)
    print()
    print(f"Hinf(R | mask,q) ~= {h_cond:.2f} bits")
    print(f"Hinf(R | mask,q,syndrome) >= {after_syndrome:.2f} bits using rank(H)<=N-K")
    print(f"Max observed category bias: {max_bias:.6f}")
    print()
    print("Caveat: this is a sanity check under the assumption that response polarity")
    print("is independent of reliability. It does not prove security for biased cells")
    print("or for a real measured dataset where reliability and polarity may correlate.")


if __name__ == "__main__":
    main()
