from __future__ import annotations

import unittest


class ActiveLearningTests(unittest.TestCase):
    def test_active_review_batch_prioritizes_uncertainty_conflicts_and_clusters(self):
        from neurobench.discovery.active_learning import build_active_review_batch
        from neurobench.discovery.clustering import cluster_candidates
        from neurobench.discovery.ranking import rank_candidates

        candidates = [
            {
                "id": "strong",
                "x": 20.0,
                "y": 20.0,
                "area_px": 30,
                "peak_z": 5.0,
                "traceSnr": 2.5,
                "eventSupport": 0.8,
                "events": [{"frame": 5, "z": 4.0}],
            },
            {
                "id": "conflict",
                "x": 10.0,
                "y": 10.0,
                "area_px": 20,
                "peak_z": 4.0,
                "traceSnr": 1.6,
                "eventSupport": 0.4,
                "artifactScore": 0.5,
                "events": [{"frame": 6, "z": 3.0}],
            },
            {"id": "overlap_a", "x": 30.0, "y": 30.0, "area_px": 10, "bbox": [28, 28, 32, 32], "peak_z": 2.0},
            {"id": "overlap_b", "x": 31.0, "y": 30.5, "area_px": 12, "bbox": [29, 28, 33, 32], "peak_z": 2.1},
        ]
        ranked = rank_candidates(candidates, video_shape={"width": 48, "height": 48})
        clusters = cluster_candidates(candidates, video_shape={"width": 48, "height": 48}, centroid_distance_px=3.0)

        batch = build_active_review_batch(ranked, clusters=clusters, target_size=4)

        self.assertEqual(batch["selected_task_count"], 4)
        task_ids = [task["task_id"] for task in batch["tasks"]]
        self.assertIn("candidate:conflict", task_ids)
        self.assertTrue(any(task_id.startswith("cluster:") for task_id in task_ids))
        conflict = next(task for task in batch["tasks"] if task["task_id"] == "candidate:conflict")
        self.assertIn("artifact_neuron_conflict", conflict["selected_by"])
        self.assertIn("decision_boundary_uncertainty", conflict["selected_by"])
        self.assertIn("artifact risk with neuron-like evidence", conflict["reasons"])
        cluster = next(task for task in batch["tasks"] if task["task_type"] == "cluster")
        self.assertEqual(cluster["candidate_ids"], ["overlap_a", "overlap_b"])
        self.assertIn("split_merge_cluster", cluster["selected_by"])
        self.assertEqual(batch["summary"]["counts_by_type"]["cluster"], 1)

    def test_active_review_batch_skips_reviewed_candidates_by_default(self):
        from neurobench.discovery.active_learning import build_active_review_batch
        from neurobench.discovery.ranking import rank_candidates

        ranked = rank_candidates(
            [
                {"id": "reviewed", "x": 5.0, "y": 5.0, "area_px": 12, "peak_z": 6.0},
                {"id": "open", "x": 8.0, "y": 5.0, "area_px": 12, "peak_z": 2.0},
            ]
        )

        batch = build_active_review_batch(
            ranked,
            annotations={"schema_version": 3, "rois": {"reviewed": {"cell_state": "accepted"}}},
            target_size=5,
        )

        self.assertEqual([task["candidate_id"] for task in batch["tasks"]], ["open"])

    def test_active_review_batch_can_include_reviewed_candidates(self):
        from neurobench.discovery.active_learning import build_active_review_batch
        from neurobench.discovery.ranking import rank_candidates

        ranked = rank_candidates([{"id": "reviewed", "x": 5.0, "y": 5.0, "area_px": 12, "peak_z": 6.0}])

        batch = build_active_review_batch(
            ranked,
            annotations={"schema_version": 3, "rois": {"reviewed": {"cell_state": "accepted"}}},
            target_size=5,
            include_reviewed=True,
        )

        self.assertEqual(batch["tasks"][0]["candidate_id"], "reviewed")
        self.assertEqual(batch["tasks"][0]["state"], "accepted")

    def test_active_review_batch_rejects_invalid_target_size(self):
        from neurobench.discovery.active_learning import build_active_review_batch

        with self.assertRaisesRegex(ValueError, "target_size"):
            build_active_review_batch([], target_size=0)


if __name__ == "__main__":
    unittest.main()
