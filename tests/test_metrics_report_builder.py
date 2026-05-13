from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


def _artifact_payload(kind: str = "candidate_events") -> dict:
    return {
        "schema_version": 1,
        "artifact_id": f"{kind}.v1",
        "kind": kind,
        "path": f"artifacts/{kind}.json",
        "schema": None,
        "producer_stage": "unit_test",
        "created_at": "2026-05-13T00:00:00Z",
        "sha256": "abc123",
        "summary": {"count": 2},
    }


def _run_payload(run_id: str = "run_001", *, status: str = "completed", warnings: list[str] | None = None) -> dict:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "dataset_id": "dataset_001",
        "pipeline_spec_id": "spec_001",
        "status": status,
        "created_at": "2026-05-13T00:00:00+00:00",
        "completed_at": "2026-05-13T00:00:12+00:00",
        "parameter_hash": f"hash_{run_id}",
        "environment": {"device": "cpu"},
        "code": {"git_commit": "abcdef"},
        "artifacts": [_artifact_payload()],
        "metrics": {
            "object_level": {"object_recall": 1.0},
            "event_level": {"event_precision": 0.5},
        },
        "warnings": warnings or [],
        "logs": ["logs/run.log"],
    }


class MetricsReportBuilderTests(unittest.TestCase):
    def test_build_metrics_report_from_single_pipeline_run_path(self):
        from neurobench.models.pipeline import PipelineRun
        from neurobench.reports.builder import build_metrics_report_from_pipeline_run

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pipeline_run.json"
            PipelineRun.from_dict(_run_payload(warnings=["synthetic warning"])).write_json(path)

            report = build_metrics_report_from_pipeline_run(
                path,
                metrics_report_id="metrics_unit",
                created_at="2026-05-13T00:01:00Z",
            )

        self.assertEqual(report.metrics_report_id, "metrics_unit")
        self.assertEqual(report.run_ids, ["run_001"])
        self.assertEqual(report.metrics["object_level"]["object_recall"], 1.0)
        self.assertEqual(report.metrics["event_level"]["event_precision"], 0.5)
        self.assertEqual(report.metrics["runtime"]["duration_seconds"], 12.0)
        self.assertEqual(report.metrics["runtime"]["artifact_count"], 1)
        self.assertEqual(report.warnings, ["run_001: synthetic warning"])
        self.assertIn("pipeline_run.json", report.provenance["pipeline_run_paths"][0])
        self.assertEqual(report.provenance["artifact_paths"], ["artifacts/candidate_events.json"])
        report.validate()

    def test_build_metrics_report_from_multiple_pipeline_runs_keeps_by_run_metrics(self):
        from neurobench.models.pipeline import PipelineRun
        from neurobench.reports.builder import build_metrics_report_from_pipeline_runs

        run_a = PipelineRun.from_dict(_run_payload("run_a"))
        run_b = PipelineRun.from_dict(_run_payload("run_b", status="failed", warnings=["failed on fixture"]))

        report = build_metrics_report_from_pipeline_runs(
            [run_a, run_b],
            created_at="2026-05-13T00:01:00Z",
        )

        self.assertEqual(report.run_ids, ["run_a", "run_b"])
        self.assertEqual(report.metrics["runtime"]["run_count"], 2)
        self.assertEqual(report.metrics["runtime"]["completed_count"], 1)
        self.assertEqual(report.metrics["runtime"]["failed_count"], 1)
        self.assertEqual(report.metrics["by_run"]["run_a"]["runtime"]["duration_seconds"], 12.0)
        self.assertEqual(report.provenance["parameter_hashes"]["run_b"], "hash_run_b")
        self.assertEqual(report.warnings, ["run_b: failed on fixture"])
        report.validate()

    def test_pipeline_run_report_can_render_to_markdown(self):
        from neurobench.models.pipeline import PipelineRun
        from neurobench.reports.builder import build_metrics_report_from_pipeline_run
        from neurobench.reports.render import render_metrics_report_markdown

        report = build_metrics_report_from_pipeline_run(
            PipelineRun.from_dict(_run_payload()),
            created_at="2026-05-13T00:01:00Z",
        )
        markdown = render_metrics_report_markdown(report)

        self.assertIn("# Neurobench Metrics Report: dataset_001", markdown)
        self.assertIn("- duration seconds: 12", markdown)
        self.assertIn("artifacts/candidate_events.json", markdown)


if __name__ == "__main__":
    unittest.main()
