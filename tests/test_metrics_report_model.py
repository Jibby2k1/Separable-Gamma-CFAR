from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import jsonschema


def _metrics_report_payload() -> dict:
    return {
        "schema_version": 1,
        "metrics_report_id": "metrics_run_001",
        "dataset_id": "synthetic_neurobench",
        "run_ids": ["run_001"],
        "created_at": "2026-05-13T00:00:00Z",
        "metrics": {
            "pixel_level": {"truncated_auc": 0.75},
            "object_level": {"object_precision": 0.8, "object_recall": 1.0},
            "event_level": {"event_precision": 0.5, "event_recall": 1.0},
            "annotation": {"reviewed_rois": 10},
            "runtime": {"duration_seconds": 12.5},
        },
        "figures": [{"path": "figures/froc.png", "caption": "FROC curve", "kind": "plot"}],
        "warnings": ["Synthetic fixture; not biological validation."],
        "provenance": {
            "pipeline_run_paths": ["pipeline_run.json"],
            "annotation_paths": ["annotations.json"],
            "code": {"git_commit": "abc123"},
            "environment": {"device": "cpu"},
        },
    }


class MetricsReportModelTests(unittest.TestCase):
    def test_metrics_report_schema_and_roundtrip(self):
        from neurobench.models.metrics import MetricsReport

        report = MetricsReport.from_dict(_metrics_report_payload())

        self.assertEqual(report.metrics_report_id, "metrics_run_001")
        self.assertEqual(report.dataset_id, "synthetic_neurobench")
        self.assertEqual(report.metrics["object_level"]["object_recall"], 1.0)
        self.assertEqual(report.to_dict(), _metrics_report_payload())
        report.validate()

    def test_metrics_report_write_json_roundtrip(self):
        from neurobench.models.metrics import MetricsReport

        report = MetricsReport.from_dict(_metrics_report_payload())
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "metrics_report.json"
            report.write_json(out)

            self.assertEqual(MetricsReport.load_json(out).to_dict(), _metrics_report_payload())

    def test_metrics_report_defaults_metric_sections(self):
        from neurobench.models.metrics import MetricsReport

        payload = _metrics_report_payload()
        payload["metrics"] = {"object_level": {"object_precision": 1.0}}

        report = MetricsReport.from_dict(payload)

        for section in ("pixel_level", "object_level", "event_level", "annotation", "runtime"):
            self.assertIn(section, report.metrics)
        self.assertEqual(report.metrics["object_level"]["object_precision"], 1.0)

    def test_metrics_report_preserves_extra_metadata(self):
        from neurobench.models.metrics import MetricsReport

        payload = _metrics_report_payload()
        payload["review_context"] = {"reviewer": "lab"}

        report = MetricsReport.from_dict(payload)

        self.assertEqual(report.extras["review_context"], {"reviewer": "lab"})
        self.assertEqual(report.to_dict()["extras"]["review_context"], {"reviewer": "lab"})

    def test_invalid_metrics_report_rejects_empty_run_id(self):
        from neurobench.models.metrics import MetricsReport

        payload = _metrics_report_payload()
        payload["run_ids"] = [""]
        report = MetricsReport.from_dict(payload)

        with self.assertRaises(jsonschema.ValidationError) as ctx:
            report.validate()

        self.assertIn("should be", ctx.exception.message)


if __name__ == "__main__":
    unittest.main()
