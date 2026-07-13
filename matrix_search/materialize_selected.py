"""Re-export a screened QC parity-check matrix with a full orthogonal G."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import numpy as np

from generate_rate12_long import (
    compute_g_nullspace_fallback,
    compute_g_orthogonal,
    export_files,
    verify_orthogonality_probabilistic,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--outdir", type=Path)
    args = parser.parse_args()
    candidate = args.candidate.resolve()
    outdir = (args.outdir or (candidate / "full_matrix")).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    base = np.loadtxt(candidate / "base_shifts.csv", delimiter=",", dtype=int)
    if base.shape != (16, 32):
        raise ValueError(f"unexpected base matrix shape: {base.shape}")
    H = np.zeros((2048, 4096), dtype=np.uint8)
    for row in range(16):
        for col in range(32):
            shift = int(base[row, col])
            if shift >= 0:
                indices = np.arange(128)
                H[row * 128 + indices, col * 128 + ((indices + shift) % 128)] = 1

    G = compute_g_orthogonal(H)
    if G is None:
        G = compute_g_nullspace_fallback(H, 2048)
    if G is None or not verify_orthogonality_probabilistic(G, H, num_tests=50):
        raise RuntimeError("failed to construct or verify the full generator matrix")

    config = {"suffix": "1_2_long", "n": 4096, "k": 2048, "z": 128}
    previous = Path.cwd()
    try:
        os.chdir(outdir)
        export_files(H, G, config, [0, 10, 20])
    finally:
        os.chdir(previous)
    (outdir / "MATERIALIZATION.json").write_text(json.dumps({
        "source_candidate": str(candidate),
        "base_shifts": "../base_shifts.csv",
        "full_generator": True,
        "orthogonality_random_tests": 50,
        "screening_H_preserved": bool(np.all(np.sum(H, axis=0) ==
            np.array([12 if col // 128 in {0, 10, 20} else 3 for col in range(4096)]))),
    }, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
