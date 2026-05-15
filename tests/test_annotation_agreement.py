from __future__ import annotations

import unittest


class AnnotationAgreementTests(unittest.TestCase):
    def test_binary_cohen_kappa_handles_perfect_and_partial_agreement(self):
        from neurobench.review.agreement import binary_cohen_kappa

        perfect = binary_cohen_kappa([True, False, True], [True, False, True])
        partial = binary_cohen_kappa([True, True, False, False], [True, False, False, False])

        self.assertEqual(perfect["kappa"], 1.0)
        self.assertEqual(perfect["observed_agreement"], 1.0)
        self.assertAlmostEqual(partial["observed_agreement"], 0.75)
        self.assertAlmostEqual(partial["expected_agreement"], 0.5)
        self.assertAlmostEqual(partial["kappa"], 0.5)

    def test_disagreement_queue_includes_missing_and_conflicting_event_labels(self):
        from neurobench.review.agreement import disagreement_queue

        reviewer_a = {"events": {"1:4": {"event_state": "accepted"}, "1:9": {"event_state": "unsure"}}}
        reviewer_b = {"events": {"1:4": {"event_state": "rejected"}, "2:5": {"event_state": "accepted"}}}

        queue = disagreement_queue(reviewer_a, reviewer_b, subject_groups=("events",))

        self.assertEqual([item["subject_id"] for item in queue], ["1:4", "1:9", "2:5"])
        self.assertEqual(queue[0]["label_a"], "accepted")
        self.assertEqual(queue[0]["label_b"], "rejected")

    def test_annotation_agreement_report_compares_roi_event_and_suggestion_labels(self):
        from neurobench.review.agreement import annotation_agreement_report

        reviewer_a = {
            "schema_version": 3,
            "rois": {
                "1": {"cell_state": "accepted", "confidence": "high"},
                "2": {"cell_state": "rejected", "artifact_class": "vessel", "confidence": "medium"},
                "3": {"cell_state": "accepted", "confidence": "low"},
            },
            "events": {
                "1:4": {"event_state": "accepted", "confidence": "high"},
                "1:9": {"event_state": "rejected", "confidence": "medium"},
            },
            "suggestions": {"S1": {"state": "missed", "confidence": "high"}},
            "settings": {},
        }
        reviewer_b = {
            "schema_version": 3,
            "rois": {
                "1": {"cell_state": "accepted", "confidence": "high"},
                "2": {"cell_state": "accepted", "artifact_class": "vessel", "confidence": "low"},
                "4": {"cell_state": "rejected", "confidence": "medium"},
            },
            "events": {
                "1:4": {"event_state": "accepted", "confidence": "medium"},
                "1:9": {"event_state": "rejected", "confidence": "medium"},
            },
            "suggestions": {"S1": {"state": "artifact", "confidence": "low"}},
            "settings": {},
        }

        report = annotation_agreement_report(reviewer_a, reviewer_b, reviewer_a_id="A", reviewer_b_id="B")

        self.assertEqual(report["reviewers"], ["A", "B"])
        self.assertEqual(report["overall"]["subject_count"], 7)
        self.assertEqual(report["overall"]["both_labeled_count"], 5)
        self.assertEqual(report["overall"]["exact_agreement_count"], 3)
        self.assertEqual(report["by_group"]["rois"]["subject_count"], 4)
        self.assertEqual(report["by_group"]["events"]["exact_agreement_count"], 2)
        self.assertEqual(report["by_group"]["suggestions"]["exact_agreement_count"], 0)
        self.assertEqual(report["by_group"]["rois"]["label_pairs"]["accepted / accepted"], 1)
        self.assertGreater(report["overall"]["binary"]["n"], 0)
        self.assertIn("high / medium", report["by_confidence_pair"])
        self.assertIn("vessel / vessel", report["by_artifact_pair"])
        self.assertEqual(report["reviewer_provenance"]["A"]["missing_reviewer_total"], 6)
        self.assertEqual(report["reviewer_provenance"]["B"]["missing_reviewer_total"], 6)
        queue_ids = {(item["subject_group"], item["subject_id"]) for item in report["disagreement_queue"]}
        self.assertEqual(queue_ids, {("rois", "2"), ("rois", "3"), ("rois", "4"), ("suggestions", "S1")})

    def test_agreement_report_markdown_and_tsv_rows_are_human_readable(self):
        from neurobench.review.agreement import agreement_report_markdown, annotation_agreement_report, disagreement_tsv_rows

        report = annotation_agreement_report(
            {"rois": {"1": {"cell_state": "accepted", "confidence": "high", "reviewer_id": "RV", "updatedAt": "2026-05-14T01:00:00Z"}}},
            {"rois": {"1": {"cell_state": "rejected", "confidence": "low", "reviewer_id": "AB", "updatedAt": "2026-05-14T02:00:00Z"}}},
            reviewer_a_id="A",
            reviewer_b_id="B",
            subject_groups=("rois",),
        )

        markdown = agreement_report_markdown(report)
        rows = disagreement_tsv_rows(report)

        self.assertIn("# Annotation Agreement Report", markdown)
        self.assertIn("Binary kappa", markdown)
        self.assertIn("Reviewer Provenance", markdown)
        self.assertIn("| A | 1 | 1 | 0 |", markdown)
        self.assertEqual(rows[0]["subject_group"], "rois")
        self.assertEqual(rows[0]["label_a"], "accepted")
        self.assertEqual(rows[0]["label_b"], "rejected")
        self.assertEqual(rows[0]["source_reviewer_id_a"], "RV")
        self.assertEqual(rows[0]["source_reviewer_id_b"], "AB")
        self.assertEqual(rows[0]["updated_at_a"], "2026-05-14T01:00:00Z")


if __name__ == "__main__":
    unittest.main()
