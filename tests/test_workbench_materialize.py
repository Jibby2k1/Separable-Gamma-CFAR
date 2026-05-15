from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from neurobench.workbench.materialize import materialize_virtual_roi_traces


class WorkbenchMaterializeTests(unittest.TestCase):
    def test_materializes_virtual_roi_trace_into_active_run_bucket(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            video = np.zeros((8, 6, 6), dtype=np.float32)
            video[:, 2, 2] = np.array([1, 1, 1, 8, 2, 1, 1, 1], dtype=np.float32)
            video[:, 2, 3] = np.array([1, 1, 1, 7, 2, 1, 1, 1], dtype=np.float32)
            raw = Path(tmp) / "video.npy"
            np.save(raw, video)
            review_data = {
                "video": {"frames": 8, "height": 6, "width": 6, "name": "video.npy"},
                "rois": [],
            }
            annotations = {
                "version": 3,
                "schema_version": 3,
                "settings": {"activeRunId": "baseline"},
                "runs": {
                    "baseline": {
                        "rois": {},
                        "events": {},
                        "suggestions": {},
                        "promotedRois": {},
                        "splitMergeDecisions": {},
                        "virtualRois": {
                            "MR_1": {
                                "id": "MR_1",
                                "roi_kind": "manual_circle",
                                "points": [[2, 2], [3, 2]],
                                "area": 2,
                                "centroidX": 2.5,
                                "centroidY": 2.0,
                            }
                        },
                    }
                },
            }

            result = materialize_virtual_roi_traces(
                review_data=review_data,
                annotations=annotations,
                raw_video_path=raw,
                run_id="baseline",
                event_threshold_z=1.0,
            )

        self.assertEqual(result["materialized_ids"], ["MR_1"])
        roi = result["annotations"]["runs"]["baseline"]["virtualRois"]["MR_1"]
        self.assertTrue(roi["trace_materialized"])
        self.assertEqual(len(roi["dffTrace"]), 8)
        self.assertEqual(len(roi["rawTrace"]), 8)
        self.assertGreater(roi["rawTrace"][3], roi["rawTrace"][0])
        self.assertIn("events", roi)
        self.assertEqual(result["annotations"]["virtualRois"]["MR_1"]["dffTrace"], roi["dffTrace"])

    def test_rejects_review_data_shape_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "video.npy"
            np.save(raw, np.zeros((3, 4, 5), dtype=np.float32))
            with self.assertRaisesRegex(ValueError, "review data expects"):
                materialize_virtual_roi_traces(
                    review_data={"video": {"frames": 4, "height": 4, "width": 5}},
                    annotations={"settings": {}, "virtualRois": {"MR": {"id": "MR", "points": [[1, 1]]}}},
                    raw_video_path=raw,
                )


if __name__ == "__main__":
    unittest.main()
