"""Structured run logging for reproducible pipeline execution."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from neurobench.models.pipeline import PipelineRun
from neurobench.pipelines.artifacts import create_run_layout


class RunLogger:
    """Write human-readable and machine-readable logs under a run root."""

    def __init__(self, run_root: str | Path, pipeline_run: PipelineRun | None = None):
        self.run_root = Path(run_root)
        self.pipeline_run = pipeline_run
        self.paths = create_run_layout(self.run_root, pipeline_run)
        self.log_path = self.paths["logs"] / "run.log"
        self.events_path = self.paths["logs"] / "events.jsonl"
        if pipeline_run is not None:
            self._record_manifest_log(self.log_path)
            self._record_manifest_log(self.events_path)
            pipeline_run.write_json(self.paths["pipeline_run"])

    def info(self, message: str, **fields: Any) -> dict[str, Any]:
        return self.log("info", message, **fields)

    def warning(self, message: str, **fields: Any) -> dict[str, Any]:
        event = self.log("warning", message, **fields)
        if self.pipeline_run is not None and message not in self.pipeline_run.warnings:
            self.pipeline_run.warnings.append(message)
            self.pipeline_run.write_json(self.paths["pipeline_run"])
        return event

    def error(self, message: str, **fields: Any) -> dict[str, Any]:
        return self.log("error", message, **fields)

    def stage_started(self, stage_id: str, **fields: Any) -> dict[str, Any]:
        return self.log("info", f"stage started: {stage_id}", stage_id=stage_id, event_type="stage_started", **fields)

    def stage_completed(self, stage_id: str, **fields: Any) -> dict[str, Any]:
        return self.log("info", f"stage completed: {stage_id}", stage_id=stage_id, event_type="stage_completed", **fields)

    def stage_failed(self, stage_id: str, message: str, **fields: Any) -> dict[str, Any]:
        return self.log("error", message, stage_id=stage_id, event_type="stage_failed", **fields)

    def log(self, level: str, message: str, **fields: Any) -> dict[str, Any]:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": str(level).lower(),
            "message": str(message),
        }
        if self.pipeline_run is not None:
            event["run_id"] = self.pipeline_run.run_id
        event.update(_json_safe(fields))
        self._append_text(event)
        self._append_json(event)
        return event

    def _append_text(self, event: dict[str, Any]) -> None:
        suffix_parts = []
        for key in ("event_type", "stage_id"):
            if key in event:
                suffix_parts.append(f"{key}={event[key]}")
        suffix = f" ({', '.join(suffix_parts)})" if suffix_parts else ""
        line = f"{event['timestamp']} {event['level'].upper()} {event['message']}{suffix}\n"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line)

    def _append_json(self, event: dict[str, Any]) -> None:
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")

    def _record_manifest_log(self, path: Path) -> None:
        if self.pipeline_run is None:
            return
        try:
            value = path.resolve().relative_to(self.run_root.resolve()).as_posix()
        except ValueError:
            value = str(path.resolve())
        if value not in self.pipeline_run.logs:
            self.pipeline_run.logs.append(value)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        return sorted(_json_safe(item) for item in value)
    if isinstance(value, Path):
        return value.as_posix()
    if hasattr(value, "item") and callable(value.item):
        return _json_safe(value.item())
    return value
