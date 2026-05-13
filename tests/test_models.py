from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[1]


class ModelRoundtripTests(unittest.TestCase):
    def test_dataset_manifest_model_roundtrip_example(self):
        from neurobench.models.dataset import DatasetManifest

        payload = json.loads((ROOT / "examples" / "dataset_manifest.example.json").read_text(encoding="utf-8"))
        model = DatasetManifest.from_dict(payload)

        self.assertEqual(model.dataset_id, "calcium_video_2")
        self.assertEqual(model.to_dict(), payload)
        model.validate()

    def test_dataset_manifest_load_write_json_roundtrip(self):
        from neurobench.models.dataset import DatasetManifest

        payload = json.loads((ROOT / "examples" / "dataset_manifest.example.json").read_text(encoding="utf-8"))
        model = DatasetManifest.from_dict(payload)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "dataset.json"
            model.write_json(out)

            self.assertEqual(DatasetManifest.load_json(out).to_dict(), payload)

    def test_dataset_manifest_model_preserves_extras(self):
        from neurobench.models.dataset import DatasetManifest

        payload = {
            "schema_version": 1,
            "dataset_id": "extra",
            "paths": {"raw_video": "raw.tif", "app_dir": "app", "review_data": "app/review_data.json"},
            "custom_note": {"reviewer": "lab"},
        }
        model = DatasetManifest.from_dict(payload)

        self.assertEqual(model.extras["custom_note"], {"reviewer": "lab"})
        self.assertEqual(model.to_dict(), payload)

    def test_pipeline_spec_model_roundtrip_example(self):
        from neurobench.models.pipeline import PipelineSpec

        payload = json.loads((ROOT / "examples" / "pipeline_spec.example.json").read_text(encoding="utf-8"))
        model = PipelineSpec.from_dict(payload)

        self.assertEqual(model.run_id, "planned_candidate_review_v1")
        self.assertEqual(model.to_dict(), payload)
        model.validate()

    def test_pipeline_spec_load_write_json_roundtrip(self):
        from neurobench.models.pipeline import PipelineSpec

        payload = json.loads((ROOT / "examples" / "pipeline_spec.example.json").read_text(encoding="utf-8"))
        model = PipelineSpec.from_dict(payload)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "pipeline.json"
            model.write_json(out)

            self.assertEqual(PipelineSpec.load_json(out).to_dict(), payload)

    def test_pipeline_spec_preserves_extras(self):
        from neurobench.models.pipeline import PipelineSpec

        payload = {
            "schema_version": 1,
            "dataset_id": "d",
            "run_id": "r",
            "pipeline": [{"id": "source", "stage_id": "source_video_import"}],
            "artifacts": {},
            "research_knob": {"enabled": True},
        }
        model = PipelineSpec.from_dict(payload)

        self.assertEqual(model.extras["research_knob"], {"enabled": True})
        self.assertEqual(model.to_dict(), payload)

    def test_invalid_model_validation_messages(self):
        from neurobench.models.dataset import DatasetManifest

        model = DatasetManifest(schema_version=1, dataset_id="bad", paths={})

        with self.assertRaises(jsonschema.ValidationError) as ctx:
            model.validate()

        self.assertIn("raw_video", ctx.exception.message)

    def test_public_model_package_exports_export_bundle(self):
        from neurobench.models import ExportBundle

        self.assertEqual(ExportBundle.__name__, "ExportBundle")


if __name__ == "__main__":
    unittest.main()
