from __future__ import annotations

import unittest

try:
    import numpy as np
except ModuleNotFoundError:
    np = None


def require_numpy():
    if np is None:
        raise unittest.SkipTest("numpy is not installed in this Python environment")


def _blob_frame(height: int = 24, width: int = 28):
    y_grid, x_grid = np.mgrid[0:height, 0:width]
    blob = np.exp(-(((x_grid - 14.0) ** 2) + ((y_grid - 11.0) ** 2)) / (2 * 2.0**2))
    return blob.astype(np.float32)


class MotionAlgorithmTests(unittest.TestCase):
    def test_estimate_integer_shift_returns_correction_shift(self):
        require_numpy()
        from neurobench.algorithms.motion import estimate_integer_shift, shift_frame_integer

        reference = _blob_frame()
        moved = shift_frame_integer(reference, 2, -1)

        shift = estimate_integer_shift(reference, moved, max_shift_px=4)

        self.assertEqual((shift["dy"], shift["dx"]), (-2, 1))

    def test_estimate_rigid_shifts_registers_shifted_video(self):
        require_numpy()
        from neurobench.algorithms.motion import estimate_rigid_shifts, shift_frame_integer

        reference = _blob_frame()
        video = np.stack(
            [
                reference,
                shift_frame_integer(reference, 1, 2),
                shift_frame_integer(reference, -2, 1),
            ]
        ).astype(np.float32)

        result = estimate_rigid_shifts(video, max_shift_px=4)
        registered = result["registered_video"]

        self.assertEqual([(item["dy"], item["dx"]) for item in result["shifts"]], [(0, 0), (-1, -2), (2, -1)])
        self.assertLess(float(np.mean(np.abs(registered[0] - registered[1]))), 0.02)
        self.assertLess(float(np.mean(np.abs(registered[0] - registered[2]))), 0.02)
        self.assertEqual(result["summary"]["max_abs_l1_shift_px"], 3)

    def test_estimate_rigid_shifts_rejects_invalid_reference(self):
        require_numpy()
        from neurobench.algorithms.motion import estimate_rigid_shifts

        video = np.zeros((2, 8, 8), dtype=np.float32)

        with self.assertRaisesRegex(ValueError, "reference"):
            estimate_rigid_shifts(video, reference="middle")


if __name__ == "__main__":
    unittest.main()
