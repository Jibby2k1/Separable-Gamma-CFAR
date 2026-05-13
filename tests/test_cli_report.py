from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _pipeline_run_payload(run_id: str, *, recall: float = 1.0, duration: float = 12.0) -> dict:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "dataset_id": "cli_report_dataset",
        "pipeline_spec_id": "spec_cli_report",
        "status": "completed",
        "created_at": "2026-05-13T00:00:00+00:00",
        "completed_at": f"2026-05-13T00:00:{int(duration):02d}+00:00",
        "parameter_hash": f"hash_{run_id}",
        "environment": {"device": "cpu"},
        "code": {"git_commit": "abc123"},
        "artifacts": [
            {
                "schema_version": 1,
                "artifact_id": "candidate_events.v1",
                "kind": "candidate_events",
                "path": f"artifacts/{run_id}/events.json",
                "producer_stage": "unit_test",
                "sha256": "abc123",
            }
        ],
        "metrics": {
            "object_level": {"object_recall": recall, "object_precision": 0.8, "accepted_candidate_ids": ["1", run_id]},
            "event_level": {"event_recall": recall, "event_precision": 0.5},
            "runtime": {},
        },
        "warnings": [],
        "logs": ["logs/run.log"],
    }


class CliReportTests(unittest.TestCase):
    def test_cli_report_generate_writes_metrics_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_path = root / "pipeline_run.json"
            out_dir = root / "report"
            run_path.write_text(json.dumps(_pipeline_run_payload("run_a")), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "neurobench.cli.main",
                    "report",
                    "generate",
                    str(run_path),
                    "--output",
                    str(out_dir),
                    "--metrics-report-id",
                    "metrics_cli",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            metrics = json.loads((out_dir / "metrics_report.json").read_text(encoding="utf-8"))
            markdown = (out_dir / "report.md").read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Metrics report JSON", result.stdout)
        self.assertEqual(metrics["metrics_report_id"], "metrics_cli")
        self.assertEqual(metrics["run_ids"], ["run_a"])
        self.assertIn("# Neurobench Metrics Report: cli_report_dataset", markdown)

    def test_cli_report_compare_writes_comparison_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_a = root / "run_a.json"
            run_b = root / "run_b.json"
            out_dir = root / "comparison"
            run_a.write_text(json.dumps(_pipeline_run_payload("run_a", recall=0.8, duration=12.0)), encoding="utf-8")
            run_b.write_text(json.dumps(_pipeline_run_payload("run_b", recall=1.0, duration=8.0)), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "neurobench.cli.main",
                    "report",
                    "compare",
                    str(run_a),
                    str(run_b),
                    "--output",
                    str(out_dir),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            comparison = json.loads((out_dir / "comparison_report.json").read_text(encoding="utf-8"))
            markdown = (out_dir / "comparison_report.md").read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(comparison["run_count"], 2)
        self.assertEqual(comparison["best_by_metric"]["object_level.object_recall"]["run_id"], "run_b")
        self.assertIn("# Neurobench Run Comparison", markdown)

    def test_cli_report_compare_requires_two_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_path = root / "pipeline_run.json"
            run_path.write_text(json.dumps(_pipeline_run_payload("run_a")), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "neurobench.cli.main",
                    "report",
                    "compare",
                    str(run_path),
                    "--output",
                    str(root / "comparison"),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("requires at least two", result.stderr)


if __name__ == "__main__":
    unittest.main()
