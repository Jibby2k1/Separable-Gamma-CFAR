from __future__ import annotations

import unittest


class EventMetricsTests(unittest.TestCase):
    def test_event_timing_metrics_match_onset_peak_and_duration(self):
        from neurobench.metrics.event_quality import event_timing_metrics

        ground_truth = [
            {"event_id": "gt_1", "roi_id": "r1", "start_frame": 10, "peak_frame": 12, "end_frame": 15},
            {"event_id": "gt_2", "roi_id": "r2", "start_frame": 25, "peak_frame": 27, "end_frame": 30},
        ]
        candidates = [
            {"event_id": "cand_1", "roi_id": "r1", "start_frame": 11, "peak_frame": 13, "end_frame": 15, "amplitude": 0.5, "snr": 4.0, "isolation": 0.8},
            {"event_id": "cand_2", "roi_id": "r2", "start_frame": 23, "peak_frame": 26, "end_frame": 28, "amplitude": 0.7, "snr": 5.0, "isolation": 0.9},
            {"event_id": "false_event", "roi_id": "r1", "start_frame": 40, "peak_frame": 41, "end_frame": 42, "amplitude": 0.1},
        ]

        metrics = event_timing_metrics(ground_truth, candidates, onset_tolerance_frames=2)

        self.assertEqual(metrics["TP"], 2)
        self.assertEqual(metrics["FP"], 1)
        self.assertEqual(metrics["FN"], 0)
        self.assertAlmostEqual(metrics["event_precision"], 2 / 3)
        self.assertEqual(metrics["event_recall"], 1.0)
        self.assertAlmostEqual(metrics["mean_onset_timing_error_frames"], -0.5)
        self.assertAlmostEqual(metrics["mean_abs_onset_timing_error_frames"], 1.5)
        self.assertAlmostEqual(metrics["mean_peak_timing_error_frames"], 0.0)
        self.assertAlmostEqual(metrics["mean_duration_error_frames"], -0.5)
        self.assertEqual(metrics["amplitude_distribution"]["count"], 2)
        self.assertAlmostEqual(metrics["event_snr"]["mean"], 4.5)
        self.assertAlmostEqual(metrics["event_isolation"]["mean"], 0.85)

    def test_event_matching_respects_roi_identity_when_present(self):
        from neurobench.metrics.event_quality import event_timing_metrics

        ground_truth = [{"event_id": "gt", "roi_id": "r1", "frame": 10}]
        candidates = [{"event_id": "wrong_roi", "roi_id": "r2", "frame": 10}]

        strict_metrics = event_timing_metrics(ground_truth, candidates, onset_tolerance_frames=0)
        permissive_metrics = event_timing_metrics(
            ground_truth,
            candidates,
            onset_tolerance_frames=0,
            require_same_object=False,
        )

        self.assertEqual(strict_metrics["TP"], 0)
        self.assertEqual(strict_metrics["FP"], 1)
        self.assertEqual(strict_metrics["FN"], 1)
        self.assertEqual(permissive_metrics["TP"], 1)

    def test_event_metrics_support_review_style_frame_only_events(self):
        from neurobench.metrics.event_quality import event_timing_metrics

        ground_truth = [{"roi_id": "1", "frame": 4}, {"roi_id": "1", "frame": 9}]
        candidates = [{"roi_id": "1", "frame": 5, "z": 3.2}, {"roi_id": "1", "frame": 20, "z": 2.0}]

        metrics = event_timing_metrics(ground_truth, candidates, onset_tolerance_frames=1)

        self.assertEqual(metrics["TP"], 1)
        self.assertEqual(metrics["FP"], 1)
        self.assertEqual(metrics["FN"], 1)
        self.assertEqual(metrics["matches"][0]["gt_event_id"], "1:4")
        self.assertEqual(metrics["matches"][0]["candidate_event_id"], "1:5")
        self.assertEqual(metrics["amplitude_distribution"]["mean"], 3.2)

    def test_unmatched_events_return_zero_quality_distributions(self):
        from neurobench.metrics.event_quality import event_timing_metrics

        metrics = event_timing_metrics([{"frame": 1}], [{"frame": 10}], onset_tolerance_frames=1)

        self.assertEqual(metrics["TP"], 0)
        self.assertEqual(metrics["amplitude_distribution"], {"count": 0, "mean": 0.0, "min": 0.0, "max": 0.0})


if __name__ == "__main__":
    unittest.main()
