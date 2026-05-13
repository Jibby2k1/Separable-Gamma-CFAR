"""Review-data model for browser workbench payloads."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from neurobench.manifests import load_json, write_json as write_json_file
from neurobench.validation.schemas import validate_dict


_KNOWN_FIELDS = {
    "schema_version",
    "dataset",
    "video",
    "parameters",
    "qc",
    "discovery",
    "rois",
}


@dataclass
class ReviewData:
    """Versioned review-workbench data preserving the public JSON shape."""

    video: dict[str, Any]
    parameters: dict[str, Any]
    rois: list[dict[str, Any]]
    schema_version: int | None = None
    dataset: dict[str, Any] | None = None
    qc: dict[str, Any] | None = None
    discovery: dict[str, Any] | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReviewData":
        extras = {key: value for key, value in payload.items() if key not in _KNOWN_FIELDS}
        return cls(
            schema_version=int(payload["schema_version"]) if payload.get("schema_version") is not None else None,
            dataset=dict(payload["dataset"]) if isinstance(payload.get("dataset"), Mapping) else payload.get("dataset"),
            video=dict(payload.get("video") or {}),
            parameters=dict(payload.get("parameters") or {}),
            qc=dict(payload["qc"]) if isinstance(payload.get("qc"), Mapping) else payload.get("qc"),
            discovery=dict(payload["discovery"]) if isinstance(payload.get("discovery"), Mapping) else payload.get("discovery"),
            rois=[dict(roi) if isinstance(roi, Mapping) else roi for roi in payload.get("rois") or []],
            extras=extras,
        )

    @classmethod
    def load_json(cls, path: str | Path) -> "ReviewData":
        return cls.from_dict(load_json(path))

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.schema_version is not None:
            payload["schema_version"] = self.schema_version
        if self.dataset is not None:
            payload["dataset"] = dict(self.dataset)
        payload["video"] = dict(self.video)
        payload["parameters"] = dict(self.parameters)
        if self.qc is not None:
            payload["qc"] = dict(self.qc)
        if self.discovery is not None:
            payload["discovery"] = dict(self.discovery)
        payload["rois"] = [dict(roi) if isinstance(roi, Mapping) else roi for roi in self.rois]
        payload.update(self.extras)
        return payload

    @property
    def dataset_id(self) -> str:
        dataset_id = (self.dataset or {}).get("dataset_id") or self.parameters.get("datasetId")
        return str(dataset_id or self.video.get("name") or "")

    def summary(self) -> dict[str, Any]:
        """Return concise counts for reporting, indexing, and QC surfaces."""
        events = 0
        for roi in self.rois:
            if isinstance(roi, Mapping):
                events += len(roi.get("events") or [])
        suggestions = 0
        if isinstance(self.discovery, Mapping):
            suggestions = len(self.discovery.get("suggestions") or [])
        return {
            "dataset_id": self.dataset_id,
            "video_name": self.video.get("name"),
            "width": self.video.get("width"),
            "height": self.video.get("height"),
            "frames": self.video.get("frames"),
            "roi_count": len(self.rois),
            "event_count": events,
            "suggestion_count": suggestions,
        }

    def validate(self) -> None:
        validate_dict(self.to_dict(), "review_data")

    def write_json(self, path: str | Path) -> None:
        payload = self.to_dict()
        validate_dict(payload, "review_data")
        write_json_file(path, payload)
