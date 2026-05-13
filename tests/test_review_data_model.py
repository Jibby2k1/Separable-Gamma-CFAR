from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import jsonschema


def _review_payload() -> dict:
    return {
        "schema_version": 1,
        "dataset": {"dataset_id": "rest_crop", "modality": "calcium"},
        "video": {"name": "rest.tif", "width": 64, "height": 32, "frames": 12, "framePattern": "frames/frame_%04d.png"},
        "parameters": {"datasetId": "rest_crop", "eventZThreshold": 2.4},
        "qc": {"roiAreaStats": {"median": 47}},
        "discovery": {
            "evidenceMaps": [{"id": "z_projection", "file": "evidence/z.png"}],
            "suggestions": [{"id": "S1", "centroidX": 10.0, "centroidY": 8.0, "discoveryScore": 0.8}],
        },
        "rois": [
            {"id": 1, "area": 45, "centroidX": 8.0, "centroidY": 7.0, "events": [{"frame": 4, "z": 3.1}]},
            {"id": 2, "area": 55, "centroidX": 20.0, "centroidY": 16.0, "events": []},
        ],
        "assetBasePath": ".",
    }


class ReviewDataModelTests(unittest.TestCase):
    def test_review_data_model_roundtrip_and_summary(self):
        from neurobench.models.review import ReviewData

        model = ReviewData.from_dict(_review_payload())

        self.assertEqual(model.to_dict(), _review_payload())
        self.assertEqual(
            model.summary(),
            {
                "dataset_id": "rest_crop",
                "video_name": "rest.tif",
                "width": 64,
                "height": 32,
                "frames": 12,
                "roi_count": 2,
                "event_count": 1,
                "suggestion_count": 1,
            },
        )
        model.validate()

    def test_review_data_load_write_json_roundtrip(self):
        from neurobench.models.review import ReviewData

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "review_data.json"
            ReviewData.from_dict(_review_payload()).write_json(out)

            self.assertEqual(ReviewData.load_json(out).to_dict(), _review_payload())

    def test_review_data_schema_rejects_invalid_video_dimensions(self):
        from neurobench.models.review import ReviewData

        payload = _review_payload()
        payload["video"]["frames"] = 0
        model = ReviewData.from_dict(payload)

        with self.assertRaises(jsonschema.ValidationError) as ctx:
            model.validate()

        self.assertEqual(list(ctx.exception.path), ["video", "frames"])

    def test_review_data_schema_alias_validates_payload(self):
        from neurobench.validation.schemas import validate_json

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review_data.json"
            path.write_text(json.dumps(_review_payload()), encoding="utf-8")

            self.assertEqual(validate_json(path, "review_data"), _review_payload())


if __name__ == "__main__":
    unittest.main()
