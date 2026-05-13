from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path


class WorkbenchServerTests(unittest.TestCase):
    def test_environment_report_has_generation_keys(self):
        from neurobench.workbench.server import environment_report

        report = environment_report()

        self.assertIn("fiji_available", report)
        self.assertIn("modules", report)
        self.assertIn("gpu", report)
        self.assertIn("cuda", report["gpu"])

    def test_generated_manifest_uses_whitelisted_app_paths(self):
        from neurobench.workbench.server import generated_dataset_manifest, load_json

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app_dir = root / "Outputs" / "NeuronReview" / "demo" / "app"
            app_dir.mkdir(parents=True)
            raw = root / "Inputs" / "demo.tif"
            raw.parent.mkdir()
            raw.write_bytes(b"fake")
            (app_dir / "review_data.json").write_text(
                json.dumps({"video": {"name": "demo.tif"}, "parameters": {"datasetId": "demo"}}),
                encoding="utf-8",
            )

            manifest_path = generated_dataset_manifest(app_dir, {"raw_video": str(raw)})
            manifest = load_json(manifest_path)

            self.assertEqual(manifest["dataset_id"], "demo")
            self.assertEqual(manifest["paths"]["app_dir"], str(app_dir))
            self.assertEqual(manifest["paths"]["raw_video"], str(raw))
            self.assertEqual(manifest["paths"]["architecture_runs"], str(app_dir / "architecture_runs.json"))

            run_app = app_dir / "generated_runs" / "planned_a"
            manifest_path = generated_dataset_manifest(app_dir, {"raw_video": str(raw)}, output_app_dir=run_app)
            manifest = load_json(manifest_path)
            self.assertEqual(manifest["paths"]["app_dir"], str(run_app))
            self.assertEqual(manifest["paths"]["review_data"], str(run_app / "review_data.json"))
            self.assertEqual(manifest["paths"]["architecture_runs"], str(app_dir / "architecture_runs.json"))

    def test_job_registry_rejects_duplicate_active_run(self):
        from neurobench.workbench.server import GenerationJob, JobRegistry

        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "app"
            app_dir.mkdir()
            registry = JobRegistry()
            job = GenerationJob(app_dir=app_dir, payload={"run_id": "planned_a"})
            job.status = "running"
            registry.add(job)

            self.assertIs(registry.active_for(app_dir, "planned_a"), job)
            self.assertIsNone(registry.active_for(app_dir, "planned_b"))

    def test_run_generation_params_extracts_executable_knobs(self):
        from neurobench.workbench.server import run_generation_params

        run = {
            "run_id": "planned",
            "dataset_id": "demo",
            "pipeline": [
                {"id": "hp", "stage_id": "temporal_highpass_gaussian", "params": {"sigma_frames": 8}},
                {"id": "components", "stage_id": "component_filter", "params": {"seed_z": 1.6, "grow_z": 0.8, "min_area_px": 3}},
                {"id": "events", "stage_id": "robust_kalman_positive_innovation", "params": {"event_threshold_z": 2.1}},
            ],
        }

        params = run_generation_params(run)

        self.assertEqual(params["sigma_label"], "08")
        self.assertEqual(params["component_seed_z"], 1.6)
        self.assertEqual(params["component_grow_z"], 0.8)
        self.assertEqual(params["component_min_area_px"], 3)
        self.assertEqual(params["event_threshold_z"], 2.1)

    def test_owner_token_matching_is_optional_and_exact(self):
        from neurobench.workbench.server import owner_token_matches, owner_token_required

        old = os.environ.pop("NEUROBENCH_OWNER_TOKEN", None)
        try:
            self.assertFalse(owner_token_required())
            self.assertTrue(owner_token_matches(None))
            os.environ["NEUROBENCH_OWNER_TOKEN"] = "secret"
            self.assertTrue(owner_token_required())
            self.assertTrue(owner_token_matches("secret"))
            self.assertFalse(owner_token_matches("wrong"))
            self.assertFalse(owner_token_matches(None))
        finally:
            if old is not None:
                os.environ["NEUROBENCH_OWNER_TOKEN"] = old
            else:
                os.environ.pop("NEUROBENCH_OWNER_TOKEN", None)

    def test_legacy_server_script_reexports_package_helpers(self):
        from neurobench.workbench import GenerationJob as PackageGenerationJob
        from neurobench.workbench import WorkbenchHandler as PackageWorkbenchHandler
        from tools.serve_neuron_workbench import GenerationJob as ToolGenerationJob
        from tools.serve_neuron_workbench import WorkbenchHandler as ToolWorkbenchHandler

        self.assertIs(ToolGenerationJob, PackageGenerationJob)
        self.assertIs(ToolWorkbenchHandler, PackageWorkbenchHandler)

    def test_server_factory_configures_single_dataset_app(self):
        from neurobench.workbench.server import WorkbenchHandler, create_workbench_server

        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "app"
            app_dir.mkdir()
            (app_dir / "index.html").write_text("<!doctype html><title>demo</title>", encoding="utf-8")

            server, served = create_workbench_server(app_dir=app_dir, host="127.0.0.1", port=0)
            try:
                self.assertEqual(served, app_dir.resolve())
                self.assertEqual(WorkbenchHandler.app_dir, app_dir.resolve())
                self.assertIsNone(WorkbenchHandler.root_dir)
            finally:
                server.server_close()

    def test_server_factory_configures_root_index(self):
        from neurobench.workbench.server import WorkbenchHandler, configure_workbench_handler

        with tempfile.TemporaryDirectory() as tmp:
            root_dir = Path(tmp) / "NeuronReview"
            root_dir.mkdir()
            (root_dir / "index.html").write_text("<!doctype html><title>index</title>", encoding="utf-8")

            handler, served = configure_workbench_handler(root_dir=root_dir)

            self.assertIs(handler, WorkbenchHandler)
            self.assertEqual(served, root_dir.resolve())
            self.assertEqual(WorkbenchHandler.root_dir, root_dir.resolve())
            self.assertEqual(WorkbenchHandler.app_dir, root_dir.resolve())


if __name__ == "__main__":
    unittest.main()
