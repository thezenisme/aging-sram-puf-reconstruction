"""5G NR LDPC baseline on the canonical clustered SRAM-PUF aging channel.

The implementation uses the standardized 3GPP NR base graph and rate-matching
chain exposed by ``py3gpp``.  It is deliberately kept separate from the
manuscript's QC-LDPC implementation and from the Polar experiments.

The comparison boundary is an ECC reconstruction block: a random 2048-bit
payload is protected with the NR transport-block CRC, encoded with BG2, rate
matched to 4096 transmitted bits, passed through the same position-dependent
aging channel as the Polar experiment, and decoded with layered min-sum (MS)
or layered normalized min-sum (NMS).
The decoder receives enrollment-time reliability magnitudes only; it does not
receive post-aging labels or the proposed UEP/masking information.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import multiprocessing as mp
import os
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "vendor"
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))

from py3gpp.nrCRCEncode import nrCRCEncode  # noqa: E402
from py3gpp.nrCodeBlockSegmentLDPC import nrCodeBlockSegmentLDPC  # noqa: E402
from py3gpp.nrCodeBlockDesegmentLDPC import nrCodeBlockDesegmentLDPC  # noqa: E402
from py3gpp.nrCRCDecode import nrCRCDecode  # noqa: E402
from py3gpp.nrDLSCHInfo import nrDLSCHInfo  # noqa: E402
from py3gpp.nrLDPCDecode import nrLDPCDecode  # noqa: E402
from py3gpp.nrLDPCEncode import nrLDPCEncode  # noqa: E402
from py3gpp.nrRateMatchLDPC import nrRateMatchLDPC  # noqa: E402
from py3gpp.nrRateRecoverLDPC import nrRateRecoverLDPC  # noqa: E402


N_PHYSICAL = 4096
PAYLOAD_BITS = 2048
E_BITS = 4096
NOMINAL_RATE = PAYLOAD_BITS / E_BITS
BGN = 2
RV = 0
MODULATION = "BPSK"
LAYERS = 1
MAX_ITER = 20
NORMALIZED_MIN_SUM = 0.75
DEFAULT_DECODER = "ms"
DEFAULT_SEED = 20260916
DEFAULT_SCALE = 2.0


def load_profile(path: Path) -> np.ndarray:
    """Load exactly the REAL_PUF_ERROR_RATES initializer from a C header."""
    source = path.read_text(encoding="utf-8")
    match = re.search(
        r"REAL_PUF_ERROR_RATES\s*\[\s*4096\s*\]\s*=\s*\{(.*?)\}",
        source,
        flags=re.DOTALL,
    )
    if match is None:
        raise ValueError(f"REAL_PUF_ERROR_RATES initializer not found in {path}")
    values = np.asarray(
        [float(token) for token in re.findall(r"(?<![A-Za-z_])[0-9]+\.[0-9]+", match.group(1))],
        dtype=np.float64,
    )
    if values.size != N_PHYSICAL:
        raise ValueError(f"expected {N_PHYSICAL} profile values, found {values.size}")
    if np.any(values <= 0.0) or np.any(values >= 0.5):
        raise ValueError("profile probabilities must lie in (0, 0.5)")
    return values


def aged_probabilities(profile: np.ndarray, scale: float, noise_floor: float) -> np.ndarray:
    return np.minimum(scale * profile + noise_floor, 0.5)


def expected_ber(profile: np.ndarray, scale: float, noise_floor: float) -> float:
    return float(np.mean(aged_probabilities(profile, scale, noise_floor)))


def build_info() -> dict[str, Any]:
    info = nrDLSCHInfo(PAYLOAD_BITS, NOMINAL_RATE)
    return {key: (int(value) if isinstance(value, (np.integer, int)) else value)
            for key, value in info.items()}


def encode_payload(payload: np.ndarray, info: dict[str, Any]) -> np.ndarray:
    """Return the 4096-bit rate-matched NR codeword for one payload."""
    tb_with_crc = nrCRCEncode(payload.astype(np.int8), "16")[:, 0].astype(np.int8)
    code_blocks = nrCodeBlockSegmentLDPC(tb_with_crc, BGN)
    native_codeword = nrLDPCEncode(code_blocks, BGN)
    rate_matched = nrRateMatchLDPC(
        native_codeword, E_BITS, RV, MODULATION, LAYERS
    )
    if rate_matched.size != E_BITS or np.any(rate_matched < 0):
        raise RuntimeError("invalid rate-matched codeword")
    return rate_matched.astype(np.uint8, copy=False)


def decode_llr(
    llr: np.ndarray,
    info: dict[str, Any],
    decoder: str = "nms",
) -> tuple[np.ndarray, int, bool]:
    """Use the same layered check-node implementation for MS and NMS.

    A scaling factor of 1.0 is ordinary MS; 0.75 gives the existing NMS.
    The schedule, maximum iterations and full-syndrome early stop are shared.
    """
    if decoder not in {"ms", "nms"}:
        raise ValueError(f"unsupported decoder: {decoder!r}")
    scaling = 1.0 if decoder == "ms" else NORMALIZED_MIN_SUM
    recovered = nrRateRecoverLDPC(
        llr.astype(np.float64, copy=False),
        PAYLOAD_BITS,
        NOMINAL_RATE,
        RV,
        MODULATION,
        LAYERS,
        numCB=1,
    )
    decoded, iterations = nrLDPCDecode(
        recovered,
        BGN,
        MAX_ITER,
        Algorithm="Normalized min-sum",
        ScalingFactor=scaling,
        vectorize=True,
        Termination="early",
    )
    if decoded.shape[0] < PAYLOAD_BITS + 16:
        raise RuntimeError(f"decoder returned only {decoded.shape[0]} bits")
    block_with_crc, _ = nrCodeBlockDesegmentLDPC(
        decoded, BGN, PAYLOAD_BITS + 16
    )
    payload_hat, crc_value = nrCRCDecode(block_with_crc, "16")
    payload_hat = np.asarray(payload_hat).reshape(-1)[:PAYLOAD_BITS].astype(np.uint8)
    crc_ok = int(np.asarray(crc_value).reshape(-1)[0]) == 0
    return payload_hat, int(iterations), crc_ok


def self_test(profile: np.ndarray, decoder: str = "nms") -> dict[str, Any]:
    """Check the standard chain without channel errors before a sweep."""
    info = build_info()
    rng = np.random.default_rng(7)
    payload = rng.integers(0, 2, PAYLOAD_BITS, dtype=np.uint8)
    tx = encode_payload(payload, info)
    enrollment_llr = np.log((1.0 - profile) / profile)
    llr = np.where(tx == 0, enrollment_llr, -enrollment_llr)
    decoded, iterations, crc_ok = decode_llr(llr, info, decoder)
    if not np.array_equal(decoded, payload):
        raise RuntimeError("no-noise 5G NR LDPC self-test failed")
    if not crc_ok:
        raise RuntimeError("no-noise 5G NR LDPC CRC self-test failed")
    return {
        "payload_bits": PAYLOAD_BITS,
        "rate_matched_bits": E_BITS,
        "native_info": info,
        "self_test_iterations": iterations,
        "decoder": decoder,
    }


def run_point(
    point_index: int,
    noise_floor: float,
    frames: int,
    seed: int,
    scale: float,
    profile_path: str,
    decoder: str = "nms",
) -> dict[str, Any]:
    """Run one BER point in a separate process."""
    profile = load_profile(Path(profile_path))
    info = build_info()
    rng = np.random.default_rng(seed + point_index * 1000003)
    p_aged = aged_probabilities(profile, scale, noise_floor)
    enrollment_llr = np.log((1.0 - profile) / profile)

    raw_errors = 0
    total_bits = 0
    message_failures = 0
    crc_failures = 0
    total_iterations = 0

    for _ in range(frames):
        payload = rng.integers(0, 2, PAYLOAD_BITS, dtype=np.uint8)
        transmitted = encode_payload(payload, info)
        flips = rng.random(E_BITS) < p_aged
        received = transmitted ^ flips.astype(np.uint8)
        llr = np.where(received == 0, enrollment_llr, -enrollment_llr)

        decoded, iterations, crc_ok = decode_llr(llr, info, decoder)
        total_iterations += iterations
        raw_errors += int(np.count_nonzero(flips))
        total_bits += E_BITS
        failed = not np.array_equal(decoded, payload)
        if failed:
            message_failures += 1

        # The payload comparison is the primary FER definition. CRC is kept
        # as a separate diagnostic for the standard NR transport-block chain.
        if not crc_ok:
            crc_failures += 1

    actual = raw_errors / total_bits
    return {
        "point_index": point_index,
        "noise_floor": noise_floor,
        "scale": scale,
        "expected_raw_ber": expected_ber(profile, scale, noise_floor),
        "actual_raw_ber": actual,
        "frames": frames,
        "message_failures": message_failures,
        "message_fer": message_failures / frames,
        "crc_failures": crc_failures,
        "mean_iterations": total_iterations / frames,
    }


def parse_floors(text: str | None) -> list[float]:
    if text:
        values = [float(item.strip()) for item in text.split(",") if item.strip()]
    else:
        values = [i / 1000.0 for i in range(1, 56)]
    if not values or any(value < 0.0 for value in values):
        raise ValueError("noise floors must be non-negative and non-empty")
    return values


def write_outputs(
    output: Path,
    args: argparse.Namespace,
    profile: np.ndarray,
    self_test_info: dict[str, Any],
    rows: list[dict[str, Any]],
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    rows = sorted(rows, key=lambda row: row["point_index"])
    fields = [
        "target_raw_ber",
        "scale",
        "expected_raw_ber",
        "actual_raw_ber",
        "frames",
        "message_failures",
        "message_fer",
        "crc_failures",
        "mean_iterations",
        "noise_floor",
    ]
    with (output / "fer_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "target_raw_ber": row["expected_raw_ber"],
                "scale": row["scale"],
                "expected_raw_ber": row["expected_raw_ber"],
                "actual_raw_ber": row["actual_raw_ber"],
                "frames": row["frames"],
                "message_failures": row["message_failures"],
                "message_fer": row["message_fer"],
                "crc_failures": row["crc_failures"],
                "mean_iterations": row["mean_iterations"],
                "noise_floor": row["noise_floor"],
            })

    info = self_test_info["native_info"]
    metadata = {
        "algorithm": "5G NR LDPC, 3GPP base graph 2",
        "implementation": "py3gpp 0.6.0 with local full-syndrome early termination",
        "implementation_source": "https://github.com/catkira/py3gpp",
        "source_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                Path(__file__).resolve(),
                VENDOR / "py3gpp" / "nrLDPCDecode.py",
                VENDOR / "py3gpp" / "nrLDPCEncode.py",
            )
        },
        "profile": str(Path(args.profile).resolve()),
        "profile_length": int(profile.size),
        "profile_p_0.15_count": int(np.count_nonzero(np.isclose(profile, 0.15))),
        "profile_p_0.01_count": int(np.count_nonzero(np.isclose(profile, 0.01))),
        "payload_bits": PAYLOAD_BITS,
        "rate_matched_bits": E_BITS,
        "effective_payload_rate": NOMINAL_RATE,
        "transport_block_crc": "CRC16",
        "base_graph": BGN,
        "lifting_factor": int(info["Zc"]),
        "native_codeword_bits_after_puncturing": int(info["N"]),
        "code_block_bits": int(info["K"]),
        "filler_bits": int(info["F"]),
        "rate_matching": "NR LDPC rate matching, rv=0, BPSK, one layer",
        "decoder": (
            f"layered {'min-sum' if args.decoder == 'ms' else 'normalized min-sum'}, "
            f"max_iter={MAX_ITER}, "
            f"scaling_factor={1.0 if args.decoder == 'ms' else NORMALIZED_MIN_SUM}"
        ),
        "decoder_family": args.decoder,
        "decoder_schedule": "layered",
        "decoder_scaling_factor": 1.0 if args.decoder == "ms" else NORMALIZED_MIN_SUM,
        "decoder_termination": "early: full mother-codeword syndrome H*c=0 after each complete layered iteration",
        "max_iterations": MAX_ITER,
        "mean_iterations_definition": "total actual iterations divided by all frames, including payload/CRC failures",
        "crc_used_for_termination": False,
        "fixed_scale": args.scale,
        "noise_floors": args.noise_floors,
        "frames_per_point": args.frames,
        "seed": args.seed,
        "workers": args.workers,
        "channel_law": "p_aged=min(scale*p_enrollment+noise_floor, 0.5)",
        "llr_source": "enrollment profile only; no post-aging labels",
        "fer_definition": "decoded 2048-bit payload differs from transmitted payload",
        "comparison_boundary": "same clustered aging channel; decoder/reconstruction block only; no hash/KDF",
        "self_test": self_test_info,
    }
    (output / "provenance.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=ROOT / "puf_profile_long.h")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--frames", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--scale", type=float, default=DEFAULT_SCALE)
    parser.add_argument("--noise-floors", type=str, default=None)
    parser.add_argument("--workers", type=int, default=min(8, mp.cpu_count()))
    parser.add_argument(
        "--decoder", choices=("ms", "nms"), default=DEFAULT_DECODER,
        help="layered min-sum (ms) or normalized min-sum (nms)",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="resume completed points from a matching progress checkpoint",
    )
    parser.add_argument("--smoke", action="store_true", help="run 3 points with 2 frames")
    args = parser.parse_args()
    if args.output is None:
        args.output = ROOT / f"results_5g_nr_ldpc_{args.decoder}_early_stop"

    if args.smoke:
        args.frames = 2
        args.workers = min(args.workers, 2)
        args.noise_floors = [0.001, 0.017, 0.055]
    else:
        args.noise_floors = parse_floors(args.noise_floors)

    if args.frames < 1 or args.workers < 1:
        raise ValueError("frames and workers must be positive")
    if any((args.output / name).exists() for name in ("fer_summary.csv", "provenance.json")):
        raise FileExistsError(f"Existing results in {args.output}; choose a new --output directory")
    profile = load_profile(args.profile)
    self_test_info = self_test(profile, args.decoder)
    print(
        f"Self-test passed: 5G NR BG2, payload={PAYLOAD_BITS}, E={E_BITS}, "
        f"R={NOMINAL_RATE:.3f}, Zc={self_test_info['native_info']['Zc']}, "
        f"decoder={args.decoder}, iterations={self_test_info['self_test_iterations']} "
        f"(syndrome early stop, max={MAX_ITER})"
    )
    print(
        f"Running {len(args.noise_floors)} points x {args.frames} frames "
        f"with {args.workers} workers; output={args.output}", flush=True
    )

    started = time.perf_counter()
    args.output.mkdir(parents=True, exist_ok=True)
    progress_csv = args.output / "progress.csv"
    progress_config = args.output / "progress_config.json"
    config = {
        "frames": args.frames,
        "seed": args.seed,
        "scale": args.scale,
        "noise_floors": args.noise_floors,
        "decoder": args.decoder,
        "profile": str(args.profile.resolve()),
        "profile_sha256": hashlib.sha256(args.profile.read_bytes()).hexdigest(),
        "runner_sha256": hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest(),
        "decoder_source_sha256": hashlib.sha256(
            (VENDOR / "py3gpp" / "nrLDPCDecode.py").read_bytes()
        ).hexdigest(),
        "encoder_source_sha256": hashlib.sha256(
            (VENDOR / "py3gpp" / "nrLDPCEncode.py").read_bytes()
        ).hexdigest(),
    }
    if progress_csv.exists() or progress_config.exists():
        if not args.resume:
            raise FileExistsError(
                f"Progress checkpoint exists in {args.output}; use --resume or a new output directory"
            )
        if not (progress_csv.exists() and progress_config.exists()):
            raise RuntimeError("incomplete checkpoint: progress.csv and progress_config.json must both exist")
        saved_config = json.loads(progress_config.read_text(encoding="utf-8"))
        if saved_config != config:
            raise ValueError("checkpoint configuration differs from this run; use the original parameters")
        with progress_csv.open(newline="", encoding="utf-8") as handle:
            checkpoint_rows = list(csv.DictReader(handle))
        rows = []
        seen = set()
        for saved in checkpoint_rows:
            idx = int(saved["point_index"])
            if idx in seen or idx < 0 or idx >= len(args.noise_floors):
                raise ValueError(f"invalid or duplicate checkpoint point index: {idx}")
            seen.add(idx)
            row = {
                "point_index": idx,
                "noise_floor": float(saved["noise_floor"]),
                "scale": float(saved["scale"]),
                "expected_raw_ber": float(saved["expected_raw_ber"]),
                "actual_raw_ber": float(saved["actual_raw_ber"]),
                "frames": int(saved["frames"]),
                "message_failures": int(saved["message_failures"]),
                "message_fer": float(saved["message_fer"]),
                "crc_failures": int(saved["crc_failures"]),
                "mean_iterations": float(saved["mean_iterations"]),
            }
            if row["frames"] != args.frames or not np.isclose(
                row["noise_floor"], args.noise_floors[idx]
            ):
                raise ValueError(f"checkpoint row does not match requested point {idx}")
            rows.append(row)
        print(f"Resuming from {len(rows)} completed points", flush=True)
    else:
        if args.resume:
            raise FileNotFoundError("--resume requested but no checkpoint exists")
        rows = []
        progress_config.write_text(
            json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        with progress_csv.open("w", newline="", encoding="utf-8") as handle:
            csv.DictWriter(
                handle,
                fieldnames=[
                    "point_index", "noise_floor", "scale", "expected_raw_ber",
                    "actual_raw_ber", "frames", "message_failures",
                    "message_fer", "crc_failures", "mean_iterations",
                ],
            ).writeheader()
            handle.flush()
            os.fsync(handle.fileno())

    completed = {row["point_index"] for row in rows}
    remaining = [
        (index, floor) for index, floor in enumerate(args.noise_floors)
        if index not in completed
    ]
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(
                run_point,
                index,
                floor,
                args.frames,
                args.seed,
                args.scale,
                str(args.profile),
                args.decoder,
            )
            for index, floor in remaining
        ]
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            with progress_csv.open("a", newline="", encoding="utf-8") as handle:
                csv.DictWriter(
                    handle,
                    fieldnames=[
                        "point_index", "noise_floor", "scale", "expected_raw_ber",
                        "actual_raw_ber", "frames", "message_failures",
                        "message_fer", "crc_failures", "mean_iterations",
                    ],
                ).writerow(row)
                handle.flush()
                os.fsync(handle.fileno())
            print(
                f"point={row['point_index'] + 1}/{len(args.noise_floors)} "
                f"actual={row['actual_raw_ber']:.6f} "
                f"FER={row['message_fer']:.6g} "
                f"failures={row['message_failures']}/{row['frames']} "
                f"mean_iterations={row['mean_iterations']:.3f}", flush=True
            )

    write_outputs(args.output, args, profile, self_test_info, rows)
    elapsed = time.perf_counter() - started
    print(f"Completed in {elapsed:.1f}s", flush=True)
    print(f"Results: {args.output / 'fer_summary.csv'}", flush=True)
    return 0


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
