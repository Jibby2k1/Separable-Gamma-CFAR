"""Metrics-report model."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from neurobench.manifests import load_json, write_json as write_json_file
from neurobench.validation.schemas import validate_dict


_KNOWN_FIELDS = {
    "schema_version",
    "metrics_report_id",
    "dataset_id",
    "run_ids",
    "created_at",
    "metrics",
    "figures",
    "warnings",
    "provenance",
    "extras",
}

_METRIC_SECTIONS = ("pixel_level", "object_level", "event_level", "annotation", "runtime")


@dataclass
class MetricsReport:
    """Versioned scientific metrics report for one or more pipeline runs."""

    schema_version: int
    metrics_report_id: str
    dataset_id: str
    run_ids: list[str]
    created_at: str
    metrics: dict[str, Any] = field(default_factory=dict)
    figures: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MetricsReport":
        extras = dict(payload.get("extras") or {})
        extras.update({key: value for key, value in payload.items() if key not in _KNOWN_FIELDS})
        metrics = dict(payload.get("metrics") or {})
        for section in _METRIC_SECTIONS:
            metrics.setdefault(section, {})
        return cls(
            schema_version=int(payload.get("schema_version", 1)),
            metrics_report_id=str(payload.get("metrics_report_id", "")),
            dataset_id=str(payload.get("dataset_id", "")),
            run_ids=[str(item) for item in payload.get("run_ids") or []],
            created_at=str(payload.get("created_at", "")),
            metrics=metrics,
            figures=[dict(item) for item in payload.get("figures") or []],
            warnings=[str(item) for item in payload.get("warnings") or []],
            provenance=dict(payload.get("provenance") or {}),
            extras=extras,
        )

    @classmethod
    def load_json(cls, path: str | Path) -> "MetricsReport":
        return cls.from_dict(load_json(path))

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "metrics_report_id": self.metrics_report_id,
            "dataset_id": self.dataset_id,
            "run_ids": list(self.run_ids),
            "created_at": self.created_at,
            "metrics": {key: dict(value) if isinstance(value, Mapping) else value for key, value in self.metrics.items()},
            "figures": [dict(item) for item in self.figures],
            "warnings": list(self.warnings),
            "provenance": dict(self.provenance),
        }
        if self.extras:
            payload["extras"] = dict(self.extras)
        return payload

    def validate(self) -> None:
        validate_dict(self.to_dict(), "metrics_report")

    def write_json(self, path: str | Path) -> None:
        payload = self.to_dict()
        validate_dict(payload, "metrics_report")
        write_json_file(path, payload)
