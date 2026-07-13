import csv
import os
import sys
from pathlib import Path

import numpy as np


def parse_curve(path):
    rows = []
    with open(path, newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) >= 2:
                rows.append(float(row[1]))
    return np.array(rows, dtype=float)


def parse_vector(path):
    text = Path(path).read_text().strip()
    if not text:
        return np.array([], dtype=float)
    return np.array([float(x) for x in text.split(",") if x], dtype=float)


def write_curve(path, header, values):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for i, value in enumerate(values):
            writer.writerow([i, f"{value:.10f}"])


def write_vector(path, values):
    Path(path).write_text(",".join(f"{v:.10f}" for v in values))


def average(seed_dirs, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    curve_files = {
        "psd_raw.csv": ("Frequency_Index", "PSD_Value"),
        "psd_baseline.csv": ("Frequency_Index", "PSD_Value"),
        "psd_masked_baseline.csv": ("Frequency_Index", "PSD_Value"),
        "psd_optimized.csv": ("Frequency_Index", "PSD_Value"),
        "autocorr_raw.csv": ("Lag", "Autocorrelation"),
        "autocorr_baseline.csv": ("Lag", "Autocorrelation"),
        "autocorr_masked_baseline.csv": ("Lag", "Autocorrelation"),
        "autocorr_optimized.csv": ("Lag", "Autocorrelation"),
    }
    vector_files = [
        "raw_error_vector.csv",
        "baseline_error_vector.csv",
        "masked_baseline_error_vector.csv",
        "optimized_error_vector.csv",
    ]

    for name, header in curve_files.items():
        arrays = [parse_curve(Path(sd) / name) for sd in seed_dirs if (Path(sd) / name).exists()]
        if not arrays:
            print(f"WARNING: missing {name}")
            continue
        min_len = min(len(a) for a in arrays)
        avg = np.mean([a[:min_len] for a in arrays], axis=0)
        write_curve(out / name, header, avg)

    for name in vector_files:
        arrays = [parse_vector(Path(sd) / name) for sd in seed_dirs if (Path(sd) / name).exists()]
        if not arrays:
            print(f"WARNING: missing {name}")
            continue
        min_len = min(len(a) for a in arrays)
        avg = np.mean([a[:min_len] for a in arrays], axis=0)
        write_vector(out / name, avg)

    fer_rows = []
    for sd in seed_dirs:
        for path in Path(sd).glob("fer_comparison_length_*.csv"):
            with open(path, newline="") as f:
                reader = csv.reader(f)
                next(reader, None)
                for row in reader:
                    if len(row) >= 9:
                        fer_rows.append([float(x) for x in row[:9]])
                    elif len(row) >= 7:
                        legacy = [float(x) for x in row[:7]]
                        fer_rows.append([
                            legacy[0], legacy[1], legacy[2], float("nan"),
                            legacy[3], legacy[4], legacy[5], float("nan"), legacy[6],
                        ])

    if fer_rows:
        arr = np.array(fer_rows, dtype=float)
        avg = np.mean(arr, axis=0)
        with open(out / "fer_comparison_length_long.csv", "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Test_ID",
                "Actual_BER",
                "Baseline_FER",
                "Masked_Baseline_FER",
                "Optimized_FER",
                "Improvement",
                "Avg_Iter_Baseline",
                "Avg_Iter_Masked_Baseline",
                "Avg_Iter_Optimized",
            ])
            writer.writerow([
                int(round(avg[0])),
                f"{avg[1]:.5f}",
                f"{avg[2]:.6f}",
                f"{avg[3]:.6f}",
                f"{avg[4]:.6f}",
                f"{avg[5]:.1f}",
                f"{avg[6]:.2f}",
                f"{avg[7]:.2f}",
                f"{avg[8]:.2f}",
            ])

    print(f"Averaged {len(seed_dirs)} seed dirs -> {out_dir}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python average_psd_current.py <out_dir> <seed_dir1> ...")
        sys.exit(1)
    average(sys.argv[2:], sys.argv[1])
