from __future__ import annotations

import unittest


class CandidateFeatureTableTests(unittest.TestCase):
    def test_feature_table_normalizes_executor_and_workbench_candidates(self):
        from neurobench.discovery.ranking import build_candidate_feature_table

        candidates = [
            {
                "id": "roi_002",
                "x": 20.0,
                "y": 12.0,
                "area_px": 9,
                "bbox": [18, 10, 22, 14],
                "peak_z": 4.2,
            },
            {
                "id": "roi_001",
                "centroidX": 5.5,
                "centroidY": 7.0,
                "area": 12,
                "traceSnr": 2.4,
                "localCorrelationMean": 0.6,
                "eventSupport": 0.5,
                "artifactScore": 0.1,
                "priorityScore": 3.0,
                "events": [{"frame": 3, "z": 2.0, "amplitude": 0.7}, {"frame": 8, "z": 4.0, "amplitude": 1.2}],
            },
        ]

        rows = build_candidate_feature_table(candidates, video_shape={"width": 32, "height": 24})

        self.assertEqual([row["candidate_id"] for row in rows], ["roi_001", "roi_002"])
        self.assertEqual(rows[0]["event_count"], 2)
        self.assertEqual(rows[0]["event_max_z"], 4.0)
        self.assertEqual(rows[0]["event_mean_z"], 3.0)
        self.assertEqual(rows[0]["event_max_amplitude"], 1.2)
        self.assertEqual(rows[0]["trace_snr"], 2.4)
        self.assertEqual(rows[0]["local_correlation"], 0.6)
        self.assertEqual(rows[0]["event_support"], 0.5)
        self.assertEqual(rows[0]["artifact_score"], 0.1)
        self.assertEqual(rows[0]["raw_priority_score"], 3.0)
        self.assertEqual(rows[1]["bbox_width_px"], 5.0)
        self.assertEqual(rows[1]["bbox_height_px"], 5.0)
        self.assertEqual(rows[1]["fill_fraction"], 0.36)
        self.assertEqual(rows[1]["peak_z"], 4.2)
        self.assertEqual(rows[1]["edge_distance_px"], 11.0)

    def test_feature_table_supports_pixel_footprints(self):
        from neurobench.discovery.ranking import build_candidate_feature_table

        rows = build_candidate_feature_table(
            [
                {
                    "id": "footprint",
                    "pixels": [(3, 4), (4, 4), (3, 5), (4, 5), (5, 5)],
                    "z": 2.5,
                }
            ],
            video_shape=(10, 12),
        )

        self.assertEqual(rows[0]["centroid_x"], 3.8)
        self.assertEqual(rows[0]["centroid_y"], 4.6)
        self.assertEqual(rows[0]["area_px"], 5.0)
        self.assertEqual(rows[0]["bbox_width_px"], 3.0)
        self.assertEqual(rows[0]["bbox_height_px"], 2.0)
        self.assertEqual(rows[0]["bbox_area_px"], 6.0)
        self.assertAlmostEqual(rows[0]["fill_fraction"], 0.833333)

    def test_feature_table_validation_rejects_missing_and_duplicate_ids(self):
        from neurobench.discovery.ranking import REQUIRED_FEATURE_COLUMNS, validate_candidate_feature_table

        valid_row = {column: 0.0 for column in REQUIRED_FEATURE_COLUMNS}
        valid_row["candidate_id"] = "same"

        with self.assertRaisesRegex(ValueError, "Duplicate candidate_id"):
            validate_candidate_feature_table([valid_row, dict(valid_row)])

        incomplete = dict(valid_row)
        del incomplete["area_px"]
        with self.assertRaisesRegex(ValueError, "missing required columns"):
            validate_candidate_feature_table([incomplete])


if __name__ == "__main__":
    unittest.main()
