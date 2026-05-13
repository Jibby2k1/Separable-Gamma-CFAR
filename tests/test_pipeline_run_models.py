from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import jsonschema


def _artifact_payload() -> dict:
    return {
        "schema_version": 1,
        "artifact_id": "candidate_events.v1",
        "kind": "candidate_events",
        "path": "artifacts/candidates/events.json",
        "schema": "candidate_event.schema.json",
        "producer_stage": "gamma_cfar",
        "created_at": "2026-05-13T00:00:00Z",
        "sha256": "abc123",
        "summary": {"count": 2},
    }


def _run_payload() -> dict:
    return {
        "schema_version": 1,
        "run_id": "run_001",
        "dataset_id": "dataset_001",
        "pipeline_spec_id": "gamma_cfar_high_recall_v1",
        "status": "completed",
        "created_at": "2026-05-13T00:00:00Z",
        "completed_at": "2026-05-13T00:01:00Z",
        "parameter_hash": "hash123",
        "environment": {"python": "3.10", "device": "cpu"},
        "code": {"git_commit": "abcdef", "git_dirty": False},
        "artifacts": [_artifact_payload()],
        "metrics": {"object_level": {"recall": 1.0}},
        "warnings": ["synthetic fixture"],
        "logs": ["completed"],
    }


class PipelineRunModelTests(unittest.TestCase):
    def test_artifact_record_schema_and_roundtrip(self):
        from neurobench.models.artifacts import ArtifactRecord

        record = ArtifactRecord.from_dict(_artifact_payload())

        self.assertEqual(record.artifact_id, "candidate_events.v1")
        self.assertEqual(record.kind, "candidate_events")
        self.assertEqual(record.producer_stage, "gamma_cfar")
        self.assertEqual(record.sha256, "abc123")
        self.assertEqual(record.to_dict(), _artifact_payload())
        record.validate()

    def test_artifact_record_write_json_roundtrip(self):
        from neurobench.models.artifacts import ArtifactRecord

        record = ArtifactRecord.from_dict(_artifact_payload())
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "artifact.json"
            record.write_json(out)

            self.assertEqual(ArtifactRecord.load_json(out).to_dict(), _artifact_payload())

    def test_pipeline_run_model_roundtrip_and_validation(self):
        from neurobench.models.pipeline import PipelineRun

        run = PipelineRun.from_dict(_run_payload())

        self.assertEqual(run.run_id, "run_001")
        self.assertEqual(run.artifacts[0].artifact_id, "candidate_events.v1")
        self.assertEqual(run.to_dict(), _run_payload())
        run.validate()

    def test_pipeline_run_write_json_roundtrip(self):
        from neurobench.models.pipeline import PipelineRun

        run = PipelineRun.from_dict(_run_payload())
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "pipeline_run.json"
            run.write_json(out)

            self.assertEqual(PipelineRun.load_json(out).to_dict(), _run_payload())

    def test_pipeline_run_preserves_extras(self):
        from neurobench.models.pipeline import PipelineRun

        payload = _run_payload()
        payload["review_context"] = {"reviewer": "lab"}
        run = PipelineRun.from_dict(payload)

        self.assertEqual(run.extras["review_context"], {"reviewer": "lab"})
        self.assertEqual(run.to_dict()["extras"]["review_context"], {"reviewer": "lab"})

    def test_invalid_pipeline_run_missing_ids_fails_clearly(self):
        from neurobench.models.pipeline import PipelineRun

        run = PipelineRun(
            schema_version=1,
            run_id="",
            dataset_id="",
            pipeline_spec_id="",
            status="completed",
            created_at="2026-05-13T00:00:00Z",
            parameter_hash="hash123",
            artifacts=[],
        )

        with self.assertRaises(jsonschema.ValidationError) as ctx:
            run.validate()

        self.assertIn(list(ctx.exception.path)[0], {"run_id", "dataset_id", "pipeline_spec_id"})
        self.assertIn("should be", ctx.exception.message)

    def test_pipeline_run_schema_rejects_invalid_artifact_record(self):
        from neurobench.models.pipeline import PipelineRun

        artifact = _artifact_payload()
        del artifact["sha256"]
        run = PipelineRun.from_dict(_run_payload())
        run.artifacts = [artifact]

        with self.assertRaises(jsonschema.ValidationError) as ctx:
            run.validate()

        self.assertIn("sha256", ctx.exception.message)


if __name__ == "__main__":
    unittest.main()
