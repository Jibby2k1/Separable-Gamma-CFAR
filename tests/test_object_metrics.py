from __future__ import annotations

import unittest


class ObjectMetricsTests(unittest.TestCase):
    def test_spatial_iou_and_centroid_distance_for_bbox_objects(self):
        from neurobench.metrics.detection import centroid_distance, spatial_iou

        a = {"id": "a", "bbox": [0, 0, 4, 4]}
        b = {"id": "b", "bbox": [1, 1, 4, 4]}

        self.assertAlmostEqual(spatial_iou(a, b), 9 / 23)
        self.assertAlmostEqual(centroid_distance(a, b), 2**0.5)

    def test_object_level_matching_counts_duplicate_and_false_positive_candidates(self):
        from neurobench.metrics.detection import object_matching_metrics

        ground_truth = [
            {"id": "gt_a", "bbox": [0, 0, 4, 4]},
            {"id": "gt_b", "bbox": [10, 10, 4, 4]},
        ]
        candidates = [
            {"id": "cand_a", "bbox": [0, 0, 4, 4]},
            {"id": "cand_b", "bbox": [11, 10, 4, 4]},
            {"id": "cand_a_duplicate", "bbox": [1, 1, 4, 4]},
            {"id": "cand_fp", "bbox": [22, 22, 3, 3]},
        ]

        metrics = object_matching_metrics(ground_truth, candidates, iou_threshold=0.25)

        self.assertEqual(metrics["TP"], 2)
        self.assertEqual(metrics["FP"], 2)
        self.assertEqual(metrics["FN"], 0)
        self.assertEqual(metrics["object_precision"], 0.5)
        self.assertEqual(metrics["object_recall"], 1.0)
        self.assertEqual(metrics["duplicate_candidate_count"], 1)
        self.assertEqual(metrics["split_ground_truth_count"], 1)
        self.assertEqual([match["gt_id"] for match in metrics["matches"]], ["gt_a", "gt_b"])

    def test_centroid_tolerance_can_match_sparse_point_objects(self):
        from neurobench.metrics.detection import object_matching_metrics

        ground_truth = [{"id": "gt_point", "centroid_x": 10.0, "centroid_y": 9.0}]
        candidates = [{"id": "candidate_point", "centroid": [10.8, 9.2]}]

        metrics = object_matching_metrics(
            ground_truth,
            candidates,
            iou_threshold=0.5,
            centroid_tolerance_px=1.0,
        )

        self.assertEqual(metrics["TP"], 1)
        self.assertEqual(metrics["FP"], 0)
        self.assertEqual(metrics["FN"], 0)
        self.assertAlmostEqual(metrics["mean_matched_centroid_distance_px"], (0.8**2 + 0.2**2) ** 0.5)

    def test_mask_and_pixel_footprints_are_supported(self):
        from neurobench.metrics.detection import spatial_iou

        mask_object = {"mask": [[1, 1, 0], [0, 1, 0]]}
        pixel_object = {"pixels": [(0, 0), (1, 0), (2, 0)]}

        self.assertAlmostEqual(spatial_iou(mask_object, pixel_object), 2 / 4)


if __name__ == "__main__":
    unittest.main()
