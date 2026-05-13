from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


def _report_payload() -> dict:
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


class MetricsReportRenderTests(unittest.TestCase):
    def test_metrics_report_markdown_contains_core_sections(self):
        from neurobench.reports.render import render_metrics_report_markdown

        markdown = render_metrics_report_markdown(_report_payload())

        self.assertIn("# Neurobench Metrics Report: synthetic_neurobench", markdown)
        self.assertIn("### Pixel-Level Metrics", markdown)
        self.assertIn("### Object-Level Metrics", markdown)
        self.assertIn("### Event-Level Metrics", markdown)
        self.assertIn("### Annotation Metrics", markdown)
        self.assertIn("### Runtime Metrics", markdown)
        self.assertIn("- object recall: 1", markdown)
        self.assertIn("## Warnings and Limitations", markdown)
        self.assertIn("Synthetic fixture; not biological validation.", markdown)
        self.assertIn("### Reproducibility Appendix", markdown)
        self.assertIn("pipeline_run.json", markdown)

    def test_metrics_report_markdown_accepts_model_instance_and_empty_sections(self):
        from neurobench.models.metrics import MetricsReport
        from neurobench.reports.render import render_metrics_report_markdown

        payload = _report_payload()
        payload["metrics"] = {"object_level": {"object_precision": 1.0}}
        payload["figures"] = []
        payload["warnings"] = []
        report = MetricsReport.from_dict(payload)

        markdown = render_metrics_report_markdown(report)

        self.assertIn("- object precision: 1", markdown)
        self.assertIn("No figures reported.", markdown)
        self.assertIn("No warnings reported.", markdown)
        self.assertIn("### Event-Level Metrics\n\nNo values reported.", markdown)

    def test_write_metrics_report_markdown_roundtrip(self):
        from neurobench.reports.render import render_metrics_report_markdown, write_metrics_report_markdown

        with tempfile.TemporaryDirectory() as tmp:
            out = write_metrics_report_markdown(_report_payload(), Path(tmp) / "report.md")
            text = out.read_text(encoding="utf-8")

        self.assertEqual(text, render_metrics_report_markdown(_report_payload()))

    def test_metrics_report_html_contains_core_sections_from_same_model(self):
        from neurobench.models.metrics import MetricsReport
        from neurobench.reports.render import render_metrics_report_html

        report = MetricsReport.from_dict(_report_payload())

        html = render_metrics_report_html(report)

        self.assertIn("<!doctype html>", html)
        self.assertIn("<title>Neurobench Metrics Report: synthetic_neurobench</title>", html)
        self.assertIn("<h1>Neurobench Metrics Report: synthetic_neurobench</h1>", html)
        self.assertIn('<h2 id="report-metadata">Report Metadata</h2>', html)
        self.assertIn('<h2 id="metrics">Metrics</h2>', html)
        self.assertIn('<h3 id="pixel-level-metrics">Pixel-Level Metrics</h3>', html)
        self.assertIn('<h3 id="object-level-metrics">Object-Level Metrics</h3>', html)
        self.assertIn('<h3 id="event-level-metrics">Event-Level Metrics</h3>', html)
        self.assertIn('<h3 id="annotation-metrics">Annotation Metrics</h3>', html)
        self.assertIn('<h3 id="runtime-metrics">Runtime Metrics</h3>', html)
        self.assertIn("<th>object recall</th><td>1</td>", html)
        self.assertIn('<h2 id="warnings-and-limitations">Warnings and Limitations</h2>', html)
        self.assertIn("Synthetic fixture; not biological validation.", html)
        self.assertIn('<h2 id="reproducibility-appendix">Reproducibility Appendix</h2>', html)
        self.assertIn("<code>pipeline_run.json</code>", html)

    def test_metrics_report_html_accepts_empty_sections_and_escapes_values(self):
        from neurobench.reports.render import render_metrics_report_html

        payload = _report_payload()
        payload["dataset_id"] = "fish <alpha>"
        payload["metrics_report_id"] = "metrics_<001>"
        payload["run_ids"] = ["run_<001>"]
        payload["metrics"] = {"object_level": {"object_precision": 1.0, "note": "<script>alert(1)</script>"}}
        payload["figures"] = [{"path": "figures/<froc>.png", "caption": "FROC <curve>"}]
        payload["warnings"] = ["Synthetic <warning>"]

        html = render_metrics_report_html(payload)

        self.assertIn("Neurobench Metrics Report: fish &lt;alpha&gt;", html)
        self.assertIn("<code>metrics_&lt;001&gt;</code>", html)
        self.assertIn("<code>run_&lt;001&gt;</code>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("<code>figures/&lt;froc&gt;.png</code>: FROC &lt;curve&gt;", html)
        self.assertIn("Synthetic &lt;warning&gt;", html)
        self.assertIn('<p class="empty">No values reported.</p>', html)

    def test_write_metrics_report_html_roundtrip(self):
        from neurobench.reports.render import render_metrics_report_html, write_metrics_report_html

        with tempfile.TemporaryDirectory() as tmp:
            out = write_metrics_report_html(_report_payload(), Path(tmp) / "report.html")
            text = out.read_text(encoding="utf-8")

        self.assertEqual(text, render_metrics_report_html(_report_payload()))


if __name__ == "__main__":
    unittest.main()
