"""Annotation schema migration helpers."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


ROI_STATE_MAP = {"accept": "accepted", "reject": "rejected", "unsure": "unsure", "": ""}
EVENT_STATE_MAP = {"accept": "accepted", "reject": "rejected", "unsure": "unsure", "": ""}


def default_annotations_v3() -> dict[str, Any]:
    return {
        "schema_version": 3,
        "updatedAt": None,
        "rois": {},
        "events": {},
        "suggestions": {},
        "promotedRois": {},
        "virtualRois": {},
        "reviewStats": {"sessionStartedAt": None, "lastActionAt": None, "actions": {}},
        "settings": {},
    }


def migrate_annotations_v3(incoming: Mapping[str, Any] | None) -> dict[str, Any]:
    src = deepcopy(dict(incoming or {}))
    migrated = default_annotations_v3()
    migrated.update({k: v for k, v in src.items() if k not in {"version", "schema_version", "rois", "events", "suggestions"}})
    migrated["schema_version"] = 3
    migrated.pop("version", None)

    migrated["rois"] = {}
    for roi_id, ann in dict(src.get("rois", {})).items():
        item = dict(ann or {})
        state = item.get("cell_state", ROI_STATE_MAP.get(item.get("state", ""), item.get("state", "")))
        item.setdefault("state", item.get("state", ""))
        item.setdefault("cell_state", state)
        item.setdefault("trace_quality", "")
        item.setdefault("control_ready", "")
        item.setdefault("artifact_class", "")
        item.setdefault("identity_group", "")
        item.setdefault("needs_action", "")
        migrated["rois"][str(roi_id)] = item

    migrated["events"] = {}
    for event_id, ann in dict(src.get("events", {})).items():
        item = dict(ann or {})
        state = item.get("event_state", EVENT_STATE_MAP.get(item.get("state", ""), item.get("state", "")))
        item.setdefault("state", item.get("state", ""))
        item.setdefault("event_state", state)
        item.setdefault("event_type", "")
        item.setdefault("timing_quality", "")
        migrated["events"][str(event_id)] = item

    migrated["suggestions"] = {str(k): dict(v or {}) for k, v in dict(src.get("suggestions", {})).items()}
    migrated["promotedRois"] = dict(src.get("promotedRois", {}))
    migrated["virtualRois"] = {str(k): dict(v or {}) for k, v in dict(src.get("virtualRois", {})).items()}
    migrated["reviewStats"] = dict(src.get("reviewStats", migrated["reviewStats"]))
    migrated["reviewStats"]["actions"] = dict(migrated["reviewStats"].get("actions", {}))
    migrated["settings"] = dict(src.get("settings", {}))
    return migrated
