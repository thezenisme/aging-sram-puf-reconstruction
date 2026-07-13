"""Isolated search for an N=4096 matrix near 9% measured raw BER.

Candidates are generated and compiled inside search_results.  The frozen
software/core matrix files are never modified.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
SEARCH_CODE = ROOT / "matrix_search"
CORE = ROOT / "software" / "core"
RESULTS = ROOT / "search_results"
GENERATOR = SEARCH_CODE / "generate_qcpeg_screen.py"
RESULT_RE = re.compile(
    r"^(?P<noise>0\.\d+),\s*(?P<ber>[0-9.eE+-]+),\s*"
    r"(?P<base_fer>[0-9.eE+-]+),\s*(?P<fer>[0-9.eE+-]+),\s*"
    r"(?P<improvement>[0-9.eE+-]+),\s*(?P<base_iter>[0-9.eE+-]+),\s*"
    r"(?P<iter>[0-9.eE+-]+),\s*(?P<tests>\d+),\s*"
    r"(?P<base_fail>\d+),\s*(?P<fail>\d+),\s*(?P<rule3>[0-9.eE+-]+)"
)


def run_logged(command: list[str], cwd: Path, log_path: Path,
               env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    started = time.time()
    result = subprocess.run(command, cwd=cwd, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log_path.write_text(
        f"command: {' '.join(command)}\n"
        f"cwd: {cwd}\n"
        f"elapsed_seconds: {time.time() - started:.3f}\n"
        f"exit_code: {result.returncode}\n\n{result.stdout}",
        encoding="utf-8",
    )
    return result


def parse_result(output: str) -> dict[str, float | int] | None:
    matches = [RESULT_RE.match(line.strip()) for line in output.splitlines()]
    matches = [match for match in matches if match]
    if not matches:
        return None
    values = matches[-1].groupdict()
    return {
        "noise": float(values["noise"]),
        "actual_ber": float(values["ber"]),
        "baseline_fer": float(values["base_fer"]),
        "proposed_fer": float(values["fer"]),
        "avg_iter": float(values["iter"]),
        "tests": int(values["tests"]),
        "baseline_failures": int(values["base_fail"]),
        "proposed_failures": int(values["fail"]),
        "rule3_95_ub": float(values["rule3"]),
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_budget_limited_profile(candidate: Path) -> None:
    mapped = set(range(0, 43))
    mapped.update(range(1280, 1280 + 42))
    mapped.update(range(2560, 2560 + 43))
    clustered = [index for index in range(4096) if index % 16 < 3 and index not in mapped]
    outside = set(clustered[:640])
    values = [0.15 if index in mapped else 0.14 if index in outside else 0.01
              for index in range(4096)]
    lines = ["// Search profile: 128 mapped hotspots plus 640 clustered hotspots outside A.",
             "#ifndef PUF_PROFILE_LONG_H", "#define PUF_PROFILE_LONG_H",
             "#define PUF_N_LONG 4096",
             "static const double REAL_PUF_ERROR_RATES[4096] = {"]
    for start in range(0, 4096, 8):
        lines.append("    " + ", ".join(f"{value:.4f}" for value in values[start:start + 8]) + ",")
    lines.extend(["};", "#endif", ""])
    (candidate / "puf_profile_long.h").write_text("\n".join(lines), encoding="ascii")
    (candidate / "profile_metadata.json").write_text(json.dumps({
        "N": 4096,
        "mapped_hotspots": 128,
        "outside_budget_clustered_hotspots": 640,
        "mapped_profile_mean": 0.15,
        "outside_profile_mean": 0.14,
        "normal_profile_mean": 0.01,
        "outside_cluster_rule": "logical_index mod 16 < 3, excluding mapped positions",
        "purpose": "matrix-search stress profile; top-A selection is unambiguous",
    }, indent=2), encoding="utf-8")


def evaluate(seed: int, args: argparse.Namespace) -> dict[str, object]:
    candidate = RESULTS / f"seed_{seed}_9pct"
    candidate.mkdir(parents=True, exist_ok=True)
    record: dict[str, object] = {"seed": seed, "status": "started"}

    generated = run_logged(
        [sys.executable, str(GENERATOR), "--seed", str(seed),
         "--outdir", str(candidate)],
        SEARCH_CODE,
        candidate / "01_generate.log",
    )
    if generated.returncode:
        record["status"] = "generation_failed"
        return record

    write_budget_limited_profile(candidate)
    for name in ("ldpc.c", "ldpc.h", "ldpc_wrapper.h", "ldpc_config.h",
                 "test_staircase_quantization.c"):
        shutil.copy2(CORE / name, candidate / name)

    executable = candidate / "test_staircase_long.exe"
    compiled = run_logged(
        ["gcc", "-std=c99", "-O3", "-fopenmp", "-DTEST_LENGTH_LONG",
         "-I", str(candidate),
         str(candidate / "ldpc.c"), str(candidate / "matrix_data_1_2_long.c"),
         str(candidate / "test_staircase_quantization.c"),
         "-o", str(executable), "-lm", "-fopenmp"],
        candidate,
        candidate / "02_compile.log",
    )
    if compiled.returncode:
        record["status"] = "compile_failed"
        return record

    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = str(args.threads)
    simulated = run_logged(
        [str(executable), "2.0", str(args.sim_seed), str(args.target_errors),
         str(args.max_tests), f"--single-noise={args.noise:.3f}"],
        candidate,
        candidate / "03_screen.log",
        env,
    )
    parsed = parse_result(simulated.stdout)
    if simulated.returncode or parsed is None:
        record["status"] = "simulation_failed"
        return record

    record.update(parsed)
    record["status"] = "ok"
    record["matrix_sha256"] = sha256(candidate / "matrix_data_1_2_long.c")
    record["ber_in_target"] = args.ber_min <= parsed["actual_ber"] <= args.ber_max
    (candidate / "result.json").write_text(
        json.dumps(record, indent=2), encoding="utf-8"
    )
    executable.unlink(missing_ok=True)
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-start", type=int, default=5001)
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--noise", type=float, default=0.021)
    parser.add_argument("--ber-min", type=float, default=0.088)
    parser.add_argument("--ber-max", type=float, default=0.092)
    parser.add_argument("--sim-seed", type=int, default=12345)
    parser.add_argument("--target-errors", type=int, default=5)
    parser.add_argument("--max-tests", type=int, default=5000)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--selection-name", default="latest_screening_candidate")
    args = parser.parse_args()

    RESULTS.mkdir(parents=True, exist_ok=True)
    records = []
    for seed in range(args.seed_start, args.seed_start + args.count):
        print(f"[{len(records) + 1}/{args.count}] seed={seed}", flush=True)
        record = evaluate(seed, args)
        records.append(record)
        print(json.dumps(record, ensure_ascii=True), flush=True)

    fields = ["seed", "status", "noise", "actual_ber", "ber_in_target",
              "baseline_fer", "proposed_fer", "avg_iter", "tests",
              "baseline_failures", "proposed_failures", "rule3_95_ub",
              "matrix_sha256"]
    summary = RESULTS / "search_9pct_summary.csv"
    with summary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)

    valid = [r for r in records if r.get("status") == "ok" and r.get("ber_in_target")]
    if not valid:
        print("No candidate produced a measured BER inside the target interval.")
        return 1
    best = min(valid, key=lambda r: (r["proposed_fer"], r["proposed_failures"], r["avg_iter"]))
    source = RESULTS / f"seed_{best['seed']}_9pct"
    destination = RESULTS / args.selection_name
    destination.mkdir(exist_ok=True)
    for name in ("h_matrix_1_2_long.h", "g_matrix_1_2_long.h",
                 "matrix_data_1_2_long.c", "01_generate.log", "02_compile.log",
                 "03_screen.log", "result.json", "base_shifts.csv",
                 "matrix_metadata.json", "puf_profile_long.h",
                 "profile_metadata.json"):
        shutil.copy2(source / name, destination / name)
    (destination / "SELECTION.json").write_text(
        json.dumps({"criterion": "minimum screened FER near 9% measured raw BER",
                    "screening_only": True, "selected": best}, indent=2),
        encoding="utf-8",
    )
    print(f"Selected seed {best['seed']}: FER={best['proposed_fer']}, "
          f"BER={best['actual_ber']}, tests={best['tests']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
