from __future__ import annotations

import unittest


def test_annotation_summary_includes_triage_categories_without_dropping_existing_keys():
    from neurobench.annotation_metrics import compute_annotation_summary

    review_data = {
        "rois": [
            {"id": 1, "artifactScore": 0.1, "events": [{"frame": 10}]},
            {"id": 2, "artifactScore": 0.5, "events": [{"frame": 20}]},
            {"id": 3, "events": []},
            {"id": 4, "events": []},
        ],
        "discovery": {
            "suggestions": [
                {"id": "S1", "artifactCue": "none"},
                {"id": "S2", "artifactCue": "vessel"},
                {"id": "S3", "artifactScore": 0.1},
            ]
        },
    }
    annotations = {
        "schema_version": 3,
        "rois": {
            "1": {"cell_state": "accepted", "trace_quality": "good", "control_ready": "yes", "artifact_class": ""},
            "2": {"cell_state": "accepted", "trace_quality": "weak", "control_ready": "maybe", "artifact_class": ""},
            "3": {"identity_group": "g1", "needs_action": "merge_needed"},
            "4": {"identity_group": "g1"},
        },
        "events": {
            "1:10": {"event_state": "accepted"},
            "2:20": {"event_state": "unsure", "event_type": "weak", "timing_quality": "ambiguous"},
        },
        "suggestions": {
            "S1": {"state": "missed"},
            "S2": {"state": "artifact"},
            "S3": {},
        },
        "promotedRois": {"S3": {"roi_id": "P1"}},
        "virtualRois": {"VM_3_4": {"roi_kind": "virtual_merge", "source_roi_ids": [3, 4]}},
        "settings": {},
    }

    summary = compute_annotation_summary(review_data, annotations)

    assert summary["roi_count"] == 4
    assert summary["event_count"] == 2
    assert summary["suggestion_count"] == 3
    assert summary["roi_states"]["accepted"] == 2
    assert summary["event_states"]["accepted"] == 1
    assert summary["suggestion_states"]["promoted"] == 1
    assert summary["trace_quality"]["weak"] == 1
    assert summary["control_ready"]["yes"] == 1
    assert "review_burden" in summary

    triage = summary["triage_categories"]
    assert summary["triage_queue_counts"] == {
        "strong_neuron": 1,
        "possible_missed_neuron": 2,
        "artifact_like": 2,
        "merged_cluster": 3,
        "weak_trace": 1,
        "needs_event_review": 1,
    }
    assert triage["strong_neuron"]["roi_ids"] == ["1"]
    assert triage["possible_missed_neuron"]["suggestion_ids"] == ["S1", "S3"]
    assert triage["artifact_like"]["roi_ids"] == ["2"]
    assert triage["artifact_like"]["suggestion_ids"] == ["S2"]
    assert triage["merged_cluster"]["roi_ids"] == ["3", "4"]
    assert triage["merged_cluster"]["virtual_roi_ids"] == ["VM_3_4"]
    assert triage["weak_trace"]["roi_ids"] == ["2"]
    assert triage["needs_event_review"]["event_ids"] == ["2:20"]


class AnnotationMetricsTests(unittest.TestCase):
    def test_annotation_summary_includes_triage_categories_without_dropping_existing_keys(self):
        test_annotation_summary_includes_triage_categories_without_dropping_existing_keys()


if __name__ == "__main__":
    unittest.main()
