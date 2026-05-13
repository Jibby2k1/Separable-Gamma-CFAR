"""Dataset manifest model."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from neurobench.manifests import load_json, write_json as write_json_file
from neurobench.validation.schemas import validate_dict


_KNOWN_FIELDS = {
    "schema_version",
    "dataset_id",
    "name",
    "modality",
    "indicator",
    "frame_rate_hz",
    "pixel_size_microns",
    "behavior",
    "online",
    "paths",
}


@dataclass
class DatasetManifest:
    """Versioned dataset manifest preserving the public JSON shape."""

    schema_version: int
    dataset_id: str
    paths: dict[str, str]
    name: str | None = None
    modality: str | None = None
    indicator: str | None = None
    frame_rate_hz: float | None = None
    pixel_size_microns: float | None = None
    behavior: dict[str, Any] | None = None
    online: dict[str, Any] | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DatasetManifest":
        extras = {key: value for key, value in payload.items() if key not in _KNOWN_FIELDS}
        return cls(
            schema_version=int(payload.get("schema_version", 1)),
            dataset_id=str(payload.get("dataset_id", "")),
            name=payload.get("name"),
            modality=payload.get("modality"),
            indicator=payload.get("indicator"),
            frame_rate_hz=payload.get("frame_rate_hz"),
            pixel_size_microns=payload.get("pixel_size_microns"),
            behavior=dict(payload["behavior"]) if isinstance(payload.get("behavior"), Mapping) else payload.get("behavior"),
            online=dict(payload["online"]) if isinstance(payload.get("online"), Mapping) else payload.get("online"),
            paths=dict(payload.get("paths") or {}),
            extras=extras,
        )

    @classmethod
    def load_json(cls, path: str | Path) -> "DatasetManifest":
        return cls.from_dict(load_json(path))

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "dataset_id": self.dataset_id,
        }
        for key in ("name", "modality", "indicator", "frame_rate_hz", "pixel_size_microns", "behavior", "online"):
            value = getattr(self, key)
            if value is not None:
                payload[key] = value
        payload["paths"] = dict(self.paths)
        payload.update(self.extras)
        return payload

    def validate(self) -> None:
        validate_dict(self.to_dict(), "dataset")

    def write_json(self, path: str | Path) -> None:
        payload = self.to_dict()
        validate_dict(payload, "dataset")
        write_json_file(path, payload)
