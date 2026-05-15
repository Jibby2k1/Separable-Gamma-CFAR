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
        "dataset": {"dataset_id": "resting"},
        "video": {"width": 8, "height": 8, "frames": 4, "framePattern": "frame_%04d.png"},
        "parameters": {},
        "rois": [
            {"id": 1, "events": [{"frame": 4}, {"frame": 8}]},
            {"id": 2, "events": [{"frame": 5}]},
            {"id": 3, "events": []},
        ],
    }


def _annotations() -> dict:
    return {
        "schema_version": 3,
        "rois": {
            "1": {"cell_state": "accepted", "confidence": "high", "reason_tags": ["compact"]},
            "2": {"cell_state": "rejected", "confidence": "high", "reason_tags": ["vessel"]},
            "3": {"cell_state": "unsure", "confidence": "low", "reason_tags": ["weak"]},
        },
        "events": {
            "1:4": {"event_state": "accepted", "confidence": "medium", "reason_tags": ["clear_onset"]},
            "1:8": {"event_state": "rejected", "confidence": "high", "reason_tags": ["noise"]},
            "2:5": {"event_state": "accepted", "confidence": "high", "reason_tags": ["clear_onset"]},
        },
        "virtualRois": {
            "V1": {
                "id": "V1",
                "roi_kind": "virtual_merge",
                "source_roi_ids": [1, 3],
                "cell_state": "accepted",
                "confidence": "medium",
                "reason_tags": ["merge"],
            },
            "MR_1": {
                "id": "MR_1",
                "roi_kind": "manual_circle",
                "source_roi_ids": [],
                "cell_state": "accepted",
                "confidence": "medium",
                "reason_tags": ["manual"],
                "needs_action": "",
                "centroidX": 4.0,
                "centroidY": 4.0,
                "area": 12,
                "points": [[4, 4]],
            }
        },
        "splitMergeDecisions": {
            "SM_merge_1_3": {
                "id": "SM_merge_1_3",
                "decision_type": "merge",
                "decision_state": "accepted",
                "source_roi_ids": [1, 3],
                "virtual_roi_id": "V1",
                "identity_group": "group_1_3",
                "needs_action": "merge_needed",
                "confidence": "medium",
                "reason_tags": ["merge"],
            },
            "SM_split_2": {
                "id": "SM_split_2",
                "decision_type": "split",
                "decision_state": "unsure",
                "source_roi_ids": [2],
                "target_roi_ids": ["2a", "2b"],
                "needs_action": "split_needed",
                "confidence": "low",
                "reason_tags": ["split"],
            },
        },
    }


class AnnotationExportTests(unittest.TestCase):
    def test_accepted_only_profile_exports_only_accepted_rois_and_parent_accepted_events(self):
        from neurobench.exports.annotations import export_annotation_profile

        with tempfile.TemporaryDirectory() as tmp:
            bundle = export_annotation_profile(_review_data(), _annotations(), tmp, profile="accepted_only", created_at="2026-05-13T00:00:00Z")
            root = Path(tmp)
            roi_tsv = (root / "accepted_rois.tsv").read_text(encoding="utf-8")
            event_tsv = (root / "accepted_events.tsv").read_text(encoding="utf-8")
            split_merge_tsv = (root / "split_merge_decisions.tsv").read_text(encoding="utf-8")
            manifest = json.loads((root / "export_bundle.json").read_text(encoding="utf-8"))

        self.assertEqual(bundle.profile, "accepted_only")
        self.assertEqual(bundle.selection_policy["name"], "accepted_only")
        self.assertIn("\n1\tsource\t\taccepted", roi_tsv)
        self.assertIn("\nV1\tvirtual_merge\t1,3\taccepted", roi_tsv)
        self.assertIn("\nMR_1\tmanual_circle\t\taccepted", roi_tsv)
        self.assertIn("\tmedium\tmanual\t", roi_tsv)
        self.assertNotIn("MR_1\tmanual_circle\t\taccepted\t\t\t\t\tmerge_needed", roi_tsv)
        self.assertNotIn("\n2\tsource", roi_tsv)
        self.assertNotIn("\n3\tsource", roi_tsv)
        self.assertIn("\n1\t4\taccepted", event_tsv)
        self.assertNotIn("\n1\t8\trejected", event_tsv)
        self.assertNotIn("\n2\t5\taccepted", event_tsv)
        self.assertIn("\nSM_merge_1_3\tmerge\taccepted\t1,3\t\tV1", split_merge_tsv)
        self.assertNotIn("SM_split_2", split_merge_tsv)
        self.assertEqual(manifest["alignment_status"], "not_provided")
        self.assertEqual(manifest["selection_policy"]["include_rois"], "accepted")
        self.assertEqual(
            {item["path"] for item in manifest["files"]},
            {"annotations_v3.json", "accepted_rois.tsv", "accepted_events.tsv", "neuron_metadata.tsv", "split_merge_decisions.tsv"},
        )

    def test_all_reviewed_profile_exports_reviewed_rejected_and_unsure_rows(self):
        from neurobench.exports.annotations import export_annotation_profile

        with tempfile.TemporaryDirectory() as tmp:
            export_annotation_profile(_review_data(), _annotations(), tmp, profile="all_reviewed", created_at="2026-05-13T00:00:00Z")
            root = Path(tmp)
            roi_tsv = (root / "reviewed_rois.tsv").read_text(encoding="utf-8")
            event_tsv = (root / "reviewed_events.tsv").read_text(encoding="utf-8")
            split_merge_tsv = (root / "split_merge_decisions.tsv").read_text(encoding="utf-8")
            manifest = json.loads((root / "export_bundle.json").read_text(encoding="utf-8"))

        self.assertIn("\n1\tsource\t\taccepted", roi_tsv)
        self.assertIn("\n2\tsource\t\trejected", roi_tsv)
        self.assertIn("\n3\tsource\t\tunsure", roi_tsv)
        self.assertIn("\n1\t8\trejected", event_tsv)
        self.assertIn("\n2\t5\taccepted", event_tsv)
        self.assertIn("\nSM_split_2\tsplit\tunsure\t2\t2a,2b\t", split_merge_tsv)
        self.assertEqual(manifest["profile"], "all_reviewed")
        self.assertTrue(manifest["warnings"])

    def test_all_candidates_profile_includes_unlabeled_rows(self):
        from neurobench.exports.annotations import export_annotation_profile

        review = _review_data()
        annotations = _annotations()
        annotations["rois"].pop("3")
        with tempfile.TemporaryDirectory() as tmp:
            export_annotation_profile(review, annotations, tmp, profile="all_candidates", created_at="2026-05-13T00:00:00Z")
            roi_tsv = (Path(tmp) / "candidate_rois.tsv").read_text(encoding="utf-8")

        self.assertIn("\n3\tsource\t\t", roi_tsv)

    def test_export_annotation_profile_rejects_unknown_profile(self):
        from neurobench.exports.annotations import export_annotation_profile

        with self.assertRaisesRegex(ValueError, "Unknown annotation export profile"):
            export_annotation_profile(_review_data(), _annotations(), "/tmp/unused", profile="missing")

    def test_legacy_export_annotations_script_accepts_profile_argument(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review_path = root / "review_data.json"
            annotations_path = root / "annotations.json"
            out_dir = root / "exports"
            review_path.write_text(json.dumps(_review_data()), encoding="utf-8")
            annotations_path.write_text(json.dumps(_annotations()), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "tools/export_annotations.py",
                    "--review-data",
                    str(review_path),
                    "--annotations",
                    str(annotations_path),
                    "--out-dir",
                    str(out_dir),
                    "--profile",
                    "all_reviewed",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            reviewed_exists = (out_dir / "reviewed_rois.tsv").is_file()
            bundle_exists = (out_dir / "export_bundle.json").is_file()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Wrote all_reviewed annotation export", result.stdout)
        self.assertTrue(reviewed_exists)
        self.assertTrue(bundle_exists)


if __name__ == "__main__":
    unittest.main()
