import argparse
import csv
import math
from pathlib import Path

import numpy as np


TARGET_WCHD_AVG = 0.0249
FACTOR_24M = 1.193
FACTOR_12M = math.sqrt(FACTOR_24M)
TOP_MAP_BITS = 128
SELECT_CASES = 32
MIN_BER = 0.010
MAX_BER = 0.080
MIN_HW = 0.45
MAX_HW = 0.55
AGING_WEIGHT_GAMMA = 1.75


def parse_args():
    parser = argparse.ArgumentParser(description="Generate 32 Wang-calibrated real SRAM aging cases.")
    parser.add_argument(
        "--split-dir",
        required=True,
        help="Directory containing grouped_by_address CSV files and ber_summary_table.csv",
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parent / "cases"),
        help="Output directory for generated case folders",
    )
    return parser.parse_args()


def load_page_matrix(csv_path: Path, target_address: str) -> np.ndarray:
    samples = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            address = (row.get("address") or "").strip()
            if address != target_address:
                continue
            data_str = (row.get("data") or "").strip().strip('"')
            if not data_str:
                continue
            byte_values = [int(x) for x in data_str.split(",") if x]
            if len(byte_values) != 512:
                raise ValueError(f"{csv_path.name} {target_address} has {len(byte_values)} bytes")
            bits = []
            for byte in byte_values:
                for bit_pos in range(8):
                    bits.append((byte >> bit_pos) & 1)
            samples.append(bits)
    matrix = np.asarray(samples, dtype=np.uint8)
    if matrix.shape != (9, 4096):
        raise ValueError(f"{csv_path.name} {target_address} matrix shape {matrix.shape}, expected (9, 4096)")
    return matrix


def build_enrollment_profile(matrix: np.ndarray):
    bit_means = matrix.mean(axis=0)
    golden_ref = np.rint(bit_means).astype(np.uint8)
    enroll_rates = np.abs(bit_means - golden_ref)
    reliability_rank = np.argsort(-enroll_rates, kind="stable")
    page_ber = float(enroll_rates.mean())
    hw = float(golden_ref.mean())
    return enroll_rates, reliability_rank, golden_ref, page_ber, hw


def allocate_aged_profile(enroll_rates: np.ndarray, factor: float) -> np.ndarray:
    target_mean = float(enroll_rates.mean()) * factor
    aged = enroll_rates.astype(np.float64).copy()
    if target_mean <= aged.mean() + 1e-15:
        return aged

    extra_sum = (target_mean - aged.mean()) * aged.size
    weights = np.maximum(aged, 1e-6) ** AGING_WEIGHT_GAMMA
    active = np.ones(aged.size, dtype=bool)

    while extra_sum > 1e-12 and np.any(active):
        active_idx = np.flatnonzero(active)
        caps = 0.5 - aged[active_idx]
        if np.all(caps <= 1e-15):
            break

        w = weights[active_idx]
        w_sum = float(w.sum())
        if w_sum <= 0.0:
            proposed = np.full(active_idx.size, extra_sum / active_idx.size, dtype=np.float64)
        else:
            proposed = extra_sum * (w / w_sum)

        add = np.minimum(proposed, caps)
        aged[active_idx] += add
        used = float(add.sum())
        extra_sum -= used

        saturated = caps - add <= 1e-15
        active[active_idx[saturated]] = False

        if used <= 1e-15:
            break

    return aged


def remap_top_bits(enroll_rates: np.ndarray, golden_ref: np.ndarray, *runtime_profiles: np.ndarray):
    reliability_rank = np.argsort(-enroll_rates, kind="stable")
    top_indices = reliability_rank[:TOP_MAP_BITS]
    selected = np.zeros(enroll_rates.size, dtype=bool)
    selected[top_indices] = True
    remainder = np.flatnonzero(~selected)
    permutation = np.concatenate([top_indices, remainder])

    mapped_enroll = enroll_rates[permutation]
    mapped_golden = golden_ref[permutation]
    mapped_runtime = [profile[permutation] for profile in runtime_profiles]
    mapped_rank = np.argsort(-mapped_enroll, kind="stable")
    return mapped_enroll, mapped_golden, mapped_runtime, mapped_rank, permutation


def write_header(path: Path, csv_name: str, address: str, case_id: str,
                 enroll_rates: np.ndarray, aged12_rates: np.ndarray, aged24_rates: np.ndarray,
                 reliability_rank: np.ndarray, golden_ref: np.ndarray, permutation: np.ndarray):
    lines = [
        "// Auto-generated real SRAM aging profile.",
        f"// Case: {case_id}",
        f"// Source file: {csv_name}",
        f"// Address: {address}",
        f"// Wang calibration: 12m=sqrt(1.193), 24m=1.193",
        "#ifndef PUF_PROFILE_LONG_H",
        "#define PUF_PROFILE_LONG_H",
        "#define PUF_N_LONG 4096",
        "",
    ]

    def emit_array(name: str, array: np.ndarray, c_type: str, data_kind: str, chunk: int):
        lines.append(f"static const {c_type} {name}[4096] = {{")
        for start in range(0, 4096, chunk):
            if data_kind == "double":
                chunk_text = ", ".join(f"{float(v):.6f}" for v in array[start:start + chunk])
            elif data_kind == "int":
                chunk_text = ", ".join(str(int(v)) for v in array[start:start + chunk])
            else:
                chunk_text = ", ".join(str(int(v)) for v in array[start:start + chunk])
            suffix = "," if start + chunk < 4096 else ""
            lines.append(f"    {chunk_text}{suffix}")
        lines.append("};")
        lines.append("")

    emit_array("ENROLL_PUF_ERROR_RATES", enroll_rates, "double", "double", 8)
    emit_array("RUNTIME_PUF_ERROR_RATES_12M", aged12_rates, "double", "double", 8)
    emit_array("RUNTIME_PUF_ERROR_RATES_24M", aged24_rates, "double", "double", 8)
    emit_array("PUF_RELIABILITY_RANK", reliability_rank, "int", "int", 16)
    emit_array("PUF_GOLDEN_RESPONSE", golden_ref, "unsigned char", "int", 32)
    emit_array("PUF_SOURCE_INDEX", permutation, "int", "int", 16)
    lines.append("#endif // PUF_PROFILE_LONG_H")
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def write_case_metadata(path: Path, row: dict):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        writer.writeheader()
        writer.writerow(row)


def main():
    args = parse_args()
    split_dir = Path(args.split_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = split_dir / "ber_summary_table.csv"
    with summary_path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    shortlist = []
    for row in rows:
        ber = float(row["ber"])
        if ber < MIN_BER or ber > MAX_BER:
            continue
        score = abs(ber - TARGET_WCHD_AVG)
        shortlist.append((score, ber, row["file_name"], row["address"]))

    shortlist.sort()

    selected = []
    used_files = set()
    case_index = 1

    for _, _, file_name, address in shortlist:
        if file_name in used_files:
            continue
        csv_path = split_dir / file_name
        matrix = load_page_matrix(csv_path, address)
        enroll_rates, rank, golden_ref, page_ber, hw = build_enrollment_profile(matrix)
        if hw < MIN_HW or hw > MAX_HW:
            continue

        aged12 = allocate_aged_profile(enroll_rates, FACTOR_12M)
        aged24 = allocate_aged_profile(enroll_rates, FACTOR_24M)
        mapped_enroll, mapped_golden, mapped_runtime, mapped_rank, permutation = remap_top_bits(
            enroll_rates, golden_ref, aged12, aged24
        )
        mapped_aged12, mapped_aged24 = mapped_runtime

        case_id = f"case_{case_index:02d}"
        case_dir = output_dir / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        write_header(
            case_dir / "puf_profile_long.h",
            file_name,
            address,
            case_id,
            mapped_enroll,
            mapped_aged12,
            mapped_aged24,
            mapped_rank,
            mapped_golden,
            permutation,
        )

        meta = {
            "case_id": case_id,
            "file_name": file_name,
            "address": address,
            "sample_count": 9,
            "enroll_ber": f"{page_ber:.8f}",
            "golden_hw": f"{hw:.8f}",
            "aged_12m_ber": f"{mapped_aged12.mean():.8f}",
            "aged_24m_ber": f"{mapped_aged24.mean():.8f}",
            "wang_factor_12m": f"{FACTOR_12M:.8f}",
            "wang_factor_24m": f"{FACTOR_24M:.8f}",
            "mapped_hotspots": str(TOP_MAP_BITS),
        }
        write_case_metadata(case_dir / "case_metadata.csv", meta)
        selected.append(meta)
        used_files.add(file_name)
        case_index += 1
        if len(selected) >= SELECT_CASES:
            break

    manifest_path = output_dir / "selected_cases_manifest.csv"
    if selected:
        with manifest_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(selected[0].keys()))
            writer.writeheader()
            writer.writerows(selected)

    print(f"Generated {len(selected)} cases in {output_dir}")
    print(f"Manifest: {manifest_path}")
    for row in selected[:8]:
        print(
            f"{row['case_id']}: {row['file_name']} {row['address']} "
            f"enroll={row['enroll_ber']} 12m={row['aged_12m_ber']} 24m={row['aged_24m_ber']}"
        )


if __name__ == "__main__":
    main()
