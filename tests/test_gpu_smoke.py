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


def require_cuda_backend():
    from neurobench.pipelines.devices import resolve_device

    spec = resolve_device("auto")
    if spec.resolved != "cuda":
        raise unittest.SkipTest(f"CUDA backend unavailable: {spec.reason}")
    return spec


class OptionalGpuSmokeTests(unittest.TestCase):
    def test_cuda_backend_can_allocate_tiny_array_when_available(self):
        spec = require_cuda_backend()

        if spec.backend == "torch_cuda":
            import torch  # type: ignore

            value = torch.ones((2, 2), device="cuda").sum().item()
            self.assertEqual(value, 4.0)
        elif spec.backend == "cupy_cuda":
            import cupy  # type: ignore

            value = float(cupy.ones((2, 2), dtype=cupy.float32).sum().get())
            self.assertEqual(value, 4.0)
        else:
            self.fail(f"Unexpected CUDA backend: {spec.backend}")

    def test_cuda_pipeline_execution_records_cuda_manifest_when_available(self):
        require_numpy()
        spec = require_cuda_backend()
        from neurobench.data.synthetic import generate_synthetic_calcium_dataset
        from neurobench.pipelines.executor import execute_pipeline

        dataset = generate_synthetic_calcium_dataset(frames=5, height=12, width=12, include_impulse_artifact=False)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = dataset.write(root / "fixture", dataset_id="gpu_smoke")
            pipeline_spec = {
                "schema_version": 1,
                "dataset_id": "gpu_smoke",
                "run_id": "gpu_smoke_pipeline",
                "execution": {"device": "cuda"},
                "pipeline": [
                    {"id": "source", "stage_id": "source_video_import", "params": {"source": paths["video"]}},
                    {"id": "highpass", "stage_id": "temporal_highpass_gaussian", "params": {"sigma_frames": 2.0}},
                    {"id": "smooth", "stage_id": "spatial_gaussian", "params": {"sigma_px": 0.0}},
                    {"id": "cfar", "stage_id": "gamma_cfar", "params": {"pfa": 0.2, "guard_px": 1, "training_radius_px": 4}},
                ],
            }

            result = execute_pipeline(pipeline_spec, run_root=root / "run")
            manifest = json.loads((root / "run" / "pipeline_run.json").read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "completed")
        self.assertEqual(manifest["environment"]["device_requested"], "cuda")
        self.assertEqual(manifest["environment"]["device"], "cuda")
        self.assertEqual(manifest["environment"]["device_backend"], spec.backend)
        self.assertGreaterEqual(len(manifest["artifacts"]), 4)


if __name__ == "__main__":
    unittest.main()
