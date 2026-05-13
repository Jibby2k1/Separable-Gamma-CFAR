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


def _spec(source: str, *, run_id: str) -> dict:
    return {
        "schema_version": 1,
        "dataset_id": "batch_synthetic",
        "run_id": run_id,
        "pipeline": [
            {"id": "source", "stage_id": "source_video_import", "params": {"source": source}},
            {"id": "highpass", "stage_id": "temporal_highpass_gaussian", "params": {"sigma_frames": 2.0}},
            {"id": "score", "stage_id": "robust_positive_local_z", "params": {"epsilon": 0.05}},
            {
                "id": "components",
                "stage_id": "component_filter",
                "params": {"seed_z": 1.5, "min_area_px": 3, "max_area_px": 100},
            },
        ],
        "artifacts": {},
    }


class PipelineBatchTests(unittest.TestCase):
    def test_batch_runner_records_failure_without_losing_successes(self):
        require_numpy()
        from neurobench.data.synthetic import generate_synthetic_calcium_dataset
        from neurobench.pipelines.batch import execute_batch

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture_paths = generate_synthetic_calcium_dataset(include_impulse_artifact=False).write(root / "fixture")
            good_spec = root / "good.json"
            bad_spec = root / "bad.json"
            good_spec.write_text(json.dumps(_spec(fixture_paths["video"], run_id="good_run")), encoding="utf-8")
            bad_spec.write_text(json.dumps(_spec(str(root / "missing.npy"), run_id="bad_run")), encoding="utf-8")

            summary = execute_batch([good_spec, bad_spec], run_root=root / "batch")
            summary_from_disk = json.loads((root / "batch" / "batch_summary.json").read_text(encoding="utf-8"))
            good_manifest = json.loads((root / "batch" / "001_good_run" / "pipeline_run.json").read_text(encoding="utf-8"))

        self.assertEqual(summary["status"], "completed_with_failures")
        self.assertEqual(summary["succeeded"], 1)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary_from_disk, summary)
        self.assertEqual(summary["runs"][0]["status"], "completed")
        self.assertEqual(summary["runs"][1]["status"], "failed")
        self.assertIn("missing.npy", summary["runs"][1]["error"])
        self.assertEqual(good_manifest["status"], "completed")


if __name__ == "__main__":
    unittest.main()
