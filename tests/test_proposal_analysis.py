from __future__ import annotations

import unittest


class ProposalAnalysisTests(unittest.TestCase):
    def test_artifact_classifier_exposes_interpretable_risk_reasons(self):
        from neurobench.proposal_analysis import artifact_score_for_roi

        row = artifact_score_for_roi(
            {
                "id": 7,
                "area": 220,
                "bbox": [2, 10, 40, 13],
                "artifactScore": 0.55,
                "backgroundCorrelation": 0.7,
                "localCorrelationMean": 0.2,
                "traceSnr": 1.0,
            },
            video={"width": 100, "height": 80},
        )

        self.assertGreaterEqual(row["artifact_risk"], 0.4)
        self.assertIn("large or merged", row["reasons"])
        self.assertIn("background correlated", row["reasons"])
        self.assertIn("elongated", row["reasons"])

    def test_missed_neuron_ranking_prefers_supported_low_artifact_suggestions(self):
        from neurobench.proposal_analysis import build_proposal_analysis

        review_data = {
            "video": {"width": 100, "height": 80, "frames": 20},
            "rois": [],
            "discovery": {
                "suggestions": [
                    {
                        "id": "weak_artifact",
                        "priorityScore": 0.8,
                        "discoveryScore": 0.8,
                        "eventSupport": 0.05,
                        "localCorrelationMean": 0.2,
                        "compactness": 0.2,
                        "artifactScore": 0.7,
                        "artifactCue": "vessel",
                        "area": 260,
                        "bbox": [0, 5, 40, 10],
                    },
                    {
                        "id": "supported_candidate",
                        "priorityScore": 0.65,
                        "discoveryScore": 0.65,
                        "eventSupport": 0.7,
                        "localCorrelationMean": 0.75,
                        "compactness": 0.65,
                        "artifactScore": 0.0,
                        "artifactCue": "none",
                        "maxZ": 4.2,
                        "activeFrames": 8,
                        "area": 55,
                        "bbox": [20, 20, 28, 27],
                    },
                ]
            },
        }

        analysis = build_proposal_analysis(review_data, limit=5)
        rows = analysis["missed_neuron_proposals"]["rows"]

        self.assertEqual(rows[0]["suggestion_id"], "supported_candidate")
        self.assertIn("event-supported", rows[0]["reasons"])
        self.assertGreater(rows[0]["proposal_score"], rows[1]["proposal_score"])


if __name__ == "__main__":
    unittest.main()
