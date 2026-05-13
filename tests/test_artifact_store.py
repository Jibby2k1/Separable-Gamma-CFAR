from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path


def _pipeline_run():
    from neurobench.models.pipeline import PipelineRun

    return PipelineRun(
        schema_version=1,
        run_id="run_001",
        dataset_id="dataset_001",
        pipeline_spec_id="spec_001",
        status="running",
        created_at="2026-05-13T00:00:00Z",
        parameter_hash="hash123",
        artifacts=[],
        environment={"device": "cpu"},
        code={"git_commit": "abcdef"},
    )


class ArtifactStoreTests(unittest.TestCase):
    def test_run_layout_helper_creates_standard_directories_and_manifest(self):
        from neurobench.pipelines.artifacts import create_run_layout

        with tempfile.TemporaryDirectory() as tmp:
            paths = create_run_layout(Path(tmp) / "run", _pipeline_run())
            manifest = json.loads(paths["pipeline_run"].read_text(encoding="utf-8"))

            self.assertTrue(paths["logs"].is_dir())
            self.assertTrue(paths["artifacts"].is_dir())
            self.assertTrue(paths["workbench"].is_dir())
            self.assertTrue(paths["exports"].is_dir())
            self.assertEqual(manifest["run_id"], "run_001")

    def test_sha256_file_matches_hashlib(self):
        from neurobench.pipelines.artifacts import sha256_file

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "artifact.txt"
            path.write_text("fixture", encoding="utf-8")

            self.assertEqual(sha256_file(path), hashlib.sha256(b"fixture").hexdigest())

    def test_artifact_store_registers_checksum_and_updates_manifest(self):
        from neurobench.pipelines.artifacts import ArtifactStore

        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore(Path(tmp) / "run", _pipeline_run())
            artifact_path = store.artifact_path("candidates", "events.json")
            artifact_path.write_text('{"events": []}', encoding="utf-8")
            record = store.register_file(
                artifact_path,
                artifact_id="candidate_events.v1",
                kind="candidate_events",
                producer_stage="gamma_cfar",
                schema="candidate_event.schema.json",
                summary={"count": 0},
                created_at="2026-05-13T00:01:00Z",
            )
            manifest = json.loads((Path(tmp) / "run" / "pipeline_run.json").read_text(encoding="utf-8"))

            self.assertEqual(record.path, "artifacts/candidates/events.json")
            self.assertEqual(record.sha256, hashlib.sha256(b'{"events": []}').hexdigest())
            self.assertEqual(manifest["artifacts"][0]["artifact_id"], "candidate_events.v1")
            self.assertEqual(manifest["artifacts"][0]["summary"], {"count": 0})

    def test_artifact_store_replaces_existing_artifact_id(self):
        from neurobench.pipelines.artifacts import ArtifactStore

        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore(Path(tmp) / "run", _pipeline_run())
            first = store.artifact_path("metrics", "first.json")
            second = store.artifact_path("metrics", "second.json")
            first.write_text("first", encoding="utf-8")
            second.write_text("second", encoding="utf-8")
            store.register_file(first, artifact_id="metrics.v1", kind="metrics", producer_stage="stage")
            store.register_file(second, artifact_id="metrics.v1", kind="metrics", producer_stage="stage")

            manifest = json.loads((Path(tmp) / "run" / "pipeline_run.json").read_text(encoding="utf-8"))

            self.assertEqual(len(manifest["artifacts"]), 1)
            self.assertEqual(manifest["artifacts"][0]["path"], "artifacts/metrics/second.json")

    def test_artifact_store_rejects_missing_file(self):
        from neurobench.pipelines.artifacts import ArtifactStore

        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore(Path(tmp) / "run", _pipeline_run())

            with self.assertRaises(FileNotFoundError):
                store.register_file(
                    Path(tmp) / "missing.json",
                    artifact_id="missing.v1",
                    kind="missing",
                    producer_stage="stage",
                )


if __name__ == "__main__":
    unittest.main()
