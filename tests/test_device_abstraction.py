from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import numpy as np
except ModuleNotFoundError:
    np = None


def require_numpy():
    if np is None:
        raise unittest.SkipTest("numpy is not installed in this Python environment")


class DeviceAbstractionTests(unittest.TestCase):
    def test_auto_device_falls_back_to_cpu_when_cuda_unavailable(self):
        from neurobench.pipelines.devices import resolve_device

        with patch("neurobench.pipelines.devices._cuda_backend", return_value=""):
            spec = resolve_device("auto")

        self.assertEqual(spec.requested, "auto")
        self.assertEqual(spec.resolved, "cpu")
        self.assertEqual(spec.backend, "numpy")
        self.assertTrue(spec.available)
        self.assertIn("fallback", spec.reason)

    def test_explicit_cuda_request_fails_when_cuda_unavailable(self):
        from neurobench.pipelines.devices import resolve_device

        with patch("neurobench.pipelines.devices._cuda_backend", return_value=""):
            with self.assertRaisesRegex(RuntimeError, "CUDA device requested"):
                resolve_device("cuda")

    def test_auto_device_metadata_reaches_algorithm_output(self):
        require_numpy()
        from neurobench.algorithms.cfar import robust_local_cfar

        video = np.zeros((2, 12, 12), dtype=np.float32)
        video[0, 6, 6] = 5.0
        with patch("neurobench.pipelines.devices._cuda_backend", return_value=""):
            result = robust_local_cfar(video, pfa=0.1, guard_px=1, training_radius_px=4, device="auto")

        self.assertEqual(result["device"]["requested"], "auto")
        self.assertEqual(result["device"]["resolved"], "cpu")
        self.assertEqual(result["device"]["backend"], "numpy")

    def test_execute_pipeline_records_auto_cpu_fallback(self):
        require_numpy()
        from neurobench.data.synthetic import generate_synthetic_calcium_dataset
        from neurobench.pipelines.executor import execute_pipeline

        dataset = generate_synthetic_calcium_dataset(frames=6, height=12, width=12, include_impulse_artifact=False)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = dataset.write(root / "fixture", dataset_id="device_auto")
            spec = {
                "schema_version": 1,
                "dataset_id": "device_auto",
                "run_id": "device_auto_pipeline",
                "execution": {"device": "auto"},
                "pipeline": [
                    {"id": "source", "stage_id": "source_video_import", "params": {"source": paths["video"]}},
                    {"id": "highpass", "stage_id": "temporal_highpass_gaussian", "params": {"sigma_frames": 2.0}},
                    {"id": "smooth", "stage_id": "spatial_gaussian", "params": {"sigma_px": 0.0}},
                    {"id": "cfar", "stage_id": "gamma_cfar", "params": {"pfa": 0.2, "guard_px": 1, "training_radius_px": 4}},
                ],
            }
            with patch("neurobench.pipelines.devices._cuda_backend", return_value=""):
                result = execute_pipeline(spec, run_root=root / "run")
            manifest = json.loads((root / "run" / "pipeline_run.json").read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "completed")
        self.assertEqual(manifest["environment"]["device_requested"], "auto")
        self.assertEqual(manifest["environment"]["device"], "cpu")
        self.assertEqual(manifest["environment"]["device_backend"], "numpy")
        self.assertIn("fallback", manifest["environment"]["device_reason"])


if __name__ == "__main__":
    unittest.main()
