"""Pipeline-spec model."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from neurobench.manifests import load_json, write_json as write_json_file
from neurobench.models.artifacts import ArtifactRecord
from neurobench.validation.schemas import validate_dict


_KNOWN_FIELDS = {
    "schema_version",
    "dataset_id",
    "run_id",
    "label",
    "pipeline",
    "sweep",
    "artifacts",
    "execution",
    "parameters",
    "summary",
    "output_root",
}

_RUN_KNOWN_FIELDS = {
    "schema_version",
    "run_id",
    "dataset_id",
    "pipeline_spec_id",
    "status",
    "created_at",
    "completed_at",
    "parameter_hash",
    "environment",
    "code",
    "artifacts",
    "metrics",
    "warnings",
    "logs",
    "extras",
}


@dataclass
class PipelineSpec:
    """Versioned pipeline specification preserving the public JSON shape."""

    schema_version: int
    dataset_id: str
    run_id: str
    pipeline: list[dict[str, Any]]
    artifacts: dict[str, Any]
    label: str | None = None
    sweep: dict[str, Any] | None = None
    execution: dict[str, Any] | None = None
    parameters: dict[str, Any] | None = None
    summary: dict[str, Any] | None = None
    output_root: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PipelineSpec":
        extras = {key: value for key, value in payload.items() if key not in _KNOWN_FIELDS}
        return cls(
            schema_version=int(payload.get("schema_version", 1)),
            dataset_id=str(payload.get("dataset_id", "")),
            run_id=str(payload.get("run_id", "")),
            label=payload.get("label"),
            pipeline=[dict(step) for step in payload.get("pipeline") or []],
            sweep=dict(payload["sweep"]) if isinstance(payload.get("sweep"), Mapping) else payload.get("sweep"),
            artifacts=dict(payload.get("artifacts") or {}),
            execution=dict(payload["execution"]) if isinstance(payload.get("execution"), Mapping) else payload.get("execution"),
            parameters=dict(payload["parameters"]) if isinstance(payload.get("parameters"), Mapping) else payload.get("parameters"),
            summary=dict(payload["summary"]) if isinstance(payload.get("summary"), Mapping) else payload.get("summary"),
            output_root=payload.get("output_root"),
            extras=extras,
        )

    @classmethod
    def load_json(cls, path: str | Path) -> "PipelineSpec":
        return cls.from_dict(load_json(path))

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "dataset_id": self.dataset_id,
            "run_id": self.run_id,
        }
        if self.label is not None:
            payload["label"] = self.label
        payload["pipeline"] = [dict(step) for step in self.pipeline]
        if self.sweep is not None:
            payload["sweep"] = dict(self.sweep)
        payload["artifacts"] = dict(self.artifacts)
        for key in ("execution", "parameters", "summary", "output_root"):
            value = getattr(self, key)
            if value is not None:
                payload[key] = value
        payload.update(self.extras)
        return payload

    def validate(self) -> None:
        validate_dict(self.to_dict(), "pipeline_spec")

    def write_json(self, path: str | Path) -> None:
        payload = self.to_dict()
        validate_dict(payload, "pipeline_spec")
        write_json_file(path, payload)


@dataclass
class PipelineRun:
    """Versioned reproducible pipeline-run manifest."""

    schema_version: int
    run_id: str
    dataset_id: str
    pipeline_spec_id: str
    status: str
    created_at: str
    parameter_hash: str
    artifacts: list[ArtifactRecord | dict[str, Any]] = field(default_factory=list)
    completed_at: str | None = None
    environment: dict[str, Any] = field(default_factory=dict)
    code: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PipelineRun":
        extras = dict(payload.get("extras") or {})
        extras.update({key: value for key, value in payload.items() if key not in _RUN_KNOWN_FIELDS})
        return cls(
            schema_version=int(payload.get("schema_version", 1)),
            run_id=str(payload.get("run_id", "")),
            dataset_id=str(payload.get("dataset_id", "")),
            pipeline_spec_id=str(payload.get("pipeline_spec_id", "")),
            status=str(payload.get("status", "")),
            created_at=str(payload.get("created_at", "")),
            completed_at=payload.get("completed_at"),
            parameter_hash=str(payload.get("parameter_hash", "")),
            environment=dict(payload.get("environment") or {}),
            code=dict(payload.get("code") or {}),
            artifacts=[
                ArtifactRecord.from_dict(item) if isinstance(item, Mapping) else item
                for item in payload.get("artifacts") or []
            ],
            metrics=dict(payload.get("metrics") or {}),
            warnings=[str(item) for item in payload.get("warnings") or []],
            logs=[str(item) for item in payload.get("logs") or []],
            extras=extras,
        )

    @classmethod
    def load_json(cls, path: str | Path) -> "PipelineRun":
        return cls.from_dict(load_json(path))

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "dataset_id": self.dataset_id,
            "pipeline_spec_id": self.pipeline_spec_id,
            "status": self.status,
            "created_at": self.created_at,
            "parameter_hash": self.parameter_hash,
            "artifacts": [
                artifact.to_dict() if isinstance(artifact, ArtifactRecord) else dict(artifact)
                for artifact in self.artifacts
            ],
            "environment": dict(self.environment),
            "code": dict(self.code),
            "metrics": dict(self.metrics),
            "warnings": list(self.warnings),
            "logs": list(self.logs),
        }
        if self.completed_at is not None:
            payload["completed_at"] = self.completed_at
        if self.extras:
            payload["extras"] = dict(self.extras)
        return payload

    def validate(self) -> None:
        validate_dict(self.to_dict(), "pipeline_run")

    def write_json(self, path: str | Path) -> None:
        payload = self.to_dict()
        validate_dict(payload, "pipeline_run")
        write_json_file(path, payload)
