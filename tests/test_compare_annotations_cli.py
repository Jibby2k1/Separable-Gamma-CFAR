from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CompareAnnotationsCliTests(unittest.TestCase):
    def test_compare_annotations_writes_json_markdown_and_tsv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a.json"
            b = root / "b.json"
            out = root / "out"
            a.write_text(
                json.dumps(
                    {
                        "schema_version": 3,
                        "runs": {"baseline": {"rois": {"1": {"cell_state": "accepted", "reviewer_id": "RV"}}, "events": {}, "suggestions": {}}},
                    }
                ),
                encoding="utf-8",
            )
            b.write_text(
                json.dumps(
                    {
                        "schema_version": 3,
                        "runs": {"baseline": {"rois": {"1": {"cell_state": "rejected", "reviewer_id": "AB"}}, "events": {}, "suggestions": {}}},
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    str(ROOT / ".venv-neurobench/bin/python"),
                    str(ROOT / "tools/compare_annotations.py"),
                    "--annotations-a",
                    str(a),
                    "--annotations-b",
                    str(b),
                    "--reviewer-a",
                    "A",
                    "--reviewer-b",
                    "B",
                    "--run-id",
                    "baseline",
                    "--out-dir",
                    str(out),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            self.assertIn("disagreements: 1", result.stdout)
            report = json.loads((out / "agreement_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["reviewers"], ["A", "B"])
            self.assertEqual(len(report["disagreement_queue"]), 1)
            self.assertIn("Annotation Agreement Report", (out / "agreement_report.md").read_text(encoding="utf-8"))
            tsv = (out / "disagreement_queue.tsv").read_text(encoding="utf-8")
            self.assertIn("source_reviewer_id_a\tsource_reviewer_id_b", tsv)
            self.assertIn("accepted\trejected", tsv)
            self.assertIn("RV\tAB", tsv)

    def test_compare_annotations_can_fail_on_missing_reviewer_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a.json"
            b = root / "b.json"
            out = root / "out"
            a.write_text(json.dumps({"schema_version": 3, "rois": {"1": {"cell_state": "accepted"}}}), encoding="utf-8")
            b.write_text(json.dumps({"schema_version": 3, "rois": {"1": {"cell_state": "rejected", "reviewer_id": "AB"}}}), encoding="utf-8")

            result = subprocess.run(
                [
                    str(ROOT / ".venv-neurobench/bin/python"),
                    str(ROOT / "tools/compare_annotations.py"),
                    "--annotations-a",
                    str(a),
                    "--annotations-b",
                    str(b),
                    "--reviewer-a",
                    "A",
                    "--reviewer-b",
                    "B",
                    "--out-dir",
                    str(out),
                    "--require-reviewer-provenance",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            report_exists = (out / "agreement_report.json").is_file()

        self.assertEqual(result.returncode, 2)
        self.assertIn("missing reviewer provenance: 1", result.stdout)
        self.assertTrue(report_exists)


if __name__ == "__main__":
    unittest.main()
