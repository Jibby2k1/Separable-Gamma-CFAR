from __future__ import annotations

import unittest

try:
    import numpy as np
except ImportError:  # pragma: no cover - depends on lightweight CI/base env
    np = None


class OnlineStageTests(unittest.TestCase):
    def test_adaptive_ewma_z_detects_synthetic_event_and_reports_latency(self):
        if np is None:
            self.skipTest("numpy is not installed")
        from neurobench.online import AdaptiveEwmaZStage, synthetic_event_video

        video = synthetic_event_video(frames=24, height=32, width=32, event_frame=8, event_amplitude=12.0)
        stage = AdaptiveEwmaZStage(alpha=0.05, threshold_z=3.0, epsilon=0.5)
        counts = []
        for index, frame in enumerate(video):
            result = stage.process_frame(frame, index, index / 100.0)
            counts.append(result["candidate_pixel_count"])

        self.assertGreater(counts[8], 0)
        summary = stage.latency_summary()
        self.assertEqual(summary["frames"], 24)
        self.assertIsNotNone(summary["p95_ms"])

    def test_adaptive_ewma_z_rejects_invalid_params(self):
        if np is None:
            self.skipTest("numpy is not installed")
        from neurobench.online import AdaptiveEwmaZStage

        with self.assertRaises(ValueError):
            AdaptiveEwmaZStage(alpha=0)
        with self.assertRaises(ValueError):
            AdaptiveEwmaZStage(threshold_z=-1)

    def test_synthetic_event_video_shape(self):
        if np is None:
            self.skipTest("numpy is not installed")
        from neurobench.online import synthetic_event_video

        video = synthetic_event_video(frames=5, height=7, width=9)

        self.assertEqual(video.shape, (5, 7, 9))
        self.assertEqual(video.dtype, np.float32)


if __name__ == "__main__":
    unittest.main()
