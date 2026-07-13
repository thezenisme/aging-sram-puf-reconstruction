"""Compute amplitude-independent spatial metrics from PSD error vectors.

The input vectors are per-position residual error probabilities accumulated
over one Monte Carlo seed.  Each vector is centered before PSD/ACF analysis,
so the reported metrics characterize spatial shape rather than error volume.
"""

import argparse
import csv
from pathlib import Path

import numpy as np


SCHEMES = {
    "Raw PUF noise": "raw_error_vector.csv",
    "Continuous baseline": "baseline_error_vector.csv",
    "Continuous + Mask": "masked_baseline_error_vector.csv",
    "Proposed": "optimized_error_vector.csv",
}


def read_vector(path: Path) -> np.ndarray:
    text = path.read_text(encoding="ascii").strip()
    return np.fromstring(text, sep=",", dtype=float)


def normalized_metrics(values: np.ndarray, lf_fraction: float, max_lag: int):
    centered = values - np.mean(values)
    spectrum = np.abs(np.fft.rfft(centered)) ** 2
    spectrum[0] = 0.0
    total_power = float(np.sum(spectrum))

    positive_bins = len(spectrum) - 1
    lf_bins = max(1, int(np.ceil(positive_bins * lf_fraction)))
    normalized_psd = spectrum / total_power if total_power > 0.0 else spectrum
    lf_power_fraction = float(np.sum(normalized_psd[1 : lf_bins + 1]))

    # Circular ACF avoids the unstable edge normalization at very large lags.
    acf = np.fft.irfft(np.abs(np.fft.rfft(centered)) ** 2, n=len(centered))
    normalized_acf = acf / acf[0] if acf[0] > 0.0 else np.zeros_like(acf)
    usable_lag = min(max_lag, len(values) - 1)
    local = normalized_acf[1 : usable_lag + 1]
    peak_offset = int(np.argmax(np.abs(local))) if len(local) else 0

    return {
        "MeanResidualBER": float(np.mean(values)),
        "SpatialVariance": float(np.mean(centered**2)),
        "NormalizedLFFraction": lf_power_fraction,
        "RhoLag1": float(normalized_acf[1]) if len(values) > 1 else 0.0,
        "MeanAbsRhoLag1To32": float(np.mean(np.abs(normalized_acf[1:33]))),
        "MaxAbsRhoLag1ToMax": float(np.abs(local[peak_offset])) if len(local) else 0.0,
        "PeakLag": peak_offset + 1 if len(local) else 0,
        "LFBins": lf_bins,
        "NormalizedPSD": normalized_psd,
        "NormalizedACF": normalized_acf,
    }


def write_rows(path: Path, fieldnames, rows):
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, help="Directory containing seed_* folders")
    parser.add_argument("output", type=Path)
    parser.add_argument("--lf-fraction", type=float, default=0.05)
    parser.add_argument("--max-lag", type=int, default=256)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    seed_dirs = sorted(path for path in args.root.glob("seed_*") if path.is_dir())
    if not seed_dirs:
        raise SystemExit(f"No seed directories found under {args.root}")

    rows = []
    curves = {scheme: [] for scheme in SCHEMES}
    for seed_dir in seed_dirs:
        result_dirs = [path for path in seed_dir.iterdir() if path.is_dir()]
        if len(result_dirs) != 1:
            raise SystemExit(f"Expected one result directory in {seed_dir}")
        result_dir = result_dirs[0]
        for scheme, filename in SCHEMES.items():
            metrics = normalized_metrics(
                read_vector(result_dir / filename), args.lf_fraction, args.max_lag
            )
            rows.append(
                {
                    "Seed": seed_dir.name,
                    "Scheme": scheme,
                    "MeanResidualBER": f"{metrics['MeanResidualBER']:.10g}",
                    "SpatialVariance": f"{metrics['SpatialVariance']:.10g}",
                    "NormalizedLFFractionPct": f"{100.0 * metrics['NormalizedLFFraction']:.8f}",
                    "RhoLag1": f"{metrics['RhoLag1']:.10g}",
                    "MeanAbsRhoLag1To32": f"{metrics['MeanAbsRhoLag1To32']:.10g}",
                    "MaxAbsRhoLag1To256": f"{metrics['MaxAbsRhoLag1ToMax']:.10g}",
                    "PeakLag": metrics["PeakLag"],
                    "LFBins": metrics["LFBins"],
                }
            )
            curves[scheme].append(metrics)

    fields = list(rows[0].keys())
    write_rows(args.output / "normalized_spatial_metrics_per_seed.csv", fields, rows)

    summary_rows = []
    numeric_fields = [
        "MeanResidualBER",
        "SpatialVariance",
        "NormalizedLFFractionPct",
        "RhoLag1",
        "MeanAbsRhoLag1To32",
        "MaxAbsRhoLag1To256",
    ]
    for scheme in SCHEMES:
        scheme_rows = [row for row in rows if row["Scheme"] == scheme]
        summary = {"Scheme": scheme, "Seeds": len(scheme_rows)}
        for field in numeric_fields:
            data = np.array([float(row[field]) for row in scheme_rows])
            summary[f"{field}_Mean"] = f"{np.mean(data):.10g}"
            summary[f"{field}_SD"] = f"{np.std(data, ddof=1):.10g}"
        summary_rows.append(summary)
    write_rows(
        args.output / "normalized_spatial_metrics_summary.csv",
        list(summary_rows[0].keys()),
        summary_rows,
    )

    for scheme, metrics_list in curves.items():
        safe_name = scheme.lower().replace(" ", "_").replace("+", "plus")
        psd = np.mean([item["NormalizedPSD"] for item in metrics_list], axis=0)
        acf = np.mean([item["NormalizedACF"] for item in metrics_list], axis=0)
        np.savetxt(
            args.output / f"normalized_psd_{safe_name}.csv",
            np.column_stack((np.arange(len(psd)), psd)),
            delimiter=",",
            header="FrequencyIndex,NormalizedPSD",
            comments="",
        )
        np.savetxt(
            args.output / f"normalized_acf_{safe_name}.csv",
            np.column_stack((np.arange(args.max_lag + 1), acf[: args.max_lag + 1])),
            delimiter=",",
            header="Lag,NormalizedACF",
            comments="",
        )

    print(f"Analyzed {len(seed_dirs)} seeds; results written to {args.output}")


if __name__ == "__main__":
    main()
