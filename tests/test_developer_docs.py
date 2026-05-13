from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DeveloperDocsTests(unittest.TestCase):
    def test_adding_pipeline_stage_guide_covers_current_runner_contract(self):
        text = (ROOT / "docs" / "developer" / "adding_pipeline_stage.md").read_text(encoding="utf-8")

        self.assertIn("neurobench/pipeline_catalog.py", text)
        self.assertIn("neurobench/pipelines/executor.py", text)
        self.assertIn("_STAGE_METADATA", text)
        self.assertIn("STAGE_CATALOG", text)
        self.assertIn("_PARAMETER_DOCS", text)
        self.assertIn("_STAGE_RUNNERS", text)
        self.assertIn("ArtifactStore", text)
        self.assertIn("store.register_file", text)
        self.assertIn("dry_run_pipeline", text)
        self.assertIn("execute_pipeline", text)
        self.assertIn("NotImplementedError", text)
        self.assertIn("real_time_profile", text)

    def test_adding_pipeline_stage_guide_contains_tested_minimal_example(self):
        text = (ROOT / "docs" / "developer" / "adding_pipeline_stage.md").read_text(encoding="utf-8")

        self.assertIn("def _run_example_stage", text)
        self.assertIn("def test_synthetic_pipeline_executes_example_stage", text)
        self.assertIn("test_synthetic_pipeline_executes_spatial_gaussian_and_gamma_cfar", text)
        self.assertIn("source_video_import -> temporal_highpass_gaussian -> spatial_gaussian ->", text)
        self.assertRegex(text, r"return \"example_video\", out")

    def test_adding_pipeline_stage_guide_uses_relative_paths_only(self):
        text = (ROOT / "docs" / "developer" / "adding_pipeline_stage.md").read_text(encoding="utf-8")

        self.assertNotRegex(text, r"/home/|/Users/|[A-Za-z]:\\\\")

    def test_readme_links_adding_pipeline_stage_guide(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("docs/developer/adding_pipeline_stage.md", readme)


if __name__ == "__main__":
    unittest.main()
