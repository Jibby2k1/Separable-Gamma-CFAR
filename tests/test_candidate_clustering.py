from __future__ import annotations

import unittest


class CandidateClusteringTests(unittest.TestCase):
    def test_cluster_candidates_groups_overlapping_candidates(self):
        from neurobench.discovery.clustering import cluster_candidates

        payload = cluster_candidates(
            [
                {"id": "roi_001", "x": 10.0, "y": 10.0, "area_px": 16, "bbox": [8, 8, 12, 12]},
                {"id": "roi_002", "x": 11.0, "y": 10.5, "area_px": 18, "bbox": [9, 8, 13, 12]},
                {"id": "roi_003", "x": 30.0, "y": 30.0, "area_px": 12, "bbox": [29, 29, 32, 32]},
            ],
            centroid_distance_px=3.0,
            bbox_iou_threshold=0.20,
        )

        self.assertEqual(payload["candidate_count"], 3)
        self.assertEqual(payload["cluster_count"], 1)
        self.assertEqual(payload["singleton_count"], 1)
        self.assertEqual(payload["singletons"], ["roi_003"])
        cluster = payload["clusters"][0]
        self.assertEqual(cluster["candidate_ids"], ["roi_001", "roi_002"])
        self.assertEqual(cluster["candidate_count"], 2)
        self.assertIn("possible_duplicate", cluster["issue_codes"])
        self.assertIn("close_centroids", cluster["issue_codes"])
        self.assertEqual(cluster["suggested_action"], "review_duplicate_or_merge")
        self.assertEqual(cluster["links"][0]["reasons"], ["nearby_centroids", "overlapping_bboxes"])

    def test_cluster_candidate_features_uses_transitive_components(self):
        from neurobench.discovery.clustering import cluster_candidate_features
        from neurobench.discovery.ranking import build_candidate_feature_table

        features = build_candidate_feature_table(
            [
                {"id": "a", "x": 0.0, "y": 0.0, "area_px": 8},
                {"id": "b", "x": 4.0, "y": 0.0, "area_px": 8},
                {"id": "c", "x": 8.0, "y": 0.0, "area_px": 8},
                {"id": "d", "x": 40.0, "y": 40.0, "area_px": 8},
            ]
        )

        payload = cluster_candidate_features(features, centroid_distance_px=4.1, bbox_iou_threshold=0.5)

        self.assertEqual(payload["cluster_count"], 1)
        self.assertEqual(payload["clusters"][0]["candidate_ids"], ["a", "b", "c"])
        self.assertIn("clustered_candidates", payload["clusters"][0]["issue_codes"])
        self.assertEqual(payload["singletons"], ["d"])

    def test_cluster_candidate_features_rejects_invalid_thresholds(self):
        from neurobench.discovery.clustering import cluster_candidate_features
        from neurobench.discovery.ranking import build_candidate_feature_table

        features = build_candidate_feature_table([{"id": "a", "x": 0.0, "y": 0.0, "area_px": 8}])

        with self.assertRaisesRegex(ValueError, "centroid_distance_px"):
            cluster_candidate_features(features, centroid_distance_px=-1)
        with self.assertRaisesRegex(ValueError, "bbox_iou_threshold"):
            cluster_candidate_features(features, bbox_iou_threshold=1.5)


if __name__ == "__main__":
    unittest.main()
