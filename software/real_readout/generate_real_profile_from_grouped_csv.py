import argparse
import csv
from pathlib import Path

import numpy as np


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate a 4096-bit real-data PUF profile from one grouped CSV page."
    )
    parser.add_argument("csv_file", help="Grouped CSV file for one UID")
    parser.add_argument("--address", required=True, help="Target SRAM page address, e.g. 0x20013A00")
    parser.add_argument(
        "--output",
        default="puf_profile_long.h",
        help="Output header path",
    )
    parser.add_argument(
        "--map-top-to-front",
        type=int,
        default=0,
        help="Move the top-N highest-BER bits to indices [0..N-1] to emulate enrollment-time mapping",
    )
    return parser.parse_args()


def load_samples(csv_path: Path, target_address: str):
    samples = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            address = (row.get("address") or "").strip()
            if not address or address.startswith("地址:"):
                continue
            if address != target_address:
                continue

            data_str = (row.get("data") or "").strip().strip('"')
            if not data_str:
                continue

            byte_values = [int(x) for x in data_str.split(",") if x]
            if len(byte_values) != 512:
                raise ValueError(f"address {target_address} has {len(byte_values)} bytes, expected 512")

            bits = []
            for byte in byte_values:
                for bit_pos in range(8):
                    bits.append((byte >> bit_pos) & 1)
            samples.append(bits)

    if len(samples) < 2:
        raise ValueError(f"not enough samples at {target_address}: {len(samples)}")

    matrix = np.asarray(samples, dtype=np.uint8)
    if matrix.shape[1] != 4096:
        raise ValueError(f"page length is {matrix.shape[1]} bits, expected 4096")
    return matrix


def build_profile(matrix: np.ndarray):
    bit_means = matrix.mean(axis=0)
    golden_ref = np.rint(bit_means).astype(np.uint8)
    error_profile = np.abs(bit_means - golden_ref)
    reliability_rank = np.argsort(-error_profile, kind="stable")
    page_ber = float(error_profile.mean())
    return error_profile, reliability_rank, golden_ref, page_ber


def remap_top_bits(error_profile: np.ndarray, golden_ref: np.ndarray, top_count: int):
    if top_count <= 0:
        identity = np.arange(error_profile.size, dtype=np.int32)
        reliability_rank = np.argsort(-error_profile, kind="stable")
        return error_profile, golden_ref, reliability_rank, identity

    top_count = min(top_count, error_profile.size)
    reliability_rank = np.argsort(-error_profile, kind="stable")
    top_indices = reliability_rank[:top_count]

    selected = np.zeros(error_profile.size, dtype=bool)
    selected[top_indices] = True
    remainder = np.flatnonzero(~selected)
    permutation = np.concatenate([top_indices, remainder])

    mapped_error_profile = error_profile[permutation]
    mapped_golden_ref = golden_ref[permutation]
    mapped_rank = np.argsort(-mapped_error_profile, kind="stable")
    return mapped_error_profile, mapped_golden_ref, mapped_rank, permutation


def write_header(output_path: Path, source_csv: Path, target_address: str,
                 error_profile: np.ndarray, reliability_rank: np.ndarray,
                 golden_ref: np.ndarray, page_ber: float, sample_count: int,
                 permutation: np.ndarray, mapped_count: int):
    lines = []
    lines.append("// Real-data PUF profile generated from grouped SRAM measurements.")
    lines.append(f"// Source file: {source_csv.name}")
    lines.append(f"// Address: {target_address}")
    lines.append(f"// Samples: {sample_count}")
    lines.append(f"// Mean page BER: {page_ber:.8f}")
    lines.append(f"// Enrollment-time mapped top bits: {mapped_count}")
    lines.append("// Golden response is majority-vote per bit; all-zero codeword tests still")
    lines.append("// use only these per-bit crossover probabilities, not the raw response bits.")
    lines.append("#ifndef PUF_PROFILE_LONG_H")
    lines.append("#define PUF_PROFILE_LONG_H")
    lines.append("#define PUF_N_LONG 4096")
    lines.append("")
    lines.append("static const double REAL_PUF_ERROR_RATES[4096] = {")
    for start in range(0, 4096, 8):
        chunk = ", ".join(f"{v:.6f}" for v in error_profile[start:start + 8])
        suffix = "," if start + 8 < 4096 else ""
        lines.append(f"    {chunk}{suffix}")
    lines.append("};")
    lines.append("")
    lines.append("static const int PUF_RELIABILITY_RANK[4096] = {")
    for start in range(0, 4096, 16):
        chunk = ", ".join(str(int(v)) for v in reliability_rank[start:start + 16])
        suffix = "," if start + 16 < 4096 else ""
        lines.append(f"    {chunk}{suffix}")
    lines.append("};")
    lines.append("")
    lines.append("static const unsigned char PUF_GOLDEN_RESPONSE[4096] = {")
    for start in range(0, 4096, 32):
        chunk = ", ".join(str(int(v)) for v in golden_ref[start:start + 32])
        suffix = "," if start + 32 < 4096 else ""
        lines.append(f"    {chunk}{suffix}")
    lines.append("};")
    lines.append("")
    lines.append("static const int PUF_SOURCE_INDEX[4096] = {")
    for start in range(0, 4096, 16):
        chunk = ", ".join(str(int(v)) for v in permutation[start:start + 16])
        suffix = "," if start + 16 < 4096 else ""
        lines.append(f"    {chunk}{suffix}")
    lines.append("};")
    lines.append("")
    lines.append("#endif // PUF_PROFILE_LONG_H")
    output_path.write_text("\n".join(lines) + "\n", encoding="ascii")


def main():
    args = parse_args()
    csv_path = Path(args.csv_file)
    output_path = Path(args.output)

    matrix = load_samples(csv_path, args.address)
    error_profile, reliability_rank, golden_ref, page_ber = build_profile(matrix)
    mapped_profile, mapped_golden_ref, mapped_rank, permutation = remap_top_bits(
        error_profile, golden_ref, args.map_top_to_front
    )
    write_header(
        output_path=output_path,
        source_csv=csv_path,
        target_address=args.address,
        error_profile=mapped_profile,
        reliability_rank=mapped_rank,
        golden_ref=mapped_golden_ref,
        page_ber=page_ber,
        sample_count=matrix.shape[0],
        permutation=permutation,
        mapped_count=args.map_top_to_front,
    )

    print(f"Generated {output_path}")
    print(f"Samples: {matrix.shape[0]}")
    print(f"Mean BER: {page_ber:.8f}")
    print(f"Max bit BER: {float(error_profile.max()):.8f}")
    print("Top-8 original hotspot indices:", ", ".join(str(int(v)) for v in reliability_rank[:8]))
    if args.map_top_to_front > 0:
        print(f"Mapped top {args.map_top_to_front} hotspot bits to front strong block.")


if __name__ == "__main__":
    main()
