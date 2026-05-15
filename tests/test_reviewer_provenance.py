from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReviewerProvenanceTests(unittest.TestCase):
    def test_backfill_reviewer_ids_stamps_only_reviewed_missing_items(self) -> None:
        from neurobench.review.provenance import backfill_reviewer_ids

        payload = backfill_reviewer_ids(
            {
                "rois": {
                    "1": {"cell_state": "accepted"},
                    "2": {},
                    "3": {"cell_state": "rejected", "reviewer_id": "AB"},
                },
                "events": {"1:4": {"event_state": "accepted"}},
                "suggestions": {"S1": {"state": "missed"}, "S2": {}},
                "splitMergeDecisions": {"D1": {"decision_type": "merge", "decision_state": "accepted"}},
            },
            "RV",
            updated_at="2026-05-14T00:00:00Z",
        )

        self.assertEqual(payload["rois"]["1"]["reviewer_id"], "RV")
        self.assertNotIn("reviewer_id", payload["rois"]["2"])
        self.assertEqual(payload["rois"]["3"]["reviewer_id"], "AB")
        self.assertEqual(payload["events"]["1:4"]["reviewer_id"], "RV")
        self.assertEqual(payload["suggestions"]["S1"]["updatedAt"], "2026-05-14T00:00:00Z")
        self.assertEqual(payload["splitMergeDecisions"]["D1"]["reviewer_id"], "RV")
        self.assertEqual(payload["reviewer_provenance_backfill"]["stamped_total"], 4)

    def test_backfill_reviewer_ids_can_target_run_scope_and_overwrite(self) -> None:
        from neurobench.review.provenance import backfill_reviewer_ids

        payload = backfill_reviewer_ids(
            {
                "runs": {
                    "baseline": {"rois": {"1": {"cell_state": "accepted", "reviewer_id": "AB"}}},
                    "strict": {"rois": {"2": {"cell_state": "accepted"}}},
                }
            },
            "RV",
            run_id="baseline",
            overwrite=True,
            updated_at="2026-05-14T00:00:00Z",
        )

        self.assertEqual(payload["runs"]["baseline"]["rois"]["1"]["reviewer_id"], "RV")
        self.assertNotIn("reviewer_id", payload["runs"]["strict"]["rois"]["2"])
        self.assertIn("runs.baseline", payload["reviewer_provenance_backfill"]["scopes"])

    def test_cli_writes_backfilled_annotations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "annotations.json"
            out = root / "out.json"
            src.write_text(json.dumps({"rois": {"1": {"cell_state": "accepted"}}}), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/backfill_reviewer_ids.py"),
                    "--annotations",
                    str(src),
                    "--reviewer-id",
                    "RV",
                    "--out",
                    str(out),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            payload = json.loads(out.read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("stamped: 1", result.stdout)
        self.assertEqual(payload["rois"]["1"]["reviewer_id"], "RV")

    def test_cli_dry_run_writes_summary_without_annotation_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "annotations.json"
            summary_path = root / "summary.json"
            src.write_text(json.dumps({"rois": {"1": {"cell_state": "accepted"}}}), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/backfill_reviewer_ids.py"),
                    "--annotations",
                    str(src),
                    "--reviewer-id",
                    "RV",
                    "--dry-run",
                    "--summary-json",
                    str(summary_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            original = json.loads(src.read_text(encoding="utf-8"))
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Dry run: no annotation file written", result.stdout)
        self.assertNotIn("reviewer_id", original["rois"]["1"])
        self.assertEqual(summary["stamped_total"], 1)

    def test_cli_rejects_dry_run_with_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "annotations.json"
            src.write_text(json.dumps({"rois": {}}), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/backfill_reviewer_ids.py"),
                    "--annotations",
                    str(src),
                    "--reviewer-id",
                    "RV",
                    "--dry-run",
                    "--out",
                    str(root / "out.json"),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--dry-run cannot be combined", result.stderr)

    def test_reviewer_provenance_summary_counts_missing_and_present_reviewers(self) -> None:
        from neurobench.review.provenance import reviewer_provenance_summary

        summary = reviewer_provenance_summary(
            {
                "rois": {
                    "1": {"cell_state": "accepted", "reviewer_id": "RV"},
                    "2": {"cell_state": "rejected"},
                    "3": {},
                },
                "events": {"1:4": {"event_state": "accepted", "reviewer_id": "RV"}},
            }
        )

        self.assertEqual(summary["reviewed_total"], 3)
        self.assertEqual(summary["with_reviewer_total"], 2)
        self.assertEqual(summary["missing_reviewer_total"], 1)
        self.assertEqual(summary["reviewers"], {"RV": 2})

    def test_cli_audit_only_does_not_require_reviewer_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "annotations.json"
            summary_path = root / "audit.json"
            src.write_text(json.dumps({"rois": {"1": {"cell_state": "accepted"}}}), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/backfill_reviewer_ids.py"),
                    "--annotations",
                    str(src),
                    "--audit-only",
                    "--summary-json",
                    str(summary_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Audit only: no annotation file written", result.stdout)
        self.assertEqual(summary["missing_reviewer_total"], 1)


if __name__ == "__main__":
    unittest.main()
