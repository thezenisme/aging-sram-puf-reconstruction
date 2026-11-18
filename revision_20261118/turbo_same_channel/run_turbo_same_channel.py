"""LTE-structure Turbo ECC baseline on the existing SRAM-PUF stress channel.

The native floating-point Max-Log-MAP decoder is pinned srsLTE source.
This is a code-block/ECC experiment, not a complete LTE transport stack.
"""
from __future__ import annotations

import argparse
import csv
import ctypes as ct
import hashlib
import json
import multiprocessing as mp
import platform
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
PAYLOAD_BITS = 2048
E_BITS = 4096
MOTHER_BITS = 3 * PAYLOAD_BITS + 12
DEFAULT_SEED = 20260916
DEFAULT_PROFILE = ROOT.parent / "nr_ldpc_same_channel" / "puf_profile_long.h"
UPSTREAM_COMMIT = "8f9ce13b1cb1892ba971dba66f49f6e4e579ecaa"
PROTECTED = [
    ROOT.parent / "paper_artifact_minimal/software/core" / name
    for name in ("test_staircase_quantization.c", "ldpc.h", "ldpc.c",
                 "puf_profile_long.h", "matrix_data_1_2_long.c")
] + [ROOT.parent / "nr_ldpc_same_channel/run_nr_ldpc_same_channel.py",
     ROOT.parent / "nr_ldpc_same_channel/puf_profile_long.h"]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_profile(path: Path) -> np.ndarray:
    source = path.read_text(encoding="utf-8")
    match = re.search(r"REAL_PUF_ERROR_RATES\s*\[\s*4096\s*\]\s*=\s*\{(.*?)\}",
                      source, re.DOTALL)
    if match is None:
        raise ValueError(f"profile initializer absent: {path}")
    # Parse only the array, not macros/comments elsewhere in the header.
    body = re.sub(r"/\*.*?\*/|//[^\n]*", "", match.group(1), flags=re.DOTALL)
    values = np.array([float(x.strip().rstrip("fF")) for x in body.split(",") if x.strip()])
    if values.shape != (E_BITS,) or np.any((values <= 0) | (values >= .5)):
        raise ValueError("invalid 4096-bit enrollment profile")
    return values


def aged_probabilities(profile: np.ndarray, scale: float, noise_floor: float) -> np.ndarray:
    return np.minimum(scale * profile + noise_floor, .5)


def rate_match_indices() -> np.ndarray:
    """LTE TS 36.212 turbo subblock interleaving/circular selection, RV=0.

    Values are indices in the upstream interlaced [sys,p1,p2] mother array,
    with its 12 constituent-tail bits at the end. No HARQ combining.
    """
    perm = np.array([0,16,8,24,4,20,12,28,2,18,10,26,6,22,14,30,
                     1,17,9,25,5,21,13,29,3,19,11,27,7,23,15,31])
    d = MOTHER_BITS // 3
    rows = (d + 31) // 32
    kp = rows * 32
    dummy = kp - d
    circular = np.full(3 * kp, -1, dtype=np.int32)
    k = 0
    for col in perm:
        for row in range(rows):
            position = row * 32 + int(col) - dummy
            if position >= 0:
                circular[k] = 3 * position
                circular[kp + 2 * k] = 3 * position + 1
            k += 1
    for k in range(kp):
        position = (int(perm[k // rows]) + 32 * (k % rows) + 1) % kp - dummy
        if position >= 0:
            circular[kp + 2 * k + 1] = 3 * position + 2
    k0 = 2 * rows  # RV0, full circular buffer
    selected = []
    j = 0
    while len(selected) < E_BITS:
        index = circular[(k0 + j) % circular.size]
        if index >= 0:
            selected.append(index)
        j += 1
    result = np.asarray(selected, dtype=np.int32)
    assert len(np.unique(result)) == E_BITS
    assert np.all((result >= 0) & (result < MOTHER_BITS))
    data = result[result < 3 * PAYLOAD_BITS]
    assert np.bincount(data % 3, minlength=3).tolist() == [1920, 1084, 1084]
    assert sorted((result[result >= 3 * PAYLOAD_BITS] - 3 * PAYLOAD_BITS).tolist()) == [0,1,3,5,6,7,9,11]
    return result


class Codec:
    def __init__(self):
        self.lib = ct.CDLL(str(ROOT / "turbo_native.dll"))
        self.lib.turbo_create.restype = ct.c_void_p
        self.lib.turbo_free.argtypes = [ct.c_void_p]
        self.lib.turbo_free.restype = None
        u8p = ct.POINTER(ct.c_uint8)
        fp = ct.POINTER(ct.c_float)
        self.lib.turbo_encode.argtypes = [ct.c_void_p, u8p, u8p]
        self.lib.turbo_encode.restype = ct.c_int
        self.lib.turbo_decode.argtypes = [ct.c_void_p, fp, u8p, ct.c_int]
        self.lib.turbo_decode.restype = ct.c_int
        self.handle = self.lib.turbo_create()
        if not self.handle:
            raise RuntimeError("native turbo_create failed")

    def close(self):
        if self.handle:
            self.lib.turbo_free(self.handle)
            self.handle = None

    def encode(self, payload: np.ndarray) -> np.ndarray:
        payload = np.ascontiguousarray(payload, dtype=np.uint8)
        if payload.shape != (PAYLOAD_BITS,) or np.any(payload > 1):
            raise ValueError("payload must contain exactly 2048 binary bits")
        out = np.empty(MOTHER_BITS, dtype=np.uint8)
        rc = self.lib.turbo_encode(self.handle, payload.ctypes.data_as(ct.POINTER(ct.c_uint8)),
                                   out.ctypes.data_as(ct.POINTER(ct.c_uint8)))
        if rc != 0:
            raise RuntimeError(f"native encode returned {rc}")
        return out

    def decode(self, mother_llr: np.ndarray, iterations: int = 8) -> np.ndarray:
        llr = np.ascontiguousarray(mother_llr, dtype=np.float32)
        if llr.shape != (MOTHER_BITS,) or not np.all(np.isfinite(llr)):
            raise ValueError("expected 6156 finite LLRs")
        if iterations < 1:
            raise ValueError("iterations must be positive")
        out = np.empty(PAYLOAD_BITS, dtype=np.uint8)
        rc = self.lib.turbo_decode(self.handle, llr.ctypes.data_as(ct.POINTER(ct.c_float)),
                                   out.ctypes.data_as(ct.POINTER(ct.c_uint8)), iterations)
        if rc != 0:
            raise RuntimeError(f"native decode returned {rc}")
        return out


def self_test(profile: np.ndarray, iterations: int) -> dict:
    indices = rate_match_indices()
    codec = Codec()
    rng = np.random.default_rng(7)
    magnitude = np.log((1 - profile) / profile)
    try:
        for _ in range(10):
            payload = rng.integers(0, 2, PAYLOAD_BITS, dtype=np.uint8)
            mother = codec.encode(payload)
            assert np.array_equal(mother[:3 * PAYLOAD_BITS:3], payload)
            llr = np.zeros(MOTHER_BITS, dtype=np.float32)
            llr[indices] = np.where(mother[indices] == 0, magnitude, -magnitude)
            if not np.array_equal(codec.decode(llr, iterations), payload):
                raise RuntimeError("noiseless punctured Turbo round-trip failed")
    finally:
        codec.close()
    return {"noiseless_random_frames": 10, "passed": True,
            "mapping_sha256": hashlib.sha256(indices.tobytes()).hexdigest()}


def run_point(index: int, floor: float, frames: int, seed: int, scale: float,
              profile_path: str, iterations: int) -> dict:
    profile = load_profile(Path(profile_path))
    p_aged = aged_probabilities(profile, scale, floor)
    magnitude = np.log((1 - profile) / profile)
    indices = rate_match_indices()
    rng = np.random.default_rng(seed + index * 1000003)
    codec = Codec()
    failures = raw_errors = message_errors = 0
    start = time.perf_counter()
    try:
        for _ in range(frames):
            # Same random generation order and seed schedule as the NR runner.
            payload = rng.integers(0, 2, PAYLOAD_BITS, dtype=np.uint8)
            mother = codec.encode(payload)
            flips = rng.random(E_BITS) < p_aged
            received = mother[indices] ^ flips.astype(np.uint8)
            mother_llr = np.zeros(MOTHER_BITS, dtype=np.float32)
            mother_llr[indices] = np.where(received == 0, magnitude, -magnitude)
            decoded = codec.decode(mother_llr, iterations)
            errors = int(np.count_nonzero(decoded != payload))
            failures += int(errors > 0)
            message_errors += errors
            raw_errors += int(np.count_nonzero(flips))
    finally:
        codec.close()
    return {
        "point_index": index, "noise_floor": floor, "scale": scale,
        "expected_raw_ber": float(np.mean(p_aged)),
        "actual_raw_ber": raw_errors / (frames * E_BITS),
        "frames": frames, "raw_errors": raw_errors,
        "message_failures": failures, "message_fer": failures / frames,
        "message_bit_errors": message_errors,
        "decoded_message_ber": message_errors / (frames * PAYLOAD_BITS),
        "mean_iterations": iterations,
        "zero_failure_upper95_one_sided": 1 - .05 ** (1 / frames) if failures == 0 else None,
        "elapsed_seconds": time.perf_counter() - start,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, default=1000)
    parser.add_argument("--iterations", type=int, default=8)
    parser.add_argument("--workers", type=int, default=min(8, mp.cpu_count()))
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--scale", type=float, default=2.0)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--noise-floors", default=None)
    parser.add_argument("--output", type=Path, default=ROOT / "results_turbo_lte_qpp_1000")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    floors = [float(x) for x in args.noise_floors.split(",")] if args.noise_floors else [i / 1000 for i in range(1,56)]
    if args.smoke:
        floors = [.001, .017, .055]
        args.frames = 5
    if args.frames < 1 or args.iterations < 1 or args.workers < 1 or args.scale < 0:
        raise ValueError("invalid run parameters")
    if not floors or any(not np.isfinite(x) or x < 0 for x in floors):
        raise ValueError("invalid noise-floor points")
    if args.output.exists() and any(args.output.iterdir()):
        raise FileExistsError(f"output already contains files: {args.output}")
    profile = load_profile(args.profile)
    protected_before = {str(p): digest(p) for p in PROTECTED if p.exists()}
    checks = self_test(profile, args.iterations)
    args.output.mkdir(parents=True, exist_ok=True)
    # Exact input snapshot, never change the canonical baseline profile.
    snapshot = args.output / "profile_snapshot.h"
    snapshot.write_bytes(args.profile.read_bytes())
    source_files = [p for p in ROOT.rglob("*") if p.is_file() and
                    (p.suffix in {".c", ".h", ".py", ".ps1", ".dll"}) and
                    "__pycache__" not in p.parts and not any(x.startswith("results") for x in p.relative_to(ROOT).parts)]
    metadata = {
        "status": "running", "algorithm": "LTE-structure Turbo, 8-state parallel concatenated RSC",
        "implementation": "srsLTE release_17_12 original float Max-Log-MAP plus standalone integration",
        "upstream_commit": UPSTREAM_COMMIT,
        "upstream_url": f"https://github.com/srsran/srsRAN_4G/tree/{UPSTREAM_COMMIT}",
        "license": "AGPL-3.0-or-later", "payload_bits": PAYLOAD_BITS,
        "mother_bits": MOTHER_BITS, "physical_bits": E_BITS,
        "effective_payload_rate": PAYLOAD_BITS / E_BITS,
        "qpp": {"f1":31, "f2":64, "K":2048},
        "rate_matching": "LTE subblock interleaver and full circular-buffer selection, RV0, no retransmissions",
        "crc": "none: code-block-level experiment, not LTE transport-block chain",
        "decoder": "floating-point Max-Log-MAP",
        "iterations": args.iterations, "iteration_definition": "one complete pair of constituent MAP decodes",
        "termination": "fixed iteration budget; no truth-based or CRC early stopping",
        "profile_source": str(args.profile.resolve()), "profile_sha256": digest(args.profile),
        "profile_values_counts": {str(x): int(np.count_nonzero(profile == x)) for x in np.unique(profile)},
        "scale": args.scale, "noise_floors": floors, "frames_per_point": args.frames,
        "seed": args.seed, "point_seed": "seed + point_index*1000003",
        "channel_law": "independent Bernoulli errors, p_aged=min(scale*p_enrollment+noise_floor,0.5)",
        "llr_source": "enrollment profile only; sign from received bit; no aging-probability oracle",
        "llr_convention_at_python_boundary": "log(P(bit=0)/P(bit=1)); native wrapper negates for srsLTE",
        "fer_definition": "any error in the reconstructed 2048-bit payload",
        "boundary": "ECC reconstruction only; no hash/KDF",
        "workers": args.workers, "python":sys.version, "numpy":np.__version__,
        "platform":platform.platform(), "self_test":checks,
        "source_sha256": {str(p.relative_to(ROOT)):digest(p) for p in sorted(source_files)},
        "protected_before": protected_before,
    }
    prov = args.output / "provenance.json"
    prov.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Self-test passed. Turbo K=2048 E=4096 R=1/2, {args.iterations} full iterations", flush=True)
    print(f"Running {len(floors)} x {args.frames} frames, workers={args.workers}, output={args.output}", flush=True)
    rows = []
    started = time.perf_counter()
    try:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(run_point, i, f, args.frames, args.seed, args.scale,
                                   str(snapshot.resolve()), args.iterations) for i,f in enumerate(floors)]
            for future in as_completed(futures):
                row = future.result()
                rows.append(row)
                # Durable checkpoint per point; raw integer counts remain primary evidence.
                (args.output / f"point_{row['point_index']:03d}.json").write_text(json.dumps(row, indent=2), encoding="utf-8")
                with (args.output / "fer_summary.csv").open("w", newline="", encoding="utf-8") as out:
                    writer = csv.DictWriter(out, fieldnames=list(row))
                    writer.writeheader()
                    writer.writerows(sorted(rows, key=lambda r:r["point_index"]))
                print(f"point={row['point_index']+1}/{len(floors)} actual={row['actual_raw_ber']:.6f} "
                      f"FER={row['message_fer']:.6g} failures={row['message_failures']}/{args.frames} "
                      f"elapsed_point={row['elapsed_seconds']:.1f}s", flush=True)
        protected_after = {str(p):digest(p) for p in PROTECTED if p.exists()}
        if protected_after != protected_before:
            raise RuntimeError("Protected source files changed during run; inspect provenance")
        metadata.update(status="complete", elapsed_seconds=time.perf_counter()-started,
                        completed_points=len(rows), total_frames=sum(r["frames"] for r in rows),
                        protected_after=protected_after, protected_files_unchanged=True)
    except BaseException as exc:
        metadata.update(status="failed", error=repr(exc), completed_points=len(rows))
        raise
    finally:
        prov.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Completed in {metadata['elapsed_seconds']:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
