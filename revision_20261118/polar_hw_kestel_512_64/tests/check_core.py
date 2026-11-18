"""Check RTL against an independent, integer min-sum SC reference."""

from __future__ import annotations

import math
import random
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
N = 512
K = 64
LOG_N = 9
FROZEN_HEX = (
    "1777577f577f7fff177f7f7f7f7f7fff177f7f7f777f7fff777f7fff7fffffff"
    "177f7f7f777f7fff777f7fff7fffffff777f7fff7fffffff7fffffff7fffffff"
)


def polar_frozen_set() -> set[int]:
    z = 2 * math.sqrt(0.15 * 0.85)
    log_z = [math.log(z)] * N
    for stage in range(LOG_N):
        half = 1 << stage
        result = [0.0] * N
        for start in range(0, N, 2 * half):
            for offset in range(half):
                a = log_z[start + offset]
                b = log_z[start + half + offset]
                product = a + b
                high, low = max(a, b), min(a, b)
                union = high + math.log1p(math.exp(low - high))
                result[start + offset] = union + math.log1p(-math.exp(product - union))
                result[start + half + offset] = product
        log_z = result
    order = sorted(range(N), key=lambda i: (log_z[i], i))
    return set(order[K:])


def encode(u: list[int]) -> list[int]:
    encoded = u.copy()
    block = N
    while block > 1:
        half = block // 2
        for start in range(0, N, block):
            for offset in range(half):
                encoded[start + offset] ^= encoded[start + half + offset]
        block //= 2
    return encoded


def clamp(value: int) -> int:
    return max(-128, min(127, value))


def decode(llr: list[int], frozen: set[int]) -> list[int]:
    def visit(values: list[int], first: int) -> tuple[list[int], list[int]]:
        if len(values) == 1:
            bit = 0 if first in frozen or values[0] >= 0 else 1
            return [bit], [bit]
        half = len(values) // 2
        left_llr = []
        for a, b in zip(values[:half], values[half:]):
            magnitude = min(abs(a), abs(b), 127)
            left_llr.append(-magnitude if (a < 0) != (b < 0) else magnitude)
        left_u, left_beta = visit(left_llr, first)
        right_llr = [
            clamp(b + (-a if beta else a))
            for a, b, beta in zip(values[:half], values[half:], left_beta)
        ]
        right_u, right_beta = visit(right_llr, first + half)
        parent_beta = [a ^ b for a, b in zip(left_beta, right_beta)] + right_beta
        return left_u + right_u, parent_beta

    return visit(llr, 0)[0]


def main() -> None:
    frozen = polar_frozen_set()
    expected_mask = sum(1 << index for index in frozen)
    assert len(frozen) == N - K
    assert f"{expected_mask:0128x}" == FROZEN_HEX, "RTL frozen set differs"

    rng = random.Random(20261014)
    all_stimuli: list[int] = []
    all_expected: list[int] = []
    error_counts = [0, 0, 1, 3, 8, 15, 20, 32]
    for frame, error_count in enumerate(error_counts):
        message = [0] * K if frame == 0 else [1] * K if frame == 1 else [rng.randrange(2) for _ in range(K)]
        u = [0] * N
        for index, bit in zip((i for i in range(N) if i not in frozen), message):
            u[index] = bit
        codeword = encode(u)
        llr = [(-1 if bit else 1) * rng.choice((35, 60, 80)) for bit in codeword]
        for index in rng.sample(range(N), error_count):
            llr[index] = -llr[index]
        result = decode(llr, frozen)
        decoded = [result[i] for i in range(N) if i not in frozen]
        if error_count == 0:
            assert decoded == message, "Noiseless reference decode failed"
        all_expected.append(sum(bit << i for i, bit in enumerate(decoded)))
        all_stimuli.extend(value & 0xFF for value in llr)

    iverilog = shutil.which("iverilog")
    vvp = shutil.which("vvp")
    if not iverilog or not vvp:
        raise SystemExit("iverilog and vvp must be on PATH")

    with tempfile.TemporaryDirectory(prefix="polar_sc_rtl_") as tmp:
        tmp_path = Path(tmp)
        stimulus_path = tmp_path / "stimuli.hex"
        expected_path = tmp_path / "expected.hex"
        simulator = tmp_path / "sim.vvp"
        stimulus_path.write_text("".join(f"{value:02x}\n" for value in all_stimuli), encoding="ascii")
        expected_path.write_text("".join(f"{value:016x}\n" for value in all_expected), encoding="ascii")
        subprocess.run(
            [iverilog, "-g2012", "-s", "tb_polar_sc_core", "-o", str(simulator),
             str(ROOT / "rtl" / "polar_sc_core.sv"), str(ROOT / "tb" / "tb_polar_sc_core.sv")],
            check=True,
        )
        subprocess.run(
            [vvp, str(simulator), f"+stimuli={stimulus_path}", f"+expected={expected_path}"],
            check=True,
        )

        wrapper_stimuli: list[int] = []
        wrapper_expected: list[int] = []
        for block in range(32):
            message = [rng.randrange(2) for _ in range(K)]
            u = [0] * N
            for index, bit in zip((i for i in range(N) if i not in frozen), message):
                u[index] = bit
            codeword = encode(u)
            llr = [(-1 if bit else 1) * 60 for bit in codeword]
            for index in rng.sample(range(N), block % 9):
                llr[index] = -llr[index]
            result = decode(llr, frozen)
            decoded = [result[i] for i in range(N) if i not in frozen]
            wrapper_expected.append(sum(bit << i for i, bit in enumerate(decoded)))
            wrapper_stimuli.extend(value & 0xFF for value in llr)

        stimulus_path.write_text("".join(f"{value:02x}\n" for value in wrapper_stimuli), encoding="ascii")
        expected_path.write_text("".join(f"{value:016x}\n" for value in wrapper_expected), encoding="ascii")
        subprocess.run(
            [iverilog, "-g2012", "-s", "tb_polar_sc_2048", "-o", str(simulator),
             str(ROOT / "rtl" / "polar_sc_core.sv"),
             str(ROOT / "rtl" / "polar_sc_2048.sv"),
             str(ROOT / "tb" / "tb_polar_sc_2048.sv")],
            check=True,
        )
        subprocess.run(
            [vvp, str(simulator), f"+stimuli={stimulus_path}", f"+expected={expected_path}"],
            check=True,
        )


if __name__ == "__main__":
    # Keep the copied scalar model available to the independent verification
    # harness; direct invocation now tests the optimized RTL as well.
    from verify_architecture import main as verify_main
    verify_main()
