from __future__ import annotations

import unittest


class ArchitectureRunTests(unittest.TestCase):
    def test_merge_manifests_rejects_duplicate_run_ids(self):
        from neurobench.architecture_runs import merge_run_manifests

        manifest = {"schema_version": 1, "dataset_id": "d", "runs": [{"run_id": "a", "dataset_id": "d"}]}
        with self.assertRaises(ValueError):
            merge_run_manifests([manifest, manifest])

    def test_merge_manifests_can_replace_duplicate_run_ids(self):
        from neurobench.architecture_runs import merge_run_manifests

        a = {"schema_version": 1, "dataset_id": "d", "runs": [{"run_id": "a", "dataset_id": "d", "label": "old"}]}
        b = {"schema_version": 1, "dataset_id": "d", "runs": [{"run_id": "a", "dataset_id": "d", "label": "new"}]}
        merged = merge_run_manifests([a, b], replace=True)

        self.assertEqual(len(merged["runs"]), 1)
        self.assertEqual(merged["runs"][0]["label"], "new")

    def test_merge_manifests_rejects_mixed_dataset_ids(self):
        from neurobench.architecture_runs import merge_run_manifests

        a = {"schema_version": 1, "dataset_id": "a", "runs": [{"run_id": "a", "dataset_id": "a"}]}
        b = {"schema_version": 1, "dataset_id": "b", "runs": [{"run_id": "b", "dataset_id": "b"}]}

        with self.assertRaises(ValueError):
            merge_run_manifests([a, b])

    def test_merge_preserves_structured_pipeline_metadata(self):
        from neurobench.architecture_runs import merge_run_manifests

        pipeline = [
            {
                "id": "source",
                "stage_id": "source_video_import",
                "params": {"source": "raw.tif"},
                "metadata": {"owner": "bench"},
            },
            {"id": "review_app", "stage_id": "generate_neuron_review_app"},
        ]
        manifest = {
            "schema_version": 1,
            "dataset_id": "d",
            "runs": [{"schema_version": 1, "run_id": "a", "dataset_id": "d", "pipeline": pipeline, "artifacts": {}}],
        }

        merged = merge_run_manifests([manifest])

        self.assertEqual(merged["runs"][0]["pipeline"][0]["metadata"], {"owner": "bench"})
        self.assertEqual(merged["runs"][0]["pipeline"][0]["params"], {"source": "raw.tif"})
        self.assertEqual(merged["runs"][0]["pipeline"][1]["params"], {"include_discovery": True})

    def test_build_planned_manifest_sets_planned_status_deterministically(self):
        from neurobench.architecture_runs import build_planned_manifest

        spec = {
            "schema_version": 1,
            "dataset_id": "d",
            "pipeline": [
                {"id": "source", "stage_id": "source_video_import", "params": {"source": "raw.tif"}},
                {"id": "review_app", "stage_id": "generate_neuron_review_app"},
            ],
            "artifacts": {"source_video": "raw.tif"},
        }

        first = build_planned_manifest(spec)
        second = build_planned_manifest(spec)

        self.assertEqual(first, second)
        self.assertEqual(first["runs"][0]["execution"], {"status": "planned"})
        self.assertTrue(first["runs"][0]["run_id"].startswith("planned_"))


if __name__ == "__main__":
    unittest.main()
