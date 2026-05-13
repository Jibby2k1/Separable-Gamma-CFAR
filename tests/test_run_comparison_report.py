from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


def _report(run_id: str, *, recall: float, precision: float, event_recall: float, duration: float, accepted: list[str], warnings: list[str] | None = None) -> dict:
    return {
        "schema_version": 1,
        "metrics_report_id": f"metrics_{run_id}",
        "dataset_id": "synthetic_neurobench",
        "run_ids": [run_id],
        "created_at": "2026-05-13T00:00:00Z",
        "metrics": {
            "object_level": {
                "object_recall": recall,
                "object_precision": precision,
                "accepted_candidate_ids": accepted,
            },
            "event_level": {"event_recall": event_recall, "event_precision": 0.5},
            "pixel_level": {"truncated_auc": 0.5 + recall / 10},
            "annotation": {},
            "runtime": {"duration_seconds": duration},
        },
        "figures": [],
        "warnings": warnings or [],
        "provenance": {"pipeline_run_paths": [f"{run_id}/pipeline_run.json"]},
    }


class RunComparisonReportTests(unittest.TestCase):
    def test_build_run_comparison_report_ranks_metrics_and_candidates(self):
        from neurobench.reports.comparison import build_run_comparison_report

        comparison = build_run_comparison_report(
            [
                _report("run_a", recall=0.8, precision=0.9, event_recall=0.6, duration=12.0, accepted=["1", "2", "3"]),
                _report("run_b", recall=1.0, precision=0.7, event_recall=0.9, duration=8.0, accepted=["2", "3", "4"], warnings=["high FP burden"]),
            ]
        )

        self.assertEqual(comparison["run_count"], 2)
        self.assertEqual(comparison["best_by_metric"]["object_level.object_recall"]["run_id"], "run_b")
        self.assertEqual(comparison["best_by_metric"]["object_level.object_precision"]["run_id"], "run_a")
        self.assertEqual(comparison["best_by_metric"]["runtime.duration_seconds"]["run_id"], "run_b")
        self.assertEqual(comparison["candidate_consensus"]["consensus_accepted_candidate_ids"], ["2", "3"])
        self.assertEqual(comparison["candidate_consensus"]["unique_accepted_candidate_ids"], ["1", "4"])
        self.assertEqual(comparison["warnings"][0]["run_id"], "run_b")

    def test_run_comparison_markdown_contains_table_winners_and_warnings(self):
        from neurobench.reports.comparison import build_run_comparison_report, render_run_comparison_markdown

        comparison = build_run_comparison_report(
            [
                _report("run_a", recall=0.8, precision=0.9, event_recall=0.6, duration=12.0, accepted=["1", "2"]),
                _report("run_b", recall=1.0, precision=0.7, event_recall=0.9, duration=8.0, accepted=["2", "3"], warnings=["high FP burden"]),
            ]
        )
        markdown = render_run_comparison_markdown(comparison)

        self.assertIn("# Neurobench Run Comparison", markdown)
        self.assertIn("| `run_a` |", markdown)
        self.assertIn("- object level.object recall: `run_b` (1)", markdown)
        self.assertIn("- Consensus accepted candidates: 1", markdown)
        self.assertIn("`run_b`: high FP burden", markdown)

    def test_write_run_comparison_markdown_roundtrip(self):
        from neurobench.reports.comparison import build_run_comparison_report, render_run_comparison_markdown, write_run_comparison_markdown

        comparison = build_run_comparison_report(
            [_report("run_a", recall=0.8, precision=0.9, event_recall=0.6, duration=12.0, accepted=[])]
        )
        with tempfile.TemporaryDirectory() as tmp:
            out = write_run_comparison_markdown(comparison, Path(tmp) / "comparison_report.md")
            text = out.read_text(encoding="utf-8")

        self.assertEqual(text, render_run_comparison_markdown(comparison))


if __name__ == "__main__":
    unittest.main()
