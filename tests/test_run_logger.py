from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


def _pipeline_run():
    from neurobench.models.pipeline import PipelineRun

    return PipelineRun(
        schema_version=1,
        run_id="run_logger_001",
        dataset_id="dataset_001",
        pipeline_spec_id="spec_001",
        status="running",
        created_at="2026-05-13T00:00:00Z",
        parameter_hash="hash123",
        artifacts=[],
    )


class RunLoggerTests(unittest.TestCase):
    def test_run_logger_creates_text_and_jsonl_logs(self):
        from neurobench.logging import RunLogger

        with tempfile.TemporaryDirectory() as tmp:
            logger = RunLogger(Path(tmp) / "run", _pipeline_run())
            event = logger.info("run initialized", device="cpu")

            text = logger.log_path.read_text(encoding="utf-8")
            json_event = json.loads(logger.events_path.read_text(encoding="utf-8").strip())

            self.assertEqual(event["message"], "run initialized")
            self.assertIn("INFO run initialized", text)
            self.assertEqual(json_event["message"], "run initialized")
            self.assertEqual(json_event["device"], "cpu")
            self.assertEqual(json_event["run_id"], "run_logger_001")

    def test_run_logger_records_log_paths_in_pipeline_manifest(self):
        from neurobench.logging import RunLogger

        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run"
            logger = RunLogger(run_root, _pipeline_run())
            logger.info("ready")
            manifest = json.loads((run_root / "pipeline_run.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["logs"], ["logs/run.log", "logs/events.jsonl"])

    def test_run_logger_stage_helpers_write_event_types(self):
        from neurobench.logging import RunLogger

        with tempfile.TemporaryDirectory() as tmp:
            logger = RunLogger(Path(tmp) / "run")
            logger.stage_started("dataset_qc")
            logger.stage_completed("dataset_qc", outputs=["qc_summary"])

            events = [
                json.loads(line)
                for line in logger.events_path.read_text(encoding="utf-8").splitlines()
            ]

            self.assertEqual([event["event_type"] for event in events], ["stage_started", "stage_completed"])
            self.assertEqual(events[1]["outputs"], ["qc_summary"])

    def test_run_logger_warning_updates_pipeline_manifest_once(self):
        from neurobench.logging import RunLogger

        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run"
            logger = RunLogger(run_root, _pipeline_run())
            logger.warning("input checksum missing", path_id="raw_video")
            logger.warning("input checksum missing", path_id="raw_video")
            manifest = json.loads((run_root / "pipeline_run.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["warnings"], ["input checksum missing"])


if __name__ == "__main__":
    unittest.main()
