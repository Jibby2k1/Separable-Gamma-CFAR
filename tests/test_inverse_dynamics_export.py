from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _review_data() -> dict:
    return {
        "dataset": {"dataset_id": "resting", "frame_rate_hz": 5.0, "pixel_size_microns": 0.5},
        "video": {"width": 8, "height": 8, "frames": 3, "framePattern": "frame_%04d.png"},
        "rois": [
            {
                "id": 1,
                "dffTrace": [0.1, 0.2, 0.3],
                "eventTrace": [0.0, 1.0, 0.0],
                "zTrace": [0.1, 2.5, 0.2],
                "events": [{"frame": 2, "z": 2.5, "amplitude": 0.7}],
            },
            {
                "id": 2,
                "dffTrace": [0.4, 0.5],
                "eventTrace": [0.0, 0.0],
                "zTrace": [0.3, 0.2],
                "events": [{"frame": 1, "z": 1.2, "amplitude": 0.2}],
            },
        ],
    }


def _annotations() -> dict:
    return {
        "schema_version": 3,
        "rois": {
            "1": {
                "cell_state": "accepted",
                "trace_quality": "good",
                "control_ready": "yes",
                "artifact_class": "",
                "confidence": "high",
                "reason_tags": ["compact"],
            },
            "2": {
                "cell_state": "accepted",
                "trace_quality": "bad",
                "control_ready": "no",
                "artifact_class": "",
                "confidence": "low",
            },
        },
        "events": {"1:2": {"event_state": "accepted", "event_type": "transient", "timing_quality": "clear"}},
    }


class InverseDynamicsExportTests(unittest.TestCase):
    def test_inverse_dynamics_export_writes_bundle_tables_and_alignment_report(self):
        from neurobench.exports.inverse_dynamics import export_inverse_dynamics_bundle

        with tempfile.TemporaryDirectory() as tmp:
            bundle = export_inverse_dynamics_bundle(_review_data(), _annotations(), tmp, created_at="2026-05-13T00:00:00Z")
            root = Path(tmp)
            traces = (root / "accepted_traces.tsv").read_text(encoding="utf-8")
            events = (root / "accepted_events.tsv").read_text(encoding="utf-8")
            metadata = (root / "neuron_metadata.tsv").read_text(encoding="utf-8")
            alignment = json.loads((root / "alignment_report.json").read_text(encoding="utf-8"))
            manifest = json.loads((root / "export_bundle.json").read_text(encoding="utf-8"))
            report = (root / "export_report.md").read_text(encoding="utf-8")
            checksums = json.loads((root / "checksums.json").read_text(encoding="utf-8"))

        self.assertEqual(bundle.profile, "inverse_dynamics")
        self.assertEqual(bundle.alignment_status, "not_provided")
        self.assertIn("\n1\t1\t0.0\t0.1", traces)
        self.assertIn("\n1\t2\t0.2\t0.2", traces)
        self.assertNotIn("\n2\t", traces)
        self.assertIn("\n1\t2\t0.2\t2.5\t0.7\taccepted\ttransient\tclear", events)
        self.assertIn("\n1\taccepted\tgood\tyes", metadata)
        self.assertEqual(alignment["status"], "not_provided")
        self.assertEqual(manifest["selection_policy"]["include_rois"], "accepted_control_ready")
        self.assertEqual(set(checksums), {item["path"] for item in manifest["files"]})
        self.assertIn("Alignment status: `not_provided`", report)

    def test_inverse_dynamics_export_marks_behavior_metadata_unvalidated(self):
        from neurobench.exports.inverse_dynamics import export_inverse_dynamics_bundle

        manifest = {
            "dataset_id": "resting",
            "frame_rate_hz": 10.0,
            "paths": {"tail_motion": "tail.tsv", "sync_table": "sync.tsv"},
            "behavior": {"sync_offset_frames": 2},
        }
        with tempfile.TemporaryDirectory() as tmp:
            bundle = export_inverse_dynamics_bundle(_review_data(), _annotations(), tmp, dataset_manifest=manifest, created_at="2026-05-13T00:00:00Z")
            alignment = json.loads((Path(tmp) / "alignment_report.json").read_text(encoding="utf-8"))

        self.assertEqual(bundle.alignment_status, "provided_unvalidated")
        self.assertEqual(alignment["has_behavior_paths"], True)
        self.assertEqual(alignment["sync_offset_frames"], 2)

    def test_inverse_dynamics_export_honors_validated_alignment_status(self):
        from neurobench.exports.inverse_dynamics import export_inverse_dynamics_bundle

        manifest = {"dataset_id": "resting", "behavior": {"alignment_status": "validated", "timebase": "tail_time_sec"}}
        with tempfile.TemporaryDirectory() as tmp:
            bundle = export_inverse_dynamics_bundle(_review_data(), _annotations(), tmp, dataset_manifest=manifest, created_at="2026-05-13T00:00:00Z")

        self.assertEqual(bundle.alignment_status, "validated")
        self.assertEqual(bundle.warnings, [])

    def test_inverse_dynamics_export_include_pending_exports_all_rois(self):
        from neurobench.exports.inverse_dynamics import export_inverse_dynamics_bundle

        with tempfile.TemporaryDirectory() as tmp:
            bundle = export_inverse_dynamics_bundle(_review_data(), _annotations(), tmp, include_pending=True, created_at="2026-05-13T00:00:00Z")
            traces = (Path(tmp) / "accepted_traces.tsv").read_text(encoding="utf-8")

        self.assertIn("\n2\t1\t0.0\t0.4", traces)
        self.assertIn("Export includes pending/unreviewed ROIs.", bundle.warnings)

    def test_legacy_inverse_dynamics_script_writes_export_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review_path = root / "review_data.json"
            annotations_path = root / "annotations.json"
            out_dir = root / "inverse"
            review_path.write_text(json.dumps(_review_data()), encoding="utf-8")
            annotations_path.write_text(json.dumps(_annotations()), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "tools/export_inverse_dynamics.py",
                    "--review-data",
                    str(review_path),
                    "--annotations",
                    str(annotations_path),
                    "--out-dir",
                    str(out_dir),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            bundle_exists = (out_dir / "export_bundle.json").is_file()
            alignment_exists = (out_dir / "alignment_report.json").is_file()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("alignment_status:", result.stdout)
        self.assertTrue(bundle_exists)
        self.assertTrue(alignment_exists)


if __name__ == "__main__":
    unittest.main()
