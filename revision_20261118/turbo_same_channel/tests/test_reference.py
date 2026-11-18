"""Independent correctness checks for the fixed K=2048, E=4096 Turbo baseline.

Run from any directory with ``python path/to/tests/test_reference.py -v``.
Reference encoder and rate-matching logic follow 3GPP TS 36.212, sections
5.1.3.2 and 5.1.4.1, independently of the srsLTE implementation:
https://www.etsi.org/deliver/etsi_ts/136200_136299/136212/11.04.00_60/ts_136212v110400p.pdf

These are finite correctness checks, not an FER sweep or decoder tuning.
"""

from __future__ import annotations

import ctypes as ct
import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("turbo_under_test", ROOT / "run_turbo_same_channel.py")
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)

K = 2048
E = 4096
M = 3 * K + 12


def reference_qpp() -> np.ndarray:
    """Table 5.1.3-3, row 124; output i reads input Pi(i)."""
    return np.asarray([(31 * i + 64 * i * i) % K for i in range(K)], dtype=np.int64)


def reference_rsc(payload: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Polynomial arithmetic: q=u/(1+D^2+D^3), parity=q(1+D+D^3).

    Three zero q coefficients append the terminating inputs automatically.
    This avoids reproducing the native encoder's register-update loop.
    """
    size = len(payload)
    q = np.zeros(size + 3, dtype=np.uint8)
    for i, bit in enumerate(payload):
        q[i] = int(bit)
        if i >= 2:
            q[i] ^= q[i - 2]
        if i >= 3:
            q[i] ^= q[i - 3]
    systematic = q.copy()
    systematic[2:] ^= q[:-2]
    systematic[3:] ^= q[:-3]
    parity = q.copy()
    parity[1:] ^= q[:-1]
    parity[3:] ^= q[:-3]
    np.testing.assert_array_equal(systematic[:size], payload)
    return systematic, parity


def reference_encode(payload: np.ndarray) -> np.ndarray:
    s1, p1 = reference_rsc(payload)
    s2, p2 = reference_rsc(payload[reference_qpp()])
    body = np.column_stack((payload, p1[:K], p2[:K])).reshape(-1)
    tail1 = np.column_stack((s1[K:], p1[K:])).reshape(-1)
    tail2 = np.column_stack((s2[K:], p2[K:])).reshape(-1)
    return np.concatenate((body, tail1, tail2)).astype(np.uint8)


def reference_rate_match_indices() -> np.ndarray:
    """Locate each real bit in the circular buffer, then order by RV0 distance.

    Unlike the production forward-buffer walk, this inverse mapping never
    creates NULL padding. Five-bit reversal is the table's column permutation.
    """
    rows = (K + 4 + 31) // 32
    padded = 32 * rows
    dummy = padded - (K + 4)
    buffer_size = 3 * padded
    positions = []
    for mother_index in range(M):
        position, stream = divmod(mother_index, 3)
        padded_index = position + dummy
        if stream == 2:
            padded_index = (padded_index - 1) % padded
        row, col = divmod(padded_index, 32)
        reversed_col = int(format(col, "05b")[::-1], 2)
        interleaved_index = reversed_col * rows + row
        circular_index = interleaved_index if stream == 0 else padded + 2 * interleaved_index + stream - 1
        positions.append(((circular_index - 2 * rows) % buffer_size, mother_index))
    positions.sort()
    return np.asarray([mother_index for _, mother_index in positions[:E]], dtype=np.int32)


def independent_profile() -> np.ndarray:
    return np.tile(np.asarray([0.15] * 3 + [0.01] * 13), 256)


def exhaustive_component_maxlog(systematic_llr, parity_llr) -> np.ndarray:
    """Enumerate every zero-start/zero-end path, with no BCJR recursion."""
    size = len(systematic_llr) - 3
    scores = []
    messages = []
    for value in range(1 << size):
        message = np.asarray([(value >> i) & 1 for i in range(size)], dtype=np.uint8)
        systematic, parity = reference_rsc(message)
        metric = np.dot(1.0 - 2.0 * systematic, systematic_llr)
        metric += np.dot(1.0 - 2.0 * parity, parity_llr)
        scores.append(0.5 * metric)
        messages.append(message)
    scores = np.asarray(scores)
    messages = np.asarray(messages)
    return np.asarray([scores[messages[:, i] == 0].max() - scores[messages[:, i] == 1].max()
                       for i in range(size)])


class ReferenceStructureTests(unittest.TestCase):
    def test_qpp_is_bijective(self):
        np.testing.assert_array_equal(np.sort(reference_qpp()), np.arange(K))
        self.assertEqual(len(np.unique(reference_qpp())), K)

    def test_polynomial_rsc_known_impulse_and_termination(self):
        # Expansion of (1+D+D^3)/(1+D^2+D^3) begins 1,1,1,1,0,0,1.
        message = np.asarray([1, 0, 0, 0, 0, 0, 0], dtype=np.uint8)
        systematic, parity = reference_rsc(message)
        np.testing.assert_array_equal(parity[:7], [1, 1, 1, 1, 0, 0, 1])
        # Verify all eight possible final memory states terminate in 3 steps.
        for value in range(8):
            bits = np.asarray([(value >> i) & 1 for i in range(3)], dtype=np.uint8)
            terminated, _ = reference_rsc(bits)
            q = []
            for i, bit in enumerate(terminated):
                q.append(int(bit) ^ (q[i - 2] if i >= 2 else 0) ^ (q[i - 3] if i >= 3 else 0))
            self.assertEqual(q[-3:], [0, 0, 0])
        self.assertEqual(len(systematic), len(message) + 3)

    def test_rate_matching_matches_inverse_standard_mapping(self):
        actual = runner.rate_match_indices()
        expected = reference_rate_match_indices()
        np.testing.assert_array_equal(actual, expected)
        self.assertEqual(actual.shape, (E,))
        self.assertEqual(len(np.unique(actual)), E)
        self.assertEqual(np.count_nonzero(actual >= 3 * K), 8)
        # RV0 punctures some systematic bits; it does not send all K of them.
        self.assertEqual(np.count_nonzero((actual < 3 * K) & (actual % 3 == 0)), 1920)

    def test_exact_channel_matches_authorized_profile_and_law(self):
        profile = runner.load_profile(runner.DEFAULT_PROFILE)
        np.testing.assert_array_equal(profile, independent_profile())
        self.assertEqual(np.count_nonzero(profile == 0.15), 768)
        self.assertEqual(np.count_nonzero(profile == 0.01), 3328)
        for floor in (0.001, 0.017, 0.055):
            aged = runner.aged_probabilities(profile, 2.0, floor)
            expected = np.tile([0.30 + floor] * 3 + [0.02 + floor] * 13, 256)
            np.testing.assert_allclose(aged, expected, rtol=0, atol=1e-15)
            self.assertAlmostEqual(float(aged.mean()), 0.0725 + floor, places=14)


class NativeCodecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Missing DLL is an error, so a test run cannot silently pass by skips.
        cls.codec = runner.Codec()
        cls.indices = reference_rate_match_indices()
        cls.magnitudes = np.log((1.0 - independent_profile()) / independent_profile())
        cls.fp = ct.POINTER(ct.c_float)
        cls.u8p = ct.POINTER(ct.c_uint8)
        cls.codec.lib.turbo_component_map.argtypes = [cls.fp, cls.fp, cls.fp, ct.c_int]
        cls.codec.lib.turbo_component_map.restype = ct.c_int
        cls.codec.lib.turbo_rate_indices.argtypes = [ct.POINTER(ct.c_int)]
        cls.codec.lib.turbo_rate_indices.restype = ct.c_int
        cls.codec.lib.turbo_rate_encode.argtypes = [cls.u8p, cls.u8p]
        cls.codec.lib.turbo_rate_encode.restype = ct.c_int
        cls.codec.lib.turbo_rate_recover.argtypes = [cls.fp, cls.fp]
        cls.codec.lib.turbo_rate_recover.restype = ct.c_int

    @classmethod
    def tearDownClass(cls):
        cls.codec.close()

    def assert_decodes(self, payload, flips, magnitudes=None):
        magnitude = self.magnitudes if magnitudes is None else magnitudes
        tx = self.codec.encode(payload)[self.indices]
        received = tx ^ np.asarray(flips, dtype=np.uint8)
        mother_llr = np.zeros(M, dtype=np.float32)
        mother_llr[self.indices] = np.where(received == 0, magnitude, -magnitude)
        decoded = self.codec.decode(mother_llr, iterations=8)
        np.testing.assert_array_equal(decoded, payload)

    def test_encoder_matches_independent_polynomial_reference(self):
        rng = np.random.default_rng(20261010)
        cases = [np.zeros(K, dtype=np.uint8), np.ones(K, dtype=np.uint8),
                 np.arange(K, dtype=np.uint8) % 2]
        for position in (0, 1, K // 2, K - 1):
            impulse = np.zeros(K, dtype=np.uint8)
            impulse[position] = 1
            cases.append(impulse)
        cases.extend(rng.integers(0, 2, K, dtype=np.uint8) for _ in range(5))
        for case_index, payload in enumerate(cases):
            with self.subTest(case=case_index):
                native = self.codec.encode(payload)
                self.assertEqual(native.shape, (M,))
                np.testing.assert_array_equal(native, reference_encode(payload))

    def test_component_soft_outputs_match_exhaustive_maxlog(self):
        rng = np.random.default_rng(104)
        for size in (3, 6, 8):
            for case in range(4):
                systematic = rng.uniform(-5.0, 5.0, size + 3).astype(np.float32)
                parity = rng.uniform(-5.0, 5.0, size + 3).astype(np.float32)
                if case == 0:
                    systematic.fill(0)  # parity and terminal observations only
                posterior = np.empty(size, dtype=np.float32)
                status = self.codec.lib.turbo_component_map(
                    systematic.ctypes.data_as(self.fp), parity.ctypes.data_as(self.fp),
                    posterior.ctypes.data_as(self.fp), size)
                with self.subTest(size=size, case=case):
                    self.assertEqual(status, 0)
                    expected = exhaustive_component_maxlog(systematic, parity)
                    np.testing.assert_allclose(posterior, expected, rtol=2e-6, atol=1e-5)

    def test_native_rate_match_and_recovery_match_independent_indices(self):
        indices = np.empty(E, dtype=np.int32)
        self.assertEqual(self.codec.lib.turbo_rate_indices(indices.ctypes.data_as(ct.POINTER(ct.c_int))), 0)
        np.testing.assert_array_equal(indices, self.indices)
        rng = np.random.default_rng(109)
        mother = reference_encode(rng.integers(0, 2, K, dtype=np.uint8))
        transmitted = np.empty(E, dtype=np.uint8)
        self.assertEqual(self.codec.lib.turbo_rate_encode(
            mother.ctypes.data_as(self.u8p), transmitted.ctypes.data_as(self.u8p)), 0)
        np.testing.assert_array_equal(transmitted, mother[self.indices])
        llr = rng.uniform(-8.0, 8.0, E).astype(np.float32)
        recovered = np.empty(M, dtype=np.float32)
        self.assertEqual(self.codec.lib.turbo_rate_recover(
            llr.ctypes.data_as(self.fp), recovered.ctypes.data_as(self.fp)), 0)
        expected = np.zeros(M, dtype=np.float32)
        expected[self.indices] = llr
        np.testing.assert_array_equal(recovered, expected)

    def test_fullchain_no_noise_nonzero_messages(self):
        rng = np.random.default_rng(105)
        cases = [np.zeros(K, dtype=np.uint8), np.ones(K, dtype=np.uint8),
                 np.arange(K, dtype=np.uint8) % 2]
        cases.extend(rng.integers(0, 2, K, dtype=np.uint8) for _ in range(5))
        for case_index, payload in enumerate(cases):
            with self.subTest(case=case_index):
                self.assert_decodes(payload, np.zeros(E, dtype=np.uint8))

    def test_fixed_sparse_errors_are_corrected(self):
        rng = np.random.default_rng(106)
        for count in (1, 8, 32):
            payload = rng.integers(0, 2, K, dtype=np.uint8)
            flips = np.zeros(E, dtype=np.uint8)
            flips[rng.choice(E, count, replace=False)] = 1
            with self.subTest(flips=count):
                self.assert_decodes(payload, flips)

    def test_encoder_linearity_including_tails_and_puncturing(self):
        rng = np.random.default_rng(107)
        left = rng.integers(0, 2, K, dtype=np.uint8)
        right = rng.integers(0, 2, K, dtype=np.uint8)
        summed = self.codec.encode(left ^ right)
        separate = self.codec.encode(left) ^ self.codec.encode(right)
        np.testing.assert_array_equal(summed, separate)
        np.testing.assert_array_equal(summed[self.indices], separate[self.indices])

    def test_same_channel_errors_zero_and_nonzero_messages(self):
        # Identical flip mask and enrollment magnitudes on every physical bit.
        # These finite masks exercise sign/scrambling symmetry without making
        # a general claim about every finite-precision decoder tie.
        rng = np.random.default_rng(108)
        for probability in (0.01, 0.04):
            payload = rng.integers(0, 2, K, dtype=np.uint8)
            flips = (rng.random(E) < probability).astype(np.uint8)
            estimates = []
            for message in (np.zeros(K, dtype=np.uint8), payload):
                tx = self.codec.encode(message)[self.indices]
                llr = np.zeros(M, dtype=np.float32)
                llr[self.indices] = np.where((tx ^ flips) == 0, self.magnitudes, -self.magnitudes)
                estimates.append(self.codec.decode(llr, iterations=8))
            with self.subTest(flip_probability=probability):
                np.testing.assert_array_equal(estimates[0], estimates[1] ^ payload)


if __name__ == "__main__":
    unittest.main()
