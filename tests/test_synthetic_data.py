from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

try:
    import numpy as np
except ModuleNotFoundError:
    np = None


def require_numpy():
    if np is None:
        raise unittest.SkipTest("numpy is not installed in this Python environment")


class SyntheticDataTests(unittest.TestCase):
    def test_synthetic_dataset_has_known_shape_events_and_artifact(self):
        require_numpy()
        from neurobench.data.synthetic import generate_synthetic_calcium_dataset

        dataset = generate_synthetic_calcium_dataset()

        self.assertEqual(dataset.shape, (24, 32, 32))
        self.assertEqual(dataset.video.dtype, np.float32)
        self.assertEqual(len(dataset.events), 2)
        self.assertIn(5, dataset.gt_data)
        self.assertEqual(dataset.gt_data[5][0], (10.0, 9.0, 1))
        self.assertEqual(dataset.artifact_locations[0]["kind"], "impulse")

    def test_synthetic_events_are_detectable_by_metric_fixture(self):
        require_numpy()
        from evaluation.metrics import calculate_froc_point_metrics
        from neurobench.data.synthetic import generate_synthetic_calcium_dataset

        dataset = generate_synthetic_calcium_dataset(include_impulse_artifact=False)
        detections = {
            frame: [{"x": x, "y": y}]
            for frame, points in dataset.gt_data.items()
            for x, y, _event_id in [points[0]]
        }
        metrics = calculate_froc_point_metrics(dataset.gt_data, detections, dataset.shape, distance_tolerance=1.0)

        self.assertEqual(metrics["TP"], sum(len(points) for points in dataset.gt_data.values()))
        self.assertEqual(metrics["FP"], 0)
        self.assertEqual(metrics["TPR"], 1.0)

    def test_synthetic_fixture_write_is_tiny_and_manifest_validates(self):
        require_numpy()
        from neurobench.data.synthetic import generate_synthetic_calcium_dataset
        from neurobench.validation.schemas import validate_json

        dataset = generate_synthetic_calcium_dataset(frames=12, height=16, width=16, include_impulse_artifact=True)
        with tempfile.TemporaryDirectory() as tmp:
            paths = dataset.write(tmp, dataset_id="unit_synthetic")
            video = np.load(paths["video"])
            manifest = validate_json(paths["manifest"], "dataset")
            gt_text = Path(paths["ground_truth"]).read_text(encoding="utf-8")

        self.assertEqual(video.shape, (12, 16, 16))
        self.assertEqual(manifest["dataset_id"], "unit_synthetic")
        self.assertIn("Start Frame", gt_text)
        self.assertLess(video.nbytes, 20_000)

    def test_synthetic_fixture_manifest_has_expected_paths(self):
        require_numpy()
        from neurobench.data.synthetic import generate_synthetic_calcium_dataset

        dataset = generate_synthetic_calcium_dataset(frames=8, height=8, width=8)
        with tempfile.TemporaryDirectory() as tmp:
            paths = dataset.write(tmp)
            manifest = json.loads(Path(paths["manifest"]).read_text(encoding="utf-8"))

        self.assertTrue(manifest["paths"]["raw_video"].endswith("video.npy"))
        self.assertTrue(manifest["paths"]["ground_truth"].endswith("ground_truth.csv"))
        self.assertTrue(manifest["paths"]["review_data"].endswith("app/review_data.json"))

    def test_synthetic_generator_rejects_invalid_dimensions(self):
        require_numpy()
        from neurobench.data.synthetic import generate_synthetic_calcium_dataset

        with self.assertRaisesRegex(ValueError, "must be positive"):
            generate_synthetic_calcium_dataset(frames=0)


if __name__ == "__main__":
    unittest.main()
