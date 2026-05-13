from __future__ import annotations

import string
import unittest
from pathlib import Path


class ParameterHashingTests(unittest.TestCase):
    def test_parameter_hash_is_independent_of_mapping_key_order(self):
        from neurobench.pipelines.specs import parameter_hash

        left = {"b": 2, "a": {"y": 1, "x": [3, 2]}}
        right = {"a": {"x": [3, 2], "y": 1}, "b": 2}

        self.assertEqual(parameter_hash(left), parameter_hash(right))

    def test_parameter_hash_preserves_sequence_order(self):
        from neurobench.pipelines.specs import parameter_hash

        self.assertNotEqual(parameter_hash({"steps": ["smooth", "cfar"]}), parameter_hash({"steps": ["cfar", "smooth"]}))

    def test_parameter_hash_returns_full_hex_sha256_digest(self):
        from neurobench.pipelines.specs import parameter_hash

        digest = parameter_hash({"event_threshold": 2.4})

        self.assertEqual(len(digest), 64)
        self.assertTrue(all(char in string.hexdigits for char in digest))

    def test_canonical_json_normalizes_paths_and_sets(self):
        from neurobench.pipelines.specs import canonical_json

        left = {"path": Path("Inputs") / "rest.tif", "channels": {"green", "red"}}
        right = {"channels": {"red", "green"}, "path": "Inputs/rest.tif"}

        self.assertEqual(canonical_json(left), canonical_json(right))

    def test_pipeline_spec_parameter_hash_ignores_non_behavioral_metadata(self):
        from neurobench.pipelines.specs import pipeline_spec_parameter_hash

        base = {
            "schema_version": 1,
            "dataset_id": "resting_crop",
            "run_id": "run_a",
            "label": "A",
            "pipeline": [{"stage": "temporal_smoothing", "params": {"sigma_frames": 6}}],
            "parameters": {"event_threshold": 2.4},
            "execution": {"device": "cpu"},
            "artifacts": {"overlay": "run_a.png"},
            "output_root": "outputs/run_a",
            "summary": {"note": "first"},
        }
        renamed = dict(base)
        renamed.update(
            {
                "run_id": "run_b",
                "label": "B",
                "artifacts": {"overlay": "run_b.png"},
                "output_root": "outputs/run_b",
                "summary": {"note": "second"},
            }
        )

        self.assertEqual(pipeline_spec_parameter_hash(base), pipeline_spec_parameter_hash(renamed))

    def test_pipeline_spec_parameter_hash_changes_when_stage_parameter_changes(self):
        from neurobench.pipelines.specs import pipeline_spec_parameter_hash

        base = {
            "pipeline": [{"stage": "event_trace", "params": {"event_threshold": 2.4}}],
            "execution": {"device": "cpu"},
        }
        changed = {
            "pipeline": [{"stage": "event_trace", "params": {"event_threshold": 2.8}}],
            "execution": {"device": "cpu"},
        }

        self.assertNotEqual(pipeline_spec_parameter_hash(base), pipeline_spec_parameter_hash(changed))


if __name__ == "__main__":
    unittest.main()
