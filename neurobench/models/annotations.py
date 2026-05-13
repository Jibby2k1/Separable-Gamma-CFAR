"""Annotation-set model for reviewed Neurobench decisions."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from neurobench.annotations import default_annotations_v3, migrate_annotations_v3
from neurobench.manifests import load_json, write_json as write_json_file
from neurobench.validation.schemas import validate_dict


@dataclass
class AnnotationSet:
    """Versioned annotation payload normalized to schema v3."""

    payload: dict[str, Any] = field(default_factory=default_annotations_v3)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> "AnnotationSet":
        return cls(migrate_annotations_v3(payload))

    @classmethod
    def load_json(cls, path: str | Path) -> "AnnotationSet":
        return cls.from_dict(load_json(path))

    def to_dict(self) -> dict[str, Any]:
        return migrate_annotations_v3(self.payload)

    def validate(self) -> None:
        validate_dict(self.to_dict(), "annotations")

    def write_json(self, path: str | Path) -> None:
        payload = self.to_dict()
        validate_dict(payload, "annotations")
        write_json_file(path, payload)

    def summary(self) -> dict[str, Any]:
        payload = self.to_dict()
        return {
            "roi_annotations": len(payload.get("rois", {})),
            "event_annotations": len(payload.get("events", {})),
            "suggestion_annotations": len(payload.get("suggestions", {})),
            "virtual_rois": len(payload.get("virtualRois", {})),
            "split_merge_decisions": len(payload.get("splitMergeDecisions", {})),
            "roi_confidence_counts": _count_field(payload.get("rois", {}), "confidence"),
            "event_confidence_counts": _count_field(payload.get("events", {}), "confidence"),
            "reason_tag_counts": _count_reason_tags(payload),
        }


def _count_field(items: Mapping[str, Any], field_name: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items.values():
        if not isinstance(item, Mapping):
            continue
        value = str(item.get(field_name) or "unlabeled")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _count_reason_tags(payload: Mapping[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for group_name in ("rois", "events", "suggestions", "virtualRois", "splitMergeDecisions"):
        for item in dict(payload.get(group_name) or {}).values():
            if not isinstance(item, Mapping):
                continue
            for tag in item.get("reason_tags") or []:
                key = str(tag)
                counts[key] = counts.get(key, 0) + 1
    return counts
