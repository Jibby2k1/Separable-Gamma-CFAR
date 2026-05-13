from __future__ import annotations

import unittest

try:
    import numpy as np
except ModuleNotFoundError:
    np = None


def require_numpy():
    if np is None:
        raise unittest.SkipTest("numpy is not installed in this Python environment")


class RealtimeLatencyTests(unittest.TestCase):
    def test_latency_report_runs_adaptive_stage_on_synthetic_source(self):
        require_numpy()
        from neurobench.online import AdaptiveEwmaZStage
        from neurobench.realtime.latency import render_latency_report_markdown, run_latency_report
        from neurobench.realtime.stream import SyntheticFrameSource

        source = SyntheticFrameSource(frames=16, height=24, width=24, frame_rate_hz=100.0, event_frame=6, event_amplitude=12.0)
        stage = AdaptiveEwmaZStage(alpha=0.05, threshold_z=3.0, epsilon=0.5)
        report = run_latency_report(source, stage, frame_budget_ms=10.0, warmup_frames=1)
        markdown = render_latency_report_markdown(report)

        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["processed_frames"], 16)
        self.assertEqual(report["latency"]["frames"], 15)
        self.assertIsNotNone(report["latency"]["p95_ms"])
        self.assertGreater(report["output"]["max_candidate_pixel_count"], 0)
        self.assertIn("# Realtime Latency Report", markdown)
        self.assertIn("AdaptiveEwmaZStage", markdown)

    def test_latency_summary_reports_budget_failures(self):
        from neurobench.realtime.latency import latency_summary

        summary = latency_summary([1.0, 2.0, 8.0], frame_budget_ms=5.0)

        self.assertEqual(summary["frames"], 3)
        self.assertEqual(summary["over_budget_frames"], 1)
        self.assertFalse(summary["budget_pass"])
        self.assertEqual(summary["max_ms"], 8.0)

    def test_latency_report_validates_inputs(self):
        require_numpy()
        from neurobench.online import AdaptiveEwmaZStage
        from neurobench.realtime.latency import run_latency_report
        from neurobench.realtime.stream import SyntheticFrameSource

        source = SyntheticFrameSource(frames=2, height=4, width=4)
        stage = AdaptiveEwmaZStage()
        with self.assertRaisesRegex(ValueError, "frame_budget_ms"):
            run_latency_report(source, stage, frame_budget_ms=0)
        with self.assertRaisesRegex(ValueError, "max_frames"):
            run_latency_report(source, stage, max_frames=0)
        with self.assertRaisesRegex(TypeError, "process_frame"):
            run_latency_report(source, object())


if __name__ == "__main__":
    unittest.main()
