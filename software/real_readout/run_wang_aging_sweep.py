import argparse
import csv
import subprocess
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Compile and run the 32x3 Wang-calibrated real SRAM aging sweep.")
    parser.add_argument(
        "--cases-dir",
        default=str(Path(__file__).resolve().parent / "cases"),
        help="Directory produced by generate_wang_aging_cases.py",
    )
    parser.add_argument("--scale", type=float, default=2.0)
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--target-errors", type=int, default=5)
    parser.add_argument("--max-tests", type=int, default=200)
    parser.add_argument("--max-noise", type=float, default=0.050)
    parser.add_argument("--min-noise", type=float, default=0.001)
    parser.add_argument("--limit-cases", type=int, default=0, help="Run only the first N cases for smoke testing")
    parser.add_argument("--tag-suffix", default="", help="Extra suffix appended to each run tag")
    return parser.parse_args()


def run(cmd, cwd: Path):
    print(f"[run] {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(cwd), check=True)


def main():
    args = parse_args()
    root = Path(__file__).resolve().parent
    cases_dir = Path(args.cases_dir)
    shared_dir = root.parent / "core"
    source_c = root / "test_staircase_quantization_aging.c"
    ldpc_c = shared_dir / "ldpc.c"
    matrix_c = shared_dir / "matrix_data_1_2_long.c"
    include_dir = shared_dir

    manifest = cases_dir / "selected_cases_manifest.csv"
    with manifest.open("r", encoding="utf-8", newline="") as f:
        cases = list(csv.DictReader(f))

    if args.limit_cases > 0:
        cases = cases[:args.limit_cases]

    summary_rows = []
    for case in cases:
        case_id = case["case_id"]
        case_dir = cases_dir / case_id
        exe_name = f"{case_id}_aging_long.exe"
        exe_path = case_dir / exe_name

        compile_cmd = [
            "gcc",
            "-O2",
            "-fopenmp",
            "-DTEST_LENGTH_LONG",
            "-include",
            str(case_dir / "puf_profile_long.h"),
            "-I",
            str(case_dir),
            "-I",
            str(include_dir),
            str(source_c),
            str(ldpc_c),
            str(matrix_c),
            "-lm",
            "-o",
            str(exe_path),
        ]
        run(compile_cmd, case_dir)

        for aging_level in (0, 12, 24):
            tag = f"{case_id}_a{aging_level}"
            if args.tag_suffix:
                tag = f"{tag}_{args.tag_suffix}"
            cmd = [
                str(exe_path),
                f"{args.scale}",
                str(args.seed),
                str(args.target_errors),
                str(args.max_tests),
                f"{args.max_noise}",
                f"--min-noise={args.min_noise}",
                f"--aging-level={aging_level}",
                f"--tag={tag}",
            ]
            run(cmd, case_dir)
            out_dir = case_dir / f"test_results_{'no_aging' if aging_level == 0 else ('aging_12m' if aging_level == 12 else 'aging_24m')}_{tag}"
            csv_path = out_dir / "fer_comparison_length_long.csv"
            summary_rows.append(
                {
                    "case_id": case_id,
                    "aging_level": aging_level,
                    "result_csv": str(csv_path),
                    "source_file": case["file_name"],
                    "address": case["address"],
                    "enroll_ber": case["enroll_ber"],
                    "aged_12m_ber": case["aged_12m_ber"],
                    "aged_24m_ber": case["aged_24m_ber"],
                }
            )

    summary_path = cases_dir / "run_manifest.csv"
    with summary_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()) if summary_rows else [])
        if summary_rows:
            writer.writeheader()
            writer.writerows(summary_rows)
    print(f"Saved run manifest: {summary_path}")


if __name__ == "__main__":
    main()
