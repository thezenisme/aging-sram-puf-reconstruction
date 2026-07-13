"""Generate a lightweight QC-PEG candidate for all-zero-codeword screening."""

from __future__ import annotations

import argparse
import json
from collections import deque
from pathlib import Path

import numpy as np


N = 4096
K = 2048
Z = 128
BASE_ROWS = 16
BASE_COLS = 32
NORMAL_DEGREE = 3
STRONG_DEGREE = 12
STRONG_COLS = (0, 10, 20)


def row_distances(base: np.ndarray, source_col: int) -> list[int | None]:
    distances: list[int | None] = [None] * BASE_ROWS
    seen_cols = {source_col}
    queue = deque([("c", source_col, 0)])
    while queue:
        kind, node, distance = queue.popleft()
        if kind == "c":
            for row in np.flatnonzero(base[:, node] >= 0):
                row = int(row)
                if distances[row] is None:
                    distances[row] = distance + 1
                    queue.append(("r", row, distance + 1))
        else:
            for col in np.flatnonzero(base[node, :] >= 0):
                col = int(col)
                if col not in seen_cols:
                    seen_cols.add(col)
                    queue.append(("c", col, distance + 1))
    return distances


def creates_qc_4cycle(base: np.ndarray, row: int, col: int, shift: int) -> bool:
    for previous_row in np.flatnonzero(base[:, col] >= 0):
        previous_row = int(previous_row)
        current_difference = (shift - int(base[previous_row, col])) % Z
        for other_col in range(BASE_COLS):
            if other_col == col:
                continue
            if base[row, other_col] >= 0 and base[previous_row, other_col] >= 0:
                other_difference = (
                    int(base[row, other_col]) - int(base[previous_row, other_col])
                ) % Z
                if current_difference == other_difference:
                    return True
    return False


def generate(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base = np.full((BASE_ROWS, BASE_COLS), -1, dtype=np.int16)
    row_degree = np.zeros(BASE_ROWS, dtype=np.int16)
    strong_row_degree = np.zeros(BASE_ROWS, dtype=np.int16)

    # Interleave strong and normal columns so early PEG decisions do not reserve
    # all low-load checks for one class.
    order = [0, 1, 10, 2, 20] + [c for c in range(BASE_COLS) if c not in {0, 1, 2, 10, 20}]
    for col in order:
        target = STRONG_DEGREE if col in STRONG_COLS else NORMAL_DEGREE
        for edge_index in range(target):
            distances = row_distances(base, col)
            candidates = [r for r in range(BASE_ROWS) if base[r, col] < 0]
            rng.shuffle(candidates)

            def key(row: int) -> tuple[int, int, int]:
                distance = distances[row]
                distance_rank = BASE_ROWS * 4 if distance is None else distance
                anchor_load = int(strong_row_degree[row]) if col in STRONG_COLS else 0
                return (-distance_rank, anchor_load, int(row_degree[row]))

            candidates.sort(key=key)
            placed = False
            for row in candidates:
                shifts = rng.permutation(Z)
                for shift in shifts:
                    if not creates_qc_4cycle(base, row, col, int(shift)):
                        base[row, col] = int(shift)
                        row_degree[row] += 1
                        if col in STRONG_COLS:
                            strong_row_degree[row] += 1
                        placed = True
                        break
                if placed:
                    break
            if not placed:
                raise RuntimeError(f"unable to place edge {edge_index} of column {col}")
    return base


def export(base: np.ndarray, outdir: Path, seed: int) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    h_header = outdir / "h_matrix_1_2_long.h"
    g_header = outdir / "g_matrix_1_2_long.h"
    source = outdir / "matrix_data_1_2_long.c"

    h_header.write_text("""#ifndef H_MAT_1_2_LONG
#define H_MAT_1_2_LONG
#include <stdint.h>
#define N_1_2_LONG 4096
#define K_1_2_LONG 2048
#define M_1_2_LONG 2048
#define EXPANSION_FACTOR_Z 128
extern const uint16_t H_row_indices_1_2_long[2048][64];
extern const uint8_t H_row_degrees_1_2_long[2048];
#define NUM_STRONG_ANCHORS 3
static const int STRONG_ANCHOR_COLS[] = { 0, 1280, 2560 };
#define LLR_SCALE_ERASURE 0.0f
#define LLR_SCALE_STRONG 1.0f
#define LLR_SCALE_WEAK 0.6f
extern const uint8_t COL_TYPE_MASK[];
#endif
""", encoding="ascii")
    g_header.write_text("""#ifndef G_MAT_1_2_LONG
#define G_MAT_1_2_LONG
#include <stdint.h>
#define G_ROWS_1_2_LONG 2048
#define MAX_G_ROW_DEGREE 4096
extern const uint16_t G_row_indices_1_2_long[2048][MAX_G_ROW_DEGREE];
extern const uint16_t G_row_degrees_1_2_long[2048];
#endif
""", encoding="ascii")

    rows: list[list[int]] = []
    for base_row in range(BASE_ROWS):
        entries = [(col, int(base[base_row, col])) for col in range(BASE_COLS)
                   if base[base_row, col] >= 0]
        for lifted_row in range(Z):
            rows.append([col * Z + ((lifted_row + shift) % Z)
                         for col, shift in entries])
    col_degrees = [STRONG_DEGREE if col // Z in STRONG_COLS else NORMAL_DEGREE
                   for col in range(N)]
    col_mask = [1 if col // Z in STRONG_COLS else 0 for col in range(N)]

    with source.open("w", encoding="ascii") as stream:
        stream.write('#include "h_matrix_1_2_long.h"\n#include "g_matrix_1_2_long.h"\n')
        stream.write("const uint16_t H_row_indices_1_2_long[2048][64] = {\n")
        for row in rows:
            padded = row + [0] * (64 - len(row))
            stream.write("{" + ",".join(map(str, padded)) + "},\n")
        stream.write("};\nconst uint8_t H_row_degrees_1_2_long[2048] = {")
        stream.write(",".join(str(len(row)) for row in rows) + "};\n")
        stream.write("const uint8_t H_col_degrees_1_2_long[4096] = {")
        stream.write(",".join(map(str, col_degrees)) + "};\n")
        stream.write("const uint8_t COL_TYPE_MASK[4096] = {")
        stream.write(",".join(map(str, col_mask)) + "};\n")
        # Screening uses the all-zero codeword, so a compact zero generator is
        # sufficient. The selected H is re-exported with a full G afterwards.
        stream.write("const uint16_t G_row_indices_1_2_long[2048][4096] = {{0}};\n")
        stream.write("const uint16_t G_row_degrees_1_2_long[2048] = {0};\n")

    np.savetxt(outdir / "base_shifts.csv", base, fmt="%d", delimiter=",")
    metadata = {
        "seed": seed,
        "construction": "base-graph PEG distance selection plus QC 4-cycle screening",
        "screening_generator_only": True,
        "N": N, "K": K, "Z": Z,
        "strong_base_columns": list(STRONG_COLS),
        "strong_degree": STRONG_DEGREE,
        "normal_degree": NORMAL_DEGREE,
        "base_row_degrees": np.sum(base >= 0, axis=1).astype(int).tolist(),
        "strong_edges_per_base_row": np.sum(base[:, STRONG_COLS] >= 0, axis=1).astype(int).tolist(),
        "qc_4cycle_screen": "passed during every edge insertion",
    }
    (outdir / "matrix_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    export(generate(args.seed), args.outdir, args.seed)


if __name__ == "__main__":
    main()
