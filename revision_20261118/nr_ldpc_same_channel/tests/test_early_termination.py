"""Regression tests for the local NR syndrome early-stop extension."""

import importlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import run_nr_ldpc_same_channel as run
from py3gpp.nrLDPCEncode import _lift_basegraph, _load_basegraph, _check_cw

decoder = importlib.import_module("py3gpp.nrLDPCDecode")


class EarlyTerminationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.info = run.build_info()
        cls.profile = run.load_profile(ROOT / "puf_profile_long.h")
        cls.payload = np.random.default_rng(7).integers(
            0, 2, run.PAYLOAD_BITS, dtype=np.uint8
        )
        cls.tx = run.encode_payload(cls.payload, cls.info)
        cls.llr = np.where(
            cls.tx == 0, 1.0, -1.0
        ) * np.log((1 - cls.profile) / cls.profile)
        cls.recovered = run.nrRateRecoverLDPC(
            cls.llr, run.PAYLOAD_BITS, run.NOMINAL_RATE,
            run.RV, run.MODULATION, run.LAYERS, numCB=1
        )

    def decode(self, recovered, limit=20, **kwargs):
        return decoder.nrLDPCDecode(
            recovered, 2, limit, Algorithm="Normalized min-sum",
            ScalingFactor=0.75, **kwargs
        )

    def test_no_noise_stops_and_preserves_payload(self):
        decoded, iterations, crc_ok = run.decode_llr(self.llr, self.info)
        np.testing.assert_array_equal(decoded, self.payload)
        self.assertTrue(crc_ok)
        self.assertGreaterEqual(iterations, 1)
        self.assertLess(iterations, 20)
        early, _ = self.decode(self.recovered, Termination="early")
        fixed, fixed_iterations = self.decode(self.recovered)
        np.testing.assert_array_equal(early, fixed)
        self.assertEqual(fixed_iterations, 20)

    def test_full_codeword_check_including_punctured_filler_and_parity(self):
        block = run.nrCodeBlockSegmentLDPC(
            run.nrCRCEncode(self.payload.astype(np.int8), "16")[:, 0], 2
        )
        punctured = run.nrLDPCEncode(block, 2)[:, 0]
        full = np.concatenate((block[:416, 0], punctured))
        full[full < 0] = 0  # known filler values
        # Zc=208 belongs to lifting-set index 6.
        bm = _load_basegraph(6, 2)
        pcm = _lift_basegraph(bm, 208).astype(np.int32)
        self.assertEqual(pcm.shape, (8736, 10816))
        self.assertTrue(_check_cw(bm, 208, full))
        self.assertTrue(decoder._parity_checks_pass(pcm, 1.0 - 2.0 * full))
        for position in (0, 2064, 2080, 10815):
            with self.subTest(position=position):
                damaged = full.copy()
                damaged[position] ^= 1
                self.assertFalse(_check_cw(bm, 208, damaged))
                self.assertFalse(decoder._parity_checks_pass(pcm, 1.0 - 2.0 * damaged))

    def test_ms_option_preserves_no_noise_payload_and_uses_unit_scaling(self):
        with patch.object(run, "nrLDPCDecode", wraps=run.nrLDPCDecode) as called:
            decoded, iterations, crc_ok = run.decode_llr(self.llr, self.info, "ms")
        np.testing.assert_array_equal(decoded, self.payload)
        self.assertTrue(crc_ok)
        self.assertLess(iterations, 20)
        self.assertEqual(called.call_args.kwargs["ScalingFactor"], 1.0)
        self.assertEqual(called.call_args.kwargs["Termination"], "early")

    def test_ms_vectorized_matches_scalar_for_noisy_frame(self):
        rng = np.random.default_rng(20260916)
        flips = rng.random(run.E_BITS) < run.aged_probabilities(self.profile, 2, 0.017)
        noisy = self.llr * np.where(flips, -1.0, 1.0)
        recovered = run.nrRateRecoverLDPC(
            noisy, run.PAYLOAD_BITS, run.NOMINAL_RATE,
            run.RV, run.MODULATION, run.LAYERS, numCB=1
        )
        options = dict(Algorithm="Normalized min-sum", ScalingFactor=1.0,
                       Termination="early")
        vectorized, vector_iterations = decoder.nrLDPCDecode(
            recovered, 2, 2, vectorize=True, **options
        )
        scalar, scalar_iterations = decoder.nrLDPCDecode(
            recovered, 2, 2, vectorize=False, **options
        )
        np.testing.assert_array_equal(vectorized, scalar)
        self.assertEqual(vector_iterations, scalar_iterations)

    def test_stops_at_first_valid_full_iteration(self):
        rng = np.random.default_rng(20260916)
        flips = rng.random(run.E_BITS) < run.aged_probabilities(self.profile, 2, 0.017)
        noisy = self.llr * np.where(flips, -1.0, 1.0)
        recovered = run.nrRateRecoverLDPC(
            noisy, run.PAYLOAD_BITS, run.NOMINAL_RATE,
            run.RV, run.MODULATION, run.LAYERS, numCB=1
        )
        passed = []
        original_check = decoder._parity_checks_pass

        def record_check(pcm, llr):
            result = original_check(pcm, llr)
            passed.append(result)
            return result

        with patch.object(decoder, "_parity_checks_pass", side_effect=record_check):
            early, iterations = self.decode(recovered, Termination="early")
        self.assertEqual(len(passed), iterations)
        self.assertFalse(any(passed[:-1]))
        self.assertTrue(passed[-1] or iterations == 20)
        prefix, _ = self.decode(recovered, limit=iterations, Termination="max")
        np.testing.assert_array_equal(early, prefix)

    def test_failed_checks_run_to_cap_and_match_fixed_mode(self):
        noisy = np.random.default_rng(4).normal(size=self.recovered.shape)
        passed = []
        original_check = decoder._parity_checks_pass

        def record_check(pcm, llr):
            result = original_check(pcm, llr)
            passed.append(result)
            return result

        with patch.object(decoder, "_parity_checks_pass", side_effect=record_check):
            early, iterations = self.decode(noisy, limit=3, Termination="early")
        self.assertEqual(passed, [False, False, False])
        self.assertEqual(iterations, 3)
        fixed, _ = self.decode(noisy, limit=3, Termination="max")
        np.testing.assert_array_equal(early, fixed)

    def test_multiple_blocks_report_maximum_iterations(self):
        noisy = np.random.default_rng(4).normal(size=self.recovered.shape)
        recovered = np.concatenate((noisy, self.recovered), axis=1)
        decoded, iterations = self.decode(recovered, limit=3, Termination="early")
        self.assertEqual(iterations, 3)  # last block stops earlier, not 3
        for i in range(2):
            single, _ = self.decode(recovered[:, i:i + 1], limit=3, Termination="early")
            np.testing.assert_array_equal(decoded[:, i], single[:, 0])

    def test_mean_includes_failed_frames(self):
        results = [(np.zeros(2048, dtype=np.uint8), 4, True),
                   (np.zeros(2048, dtype=np.uint8), 20, False)]
        with patch.object(run, "encode_payload", return_value=np.zeros(4096, dtype=np.uint8)), \
             patch.object(run, "decode_llr", side_effect=results):
            row = run.run_point(0, 0.017, 2, 42, 2, str(ROOT / "puf_profile_long.h"))
        self.assertEqual(row["mean_iterations"], 12)
        self.assertEqual(row["message_failures"], 2)
        self.assertEqual(row["crc_failures"], 1)

    def test_existing_results_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            existing = Path(directory) / "fer_summary.csv"
            existing.touch()
            with patch.object(sys, "argv", ["runner", "--smoke", "--output", directory]):
                with self.assertRaises(FileExistsError):
                    run.main()

    def test_invalid_options_rejected(self):
        for kwargs in ({"Termination": "unknown"}, {"limit": 0}, {"limit": 1.5}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.decode(self.recovered, **kwargs)


if __name__ == "__main__":
    unittest.main()
