from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import numpy as np
except ModuleNotFoundError:
    np = None


ROOT = Path(__file__).resolve().parents[1]


def require_numpy():
    if np is None:
        raise unittest.SkipTest("numpy is not installed in this Python environment")


class DatasetQCTests(unittest.TestCase):
    def test_compute_dataset_qc_from_synthetic_manifest(self):
        require_numpy()
        from neurobench.data.qc import compute_dataset_qc_from_manifest
        from neurobench.data.synthetic import generate_synthetic_calcium_dataset

        dataset = generate_synthetic_calcium_dataset(frames=12, height=16, width=16, include_impulse_artifact=False)
        with tempfile.TemporaryDirectory() as tmp:
            paths = dataset.write(tmp, dataset_id="qc_synthetic")
            qc = compute_dataset_qc_from_manifest(paths["manifest"])

        self.assertEqual(qc["schema_version"], 1)
        self.assertEqual(qc["dataset_id"], "qc_synthetic")
        self.assertEqual(qc["video"]["shape"], [12, 16, 16])
        self.assertEqual(qc["video"]["dtype"], "float32")
        self.assertGreater(qc["intensity"]["std"], 0.0)
        self.assertIn("median_abs_frame_diff", qc["temporal"])

    def test_compute_video_qc_flags_constant_video(self):
        require_numpy()
        from neurobench.data.qc import compute_video_qc

        video = np.zeros((4, 8, 8), dtype=np.float32)
        qc = compute_video_qc(video, dataset_id="constant")

        self.assertIn("Video has near-zero intensity variance.", qc["warnings"])
        self.assertEqual(qc["saturation"]["max_fraction"], 1.0)

    def test_render_dataset_qc_markdown_contains_core_sections(self):
        require_numpy()
        from neurobench.data.qc import compute_video_qc, render_dataset_qc_markdown

        qc = compute_video_qc(np.ones((3, 4, 5), dtype=np.float32), dataset_id="demo", source_path="video.npy")
        markdown = render_dataset_qc_markdown(qc)

        self.assertIn("# Dataset QC: demo", markdown)
        self.assertIn("## Video", markdown)
        self.assertIn("## Intensity", markdown)
        self.assertIn("## Temporal Stability", markdown)
        self.assertIn("video.npy", markdown)

    def test_cli_dataset_qc_writes_json_and_markdown(self):
        require_numpy()
        from neurobench.data.synthetic import generate_synthetic_calcium_dataset

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = generate_synthetic_calcium_dataset(frames=8, height=8, width=8).write(root / "fixture", dataset_id="cli_qc")
            out_dir = root / "qc"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "neurobench.cli.main",
                    "dataset",
                    "qc",
                    paths["manifest"],
                    "--output",
                    str(out_dir),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            qc = json.loads((out_dir / "qc_report.json").read_text(encoding="utf-8"))
            markdown = (out_dir / "qc_report.md").read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Dataset QC JSON", result.stdout)
        self.assertEqual(qc["dataset_id"], "cli_qc")
        self.assertIn("# Dataset QC: cli_qc", markdown)


if __name__ == "__main__":
    unittest.main()
