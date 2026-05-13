from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import jsonschema


def _bundle_payload() -> dict:
    return {
        "schema_version": 1,
        "export_bundle_id": "export_resting_001",
        "dataset_id": "calcium_rest_cropped",
        "run_ids": ["resting_baseline"],
        "created_at": "2026-05-13T00:00:00Z",
        "profile": "accepted_only",
        "selection_policy": {
            "name": "accepted_only",
            "description": "Only reviewed accepted ROIs and accepted candidate events are exported.",
            "include_rois": "accepted",
            "include_events": "accepted",
            "review_state_required": ["accepted"],
        },
        "alignment_status": "not_provided",
        "alignment": {"status": "not_provided"},
        "files": [
            {
                "kind": "accepted_traces",
                "path": "accepted_traces.tsv",
                "format": "tsv",
                "sha256": "abc123",
                "rows": 12,
                "description": "Background-corrected accepted ROI traces.",
            },
            {
                "kind": "neuron_metadata",
                "path": "neuron_metadata.tsv",
                "format": "tsv",
                "rows": 12,
            },
        ],
        "checksums": {"accepted_traces.tsv": "abc123"},
        "warnings": ["No behavior alignment file was provided."],
        "provenance": {
            "review_data": "app/review_data.json",
            "annotations": "app/annotations.json",
            "pipeline_run_paths": ["runs/resting_baseline/pipeline_run.json"],
            "metrics_report": "reports/resting_baseline_metrics.json",
        },
    }


class ExportBundleModelTests(unittest.TestCase):
    def test_export_bundle_model_roundtrip_and_validation(self):
        from neurobench.models.exports import ExportBundle

        payload = _bundle_payload()
        model = ExportBundle.from_dict(payload)

        self.assertEqual(model.export_bundle_id, "export_resting_001")
        self.assertEqual(model.alignment_status, "not_provided")
        self.assertEqual(model.to_dict(), payload)
        model.validate()

    def test_export_bundle_load_write_json_roundtrip(self):
        from neurobench.models.exports import ExportBundle

        model = ExportBundle.from_dict(_bundle_payload())
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "export_bundle.json"
            model.write_json(out)

            self.assertEqual(ExportBundle.load_json(out).to_dict(), model.to_dict())

    def test_export_bundle_preserves_extras(self):
        from neurobench.models.exports import ExportBundle

        payload = _bundle_payload()
        payload["downstream_note"] = {"owner": "inverse_dynamics"}

        model = ExportBundle.from_dict(payload)

        self.assertEqual(model.extras["downstream_note"], {"owner": "inverse_dynamics"})
        self.assertEqual(model.to_dict()["extras"]["downstream_note"], {"owner": "inverse_dynamics"})

    def test_export_bundle_rejects_invalid_alignment_status(self):
        from neurobench.models.exports import ExportBundle

        payload = _bundle_payload()
        payload["alignment_status"] = "unknown"
        model = ExportBundle.from_dict(payload)

        with self.assertRaisesRegex(ValueError, "Invalid alignment_status"):
            model.validate()

    def test_export_bundle_schema_rejects_missing_selection_policy(self):
        from neurobench.validation.schemas import validate_dict

        payload = _bundle_payload()
        del payload["selection_policy"]

        with self.assertRaises(jsonschema.ValidationError):
            validate_dict(payload, "export_bundle")

    def test_export_bundle_schema_alias_accepts_payload(self):
        from neurobench.validation.schemas import validate_dict

        validate_dict(_bundle_payload(), "export")

    def test_export_bundle_json_schema_document_is_valid(self):
        from neurobench.validation.schemas import load_schema

        schema = load_schema("export_bundle")

        self.assertEqual(schema["title"], "Neurobench Export Bundle")


if __name__ == "__main__":
    unittest.main()
