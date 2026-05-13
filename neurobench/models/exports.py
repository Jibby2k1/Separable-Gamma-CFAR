"""Export-bundle model."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from neurobench.manifests import load_json, write_json as write_json_file
from neurobench.validation.schemas import validate_dict


ALIGNMENT_STATUSES = frozenset({"not_provided", "provided_unvalidated", "validated", "failed"})

_KNOWN_FIELDS = {
    "schema_version",
    "export_bundle_id",
    "dataset_id",
    "run_ids",
    "created_at",
    "profile",
    "selection_policy",
    "alignment_status",
    "alignment",
    "files",
    "checksums",
    "warnings",
    "provenance",
    "extras",
}


@dataclass
class ExportBundle:
    """Versioned manifest for downstream Neurobench exports."""

    schema_version: int
    export_bundle_id: str
    dataset_id: str
    run_ids: list[str]
    created_at: str
    selection_policy: dict[str, Any]
    alignment_status: str = "not_provided"
    profile: str = "accepted_only"
    alignment: dict[str, Any] = field(default_factory=dict)
    files: list[dict[str, Any]] = field(default_factory=list)
    checksums: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExportBundle":
        extras = dict(payload.get("extras") or {})
        extras.update({key: value for key, value in payload.items() if key not in _KNOWN_FIELDS})
        return cls(
            schema_version=int(payload.get("schema_version", 1)),
            export_bundle_id=str(payload.get("export_bundle_id", "")),
            dataset_id=str(payload.get("dataset_id", "")),
            run_ids=[str(item) for item in payload.get("run_ids") or []],
            created_at=str(payload.get("created_at", "")),
            profile=str(payload.get("profile", "accepted_only")),
            selection_policy=dict(payload.get("selection_policy") or {}),
            alignment_status=str(payload.get("alignment_status", "not_provided")),
            alignment=dict(payload.get("alignment") or {}),
            files=[dict(item) for item in payload.get("files") or []],
            checksums={str(key): str(value) for key, value in dict(payload.get("checksums") or {}).items()},
            warnings=[str(item) for item in payload.get("warnings") or []],
            provenance=dict(payload.get("provenance") or {}),
            extras=extras,
        )

    @classmethod
    def load_json(cls, path: str | Path) -> "ExportBundle":
        return cls.from_dict(load_json(path))

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "export_bundle_id": self.export_bundle_id,
            "dataset_id": self.dataset_id,
            "run_ids": list(self.run_ids),
            "created_at": self.created_at,
            "profile": self.profile,
            "selection_policy": dict(self.selection_policy),
            "alignment_status": self.alignment_status,
            "alignment": dict(self.alignment),
            "files": [dict(item) for item in self.files],
            "checksums": dict(self.checksums),
            "warnings": list(self.warnings),
            "provenance": dict(self.provenance),
        }
        if self.extras:
            payload["extras"] = dict(self.extras)
        return payload

    def validate(self) -> None:
        if self.alignment_status not in ALIGNMENT_STATUSES:
            raise ValueError(f"Invalid alignment_status: {self.alignment_status}")
        validate_dict(self.to_dict(), "export_bundle")

    def write_json(self, path: str | Path) -> None:
        payload = self.to_dict()
        validate_dict(payload, "export_bundle")
        write_json_file(path, payload)
