from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


class PipelineRunnerIndexTests(unittest.TestCase):
    def test_runner_stage_aliases_expand_to_dataset_workflow(self):
        from tools.run_neuron_review_pipeline import split_stages

        self.assertEqual(
            split_stages("highpass,denoise,build"),
            ["high-pass", "event-denoise", "workbench"],
        )
        self.assertIn("index", split_stages("all"))

    def test_workbench_index_discovers_dataset_apps(self):
        from tools.build_workbench_index import dataset_rows, render

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "calcium_rest_cropped" / "app"
            app.mkdir(parents=True)
            (app / "index.html").write_text("<html></html>", encoding="utf-8")
            (app / "review_data.json").write_text(
                json.dumps(
                    {
                        "dataset": {"dataset_id": "calcium_rest_cropped"},
                        "video": {"name": "calcium_rest_cropped.tif", "frames": 42, "width": 64, "height": 32},
                        "qc": {"roiAreaStats": {"median": 55}},
                        "rois": [{"id": 1}, {"id": 2}],
                        "discovery": {"suggestions": [{"id": "S1"}]},
                    }
                ),
                encoding="utf-8",
            )

            rows = dataset_rows(root)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["dataset_id"], "calcium_rest_cropped")
            self.assertEqual(rows[0]["rois"], 2)
            html = render(rows)
            self.assertIn("Open dashboard", html)
            self.assertIn("calcium_rest_cropped/app/index.html", html)


if __name__ == "__main__":
    unittest.main()
