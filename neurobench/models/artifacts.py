"""Artifact record model."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from neurobench.manifests import load_json, write_json as write_json_file
from neurobench.validation.schemas import validate_dict


_KNOWN_FIELDS = {
    "schema_version",
    "artifact_id",
    "kind",
    "path",
    "schema",
    "producer_stage",
    "created_at",
    "sha256",
    "summary",
    "extras",
}


@dataclass
class ArtifactRecord:
    """Versioned record for a produced file or artifact."""

    schema_version: int
    artifact_id: str
    kind: str
    path: str
    producer_stage: str
    sha256: str
    schema: str | None = None
    created_at: str | None = None
    summary: dict[str, Any] = field(default_factory=dict)
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ArtifactRecord":
        extras = dict(payload.get("extras") or {})
        extras.update({key: value for key, value in payload.items() if key not in _KNOWN_FIELDS})
        return cls(
            schema_version=int(payload.get("schema_version", 1)),
            artifact_id=str(payload.get("artifact_id", "")),
            kind=str(payload.get("kind", "")),
            path=str(payload.get("path", "")),
            schema=payload.get("schema"),
            producer_stage=str(payload.get("producer_stage", "")),
            created_at=payload.get("created_at"),
            sha256=str(payload.get("sha256", "")),
            summary=dict(payload.get("summary") or {}),
            extras=extras,
        )

    @classmethod
    def load_json(cls, path: str | Path) -> "ArtifactRecord":
        return cls.from_dict(load_json(path))

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "path": self.path,
            "producer_stage": self.producer_stage,
            "sha256": self.sha256,
        }
        if self.schema is not None:
            payload["schema"] = self.schema
        if self.created_at is not None:
            payload["created_at"] = self.created_at
        payload["summary"] = dict(self.summary)
        if self.extras:
            payload["extras"] = dict(self.extras)
        return payload

    def validate(self) -> None:
        validate_dict(self.to_dict(), "artifact_record")

    def write_json(self, path: str | Path) -> None:
        payload = self.to_dict()
        validate_dict(payload, "artifact_record")
        write_json_file(path, payload)
