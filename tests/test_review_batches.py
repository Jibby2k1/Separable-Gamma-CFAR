from __future__ import annotations

import unittest


class ReviewBatchTests(unittest.TestCase):
    def test_annotation_batch_prioritizes_unlabeled_supported_candidates(self):
        from neurobench.review_batches import build_annotation_batch, review_progress

        review_data = {
            "rois": [
                {
                    "id": 1,
                    "area": 50,
                    "priorityScore": 1.0,
                    "traceSnr": 2.0,
                    "localCorrelationMean": 0.5,
                    "eventSupport": 0.5,
                    "artifactScore": 0.1,
                    "events": [{"frame": 10, "z": 3.0, "amplitude": 0.2}],
                },
                {
                    "id": 2,
                    "area": 50,
                    "priorityScore": 3.0,
                    "traceSnr": 2.0,
                    "artifactScore": 0.1,
                    "events": [{"frame": 20, "z": 2.0}],
                },
                {
                    "id": 3,
                    "area": 20,
                    "priorityScore": 0.1,
                    "traceSnr": 0.5,
                    "artifactScore": 0.5,
                    "events": [],
                },
            ],
            "discovery": {
                "suggestions": [
                    {"id": "S1", "priorityScore": 2.0, "artifactCue": "none", "artifactScore": 0.1},
                    {"id": "S2", "priorityScore": 1.0, "artifactCue": "vessel", "artifactScore": 0.5},
                ]
            },
        }
        annotations = {
            "schema_version": 3,
            "rois": {"2": {"cell_state": "accepted", "state": "accept"}},
            "events": {"2:20": {"event_state": "accepted", "state": "accept"}},
            "suggestions": {},
        }

        batch = build_annotation_batch(review_data, annotations, target_rois=2, target_events=2, target_suggestions=2)
        progress = review_progress(review_data, annotations)

        self.assertEqual([item["roi_id"] for item in batch["rois"]], ["1", "3"])
        self.assertEqual(batch["events"][0]["roi_id"], "1")
        self.assertEqual(batch["events"][0]["frame"], 10)
        self.assertEqual([item["suggestion_id"] for item in batch["suggestions"]], ["S1", "S2"])
        self.assertEqual(progress["reviewed_rois"], 1)
        self.assertEqual(progress["reviewed_events"], 1)
        self.assertFalse(progress["tuning_ready"])

    def test_annotation_summary_includes_progress_and_next_batch(self):
        from neurobench.annotation_metrics import compute_annotation_summary

        review_data = {
            "rois": [
                {"id": 1, "area": 50, "traceSnr": 2.0, "events": [{"frame": 10, "z": 3.0}]},
                {"id": 2, "area": 50, "traceSnr": 2.0, "events": []},
            ],
            "discovery": {"suggestions": [{"id": "S1", "priorityScore": 1.0}]},
        }
        summary = compute_annotation_summary(review_data, {"schema_version": 3})

        self.assertIn("review_progress", summary)
        self.assertIn("next_annotation_batch", summary)
        self.assertEqual(summary["review_progress"]["reviewed_rois"], 0)
        self.assertEqual(summary["next_annotation_batch"]["rois"][0]["roi_id"], "1")
        self.assertIn("roi", {task["task_type"] for task in summary["next_annotation_batch"]["tasks"]})

    def test_review_task_feature_rows_support_active_learning_exports(self):
        from neurobench.review_batches import review_task_feature_rows

        rows = review_task_feature_rows(
            {
                "rois": [{"id": 1, "area": 50, "traceSnr": 2.0, "events": []}],
                "discovery": {"suggestions": [{"id": "S1", "priorityScore": 1.0}]},
            },
            {"schema_version": 3, "rois": {"1": {"cell_state": "accepted"}}},
        )

        self.assertEqual([row["subject_type"] for row in rows], ["roi", "suggestion"])
        self.assertEqual(rows[0]["label_state"], "accepted")
        self.assertIn("priority_score", rows[0])


class SweepPackAndReportTests(unittest.TestCase):
    def test_sweep_pack_contains_grouped_planned_runs(self):
        from neurobench.sweep_packs import build_sweep_pack

        pack = build_sweep_pack(dataset_id="rest", pack_id="pack")

        self.assertEqual(pack["dataset_id"], "rest")
        self.assertEqual(len(pack["runs"]), 5)
        self.assertTrue(all(run["execution"]["status"] == "planned" for run in pack["runs"]))
        self.assertEqual(pack["runs"][0]["review_pack"]["pack_id"], "pack")

    def test_review_report_markdown_summarizes_progress(self):
        from neurobench.review_reports import build_review_report, render_review_report_markdown

        report = build_review_report(
            {"dataset": {"dataset_id": "rest"}, "rois": [{"id": 1, "events": [{"frame": 4, "z": 3.0}]}]},
            {"schema_version": 3},
        )
        markdown = render_review_report_markdown(report)

        self.assertIn("Neuron Workbench Review Report: rest", markdown)
        self.assertIn("Reviewed ROIs", markdown)
        self.assertIn("ROI 1", markdown)


if __name__ == "__main__":
    unittest.main()
