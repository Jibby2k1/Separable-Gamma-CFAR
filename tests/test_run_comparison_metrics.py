from __future__ import annotations

import unittest


class RunComparisonMetricsTests(unittest.TestCase):
    def test_candidate_consensus_metrics_reports_support_unique_and_pairwise_overlap(self):
        from neurobench.metrics.run_comparison import candidate_consensus_metrics

        metrics = candidate_consensus_metrics(
            [
                {"run_id": "run_a", "candidate_ids": ["1", "2", "3"]},
                {"run_id": "run_b", "candidate_ids": ["2", "3", "4"]},
                {"run_id": "run_c", "candidate_ids": ["3", "4", "5"]},
            ]
        )

        self.assertEqual(metrics["run_count"], 3)
        self.assertEqual(metrics["candidate_count_union"], 5)
        self.assertEqual(metrics["consensus_accepted_candidate_ids"], ["3"])
        self.assertEqual(metrics["unique_accepted_candidate_ids"], ["1", "5"])
        self.assertAlmostEqual(metrics["consensus_rate"], 0.2)
        self.assertEqual(metrics["unique_by_run"][0], {"run_id": "run_a", "candidate_ids": ["1"]})
        self.assertEqual(metrics["unique_by_run"][1], {"run_id": "run_b", "candidate_ids": []})
        self.assertEqual(metrics["unique_by_run"][2], {"run_id": "run_c", "candidate_ids": ["5"]})
        self.assertEqual(metrics["pairwise_overlap"][0]["run_a"], "run_a")
        self.assertEqual(metrics["pairwise_overlap"][0]["run_b"], "run_b")
        self.assertEqual(metrics["pairwise_overlap"][0]["shared_candidate_ids"], ["2", "3"])
        self.assertAlmostEqual(metrics["pairwise_overlap"][0]["jaccard"], 0.5)
        support = {row["candidate_id"]: row for row in metrics["candidate_support"]}
        self.assertEqual(support["3"]["support_count"], 3)
        self.assertEqual(support["4"]["run_ids"], ["run_b", "run_c"])

    def test_candidate_consensus_metrics_accepts_metrics_report_payloads(self):
        from neurobench.metrics.run_comparison import candidate_consensus_metrics

        metrics = candidate_consensus_metrics(
            [
                {
                    "metrics_report_id": "metrics_a",
                    "run_ids": ["run_a"],
                    "metrics": {"object_level": {"accepted_candidate_ids": [{"candidate_id": "1"}, {"id": "2"}]}},
                },
                {
                    "metrics_report_id": "metrics_b",
                    "run_ids": ["run_b"],
                    "metrics": {"object_level": {"unique_accepted_candidates": [{"roi_id": "2"}, "3"]}},
                },
            ]
        )

        self.assertEqual(metrics["consensus_accepted_candidate_ids"], ["2"])
        self.assertEqual(metrics["unique_accepted_candidate_ids"], ["1", "3"])

    def test_metric_winner_table_handles_direction_and_missing_values(self):
        from neurobench.metrics.run_comparison import metric_winner_table

        table = metric_winner_table(
            [
                {
                    "metrics_report_id": "metrics_a",
                    "run_ids": ["run_a"],
                    "metrics": {"object_level": {"object_recall": 0.8}, "runtime": {"duration_seconds": 12}},
                },
                {
                    "metrics_report_id": "metrics_b",
                    "run_ids": ["run_b"],
                    "metrics": {"object_level": {"object_recall": 0.9}, "runtime": {"duration_seconds": 8}},
                },
                {
                    "metrics_report_id": "metrics_c",
                    "run_ids": ["run_c"],
                    "metrics": {"object_level": {"object_recall": "bad"}, "runtime": {}},
                },
            ],
            [("object_level", "object_recall", "higher"), ("runtime", "duration_seconds", "lower")],
        )

        self.assertEqual(table["best_by_metric"]["object_level.object_recall"]["run_id"], "run_b")
        self.assertEqual(table["best_by_metric"]["runtime.duration_seconds"]["run_id"], "run_b")
        self.assertIsNone(table["runs"][2]["values"]["object_level.object_recall"])


if __name__ == "__main__":
    unittest.main()
