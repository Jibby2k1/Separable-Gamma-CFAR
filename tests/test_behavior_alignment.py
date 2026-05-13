from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


class BehaviorAlignmentDiagnosticsTests(unittest.TestCase):
    def test_sync_diagnostics_accepts_offset_corrected_points(self):
        from neurobench.exports.behavior_alignment import alignment_report

        report = alignment_report(
            {
                "frame_rate_hz": 10.0,
                "imaging_frame_count": 3,
                "behavior": {
                    "alignment_status": "validated",
                    "sync_offset_sec": 0.1,
                    "sync_tolerance_sec": 0.005,
                    "sync_points": [
                        {"imaging_time_sec": 0.1, "behavior_time_sec": 0.0},
                        {"imaging_time_sec": 0.2, "behavior_time_sec": 0.1},
                    ],
                },
            }
        )

        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["status"], "validated")
        self.assertEqual(report["sync"]["status"], "ok")
        self.assertAlmostEqual(report["sync"]["max_abs_error_sec"], 0.0)
        self.assertEqual(report["warnings"], [])

    def test_sync_diagnostics_fails_when_error_exceeds_tolerance(self):
        from neurobench.exports.behavior_alignment import alignment_report

        report = alignment_report(
            {
                "frame_rate_hz": 10.0,
                "imaging_frame_count": 3,
                "behavior": {
                    "alignment_status": "validated",
                    "sync_tolerance_sec": 0.01,
                    "sync_points": [
                        {"imaging_time_sec": 0.0, "behavior_time_sec": 0.0},
                        {"imaging_time_sec": 0.25, "behavior_time_sec": 0.1},
                    ],
                },
            }
        )

        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["sync"]["status"], "failed")
        self.assertGreater(report["sync"]["max_abs_error_sec"], report["sync"]["tolerance_sec"])
        self.assertIn("exceeds tolerance", report["errors"][0])

    def test_resampling_diagnostics_warns_on_duplicate_and_missing_timestamps(self):
        from neurobench.exports.behavior_alignment import alignment_report

        report = alignment_report(
            {
                "frame_rate_hz": 10.0,
                "imaging_frame_count": 4,
                "behavior": {
                    "alignment_status": "validated",
                    "resampling_policy": "sample_behavior_to_imaging_frames",
                    "interpolation_policy": "linear",
                    "behavior_timestamps_sec": [0.0, 0.1, 0.1, None, 0.5],
                },
            }
        )

        source = report["resampling"]["source_timestamps"]
        self.assertEqual(report["status"], "provided_unvalidated")
        self.assertEqual(report["resampling"]["status"], "warning")
        self.assertEqual(report["resampling"]["policy"], "sample_behavior_to_imaging_frames")
        self.assertEqual(source["duplicate_count"], 1)
        self.assertEqual(source["missing_count"], 1)
        self.assertEqual(source["large_gap_count"], 1)
        self.assertTrue(any("duplicate" in warning for warning in report["warnings"]))
        self.assertTrue(any("missing" in warning for warning in report["warnings"]))

    def test_frame_time_mapping_reports_timestamp_mismatch(self):
        from neurobench.exports.behavior_alignment import alignment_report

        report = alignment_report(
            {
                "frame_rate_hz": 10.0,
                "imaging_frame_count": 3,
                "frame_timestamps_sec": [0.0, 0.1, 0.35],
            }
        )

        self.assertEqual(report["frame_time_mapping"]["status"], "warning")
        self.assertAlmostEqual(report["frame_time_mapping"]["max_abs_timestamp_error_sec"], 0.15)
        self.assertTrue(any("frame_rate_hz mapping" in warning for warning in report["warnings"]))

    def test_inverse_dynamics_export_writes_alignment_diagnostics(self):
        from neurobench.exports.inverse_dynamics import export_inverse_dynamics_bundle

        review_data = {
            "dataset": {"dataset_id": "resting", "frame_rate_hz": 10.0},
            "video": {"frames": 3},
            "rois": [{"id": 1, "dffTrace": [0.1, 0.2, 0.3], "eventTrace": [], "zTrace": [], "events": []}],
        }
        annotations = {
            "schema_version": 3,
            "rois": {"1": {"cell_state": "accepted", "trace_quality": "good", "control_ready": "yes", "artifact_class": ""}},
        }
        manifest = {
            "dataset_id": "resting",
            "behavior": {
                "alignment_status": "validated",
                "behavior_timestamps_sec": [0.0, 0.1, 0.1, 0.4],
            },
        }

        with tempfile.TemporaryDirectory() as tmp:
            bundle = export_inverse_dynamics_bundle(review_data, annotations, tmp, dataset_manifest=manifest, created_at="2026-05-13T00:00:00Z")
            alignment = json.loads((Path(tmp) / "alignment_report.json").read_text(encoding="utf-8"))

        self.assertEqual(bundle.alignment_status, "provided_unvalidated")
        self.assertIn("resampling", alignment)
        self.assertEqual(alignment["resampling"]["source_timestamps"]["duplicate_count"], 1)
        self.assertTrue(any("duplicate" in warning for warning in bundle.warnings))


if __name__ == "__main__":
    unittest.main()
