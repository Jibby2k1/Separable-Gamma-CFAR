from __future__ import annotations

import unittest


class CandidateRankingTests(unittest.TestCase):
    def test_rank_candidates_returns_explanations_and_reasons(self):
        from neurobench.discovery.ranking import rank_candidates

        payload = rank_candidates(
            [
                {
                    "id": "weak_artifact",
                    "x": 2.0,
                    "y": 2.0,
                    "area_px": 6,
                    "peak_z": 2.0,
                    "artifactScore": 0.8,
                    "events": [],
                },
                {
                    "id": "strong_neuron",
                    "centroidX": 12.0,
                    "centroidY": 11.0,
                    "area": 42,
                    "peak_z": 4.0,
                    "traceSnr": 2.5,
                    "localCorrelationMean": 0.7,
                    "eventSupport": 0.6,
                    "events": [{"frame": 4, "z": 3.0}, {"frame": 9, "z": 2.6}],
                },
            ],
            video_shape={"width": 32, "height": 24},
        )

        ranked = payload["ranked_candidates"]

        self.assertEqual(payload["candidate_count"], 2)
        self.assertEqual(ranked[0]["candidate_id"], "strong_neuron")
        self.assertEqual(ranked[0]["rank"], 1)
        self.assertIn("2 candidate events", ranked[0]["reasons"])
        self.assertIn("usable trace SNR", ranked[0]["reasons"])
        self.assertIn("event_support", ranked[0]["reason_codes"])
        self.assertIn("trace_snr", ranked[0]["reason_codes"])
        self.assertGreater(ranked[0]["priority_score"], ranked[1]["priority_score"])
        self.assertTrue(ranked[0]["explanation"]["contributions"])
        self.assertEqual(ranked[1]["candidate_id"], "weak_artifact")
        self.assertIn("artifact risk", ranked[1]["reasons"])
        self.assertIn("near video edge", ranked[1]["reasons"])

    def test_rank_candidate_features_honors_weight_overrides(self):
        from neurobench.discovery.ranking import build_candidate_feature_table, rank_candidate_features

        features = build_candidate_feature_table(
            [
                {"id": "coherent", "x": 10.0, "y": 10.0, "area_px": 10, "localCorrelationMean": 1.0},
                {"id": "eventful", "x": 12.0, "y": 10.0, "area_px": 10, "eventSupport": 1.0},
            ]
        )

        ranked = rank_candidate_features(
            features,
            weights={"local_correlation_weight": 0.0, "event_support_weight": 2.0},
        )

        self.assertEqual(ranked[0]["candidate_id"], "eventful")
        self.assertGreater(ranked[0]["priority_score"], ranked[1]["priority_score"])

    def test_rank_candidate_features_is_deterministic_for_ties(self):
        from neurobench.discovery.ranking import build_candidate_feature_table, rank_candidate_features

        features = build_candidate_feature_table(
            [
                {"id": "roi_002", "x": 10.0, "y": 10.0, "area_px": 10},
                {"id": "roi_001", "x": 11.0, "y": 10.0, "area_px": 10},
            ]
        )

        ranked = rank_candidate_features(features)

        self.assertEqual([row["candidate_id"] for row in ranked], ["roi_001", "roi_002"])


if __name__ == "__main__":
    unittest.main()
