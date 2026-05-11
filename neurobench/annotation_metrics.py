"""Annotation-driven summary metrics for partial review sessions."""
from __future__ import annotations

from typing import Any, Mapping

from neurobench.annotations import migrate_annotations_v3


TRIAGE_CATEGORY_NAMES = (
    "strong_neuron",
    "possible_missed_neuron",
    "artifact_like",
    "merged_cluster",
    "weak_trace",
    "needs_event_review",
)

def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _is_empty_label(value: Any) -> bool:
    if value is None:
        return True
    return str(value).strip().lower() in {"", "none", "n/a", "na"}


def _triage_bucket() -> dict[str, Any]:
    return {
        "count": 0,
        "roi_ids": [],
        "event_ids": [],
        "suggestion_ids": [],
        "virtual_roi_ids": [],
    }


def _add_id(bucket: dict[str, Any], field: str, value: Any) -> None:
    item = str(value)
    if item not in bucket[field]:
        bucket[field].append(item)
        bucket["count"] += 1


def compute_triage_categories(review_data: Mapping[str, Any], annotations: Mapping[str, Any]) -> dict[str, Any]:
    """Return queue-ready category counts and IDs from review data plus annotations."""
    ann = migrate_annotations_v3(annotations)
    rois = list(review_data.get("rois", []))
    suggestions = list(review_data.get("discovery", {}).get("suggestions", []))
    categories = {name: _triage_bucket() for name in TRIAGE_CATEGORY_NAMES}

    identity_groups: dict[str, list[str]] = {}
    for roi in rois:
        roi_id = str(roi.get("id"))
        item = ann["rois"].get(roi_id, {})
        identity_group = str(item.get("identity_group") or "").strip()
        if identity_group:
            identity_groups.setdefault(identity_group, []).append(roi_id)

    grouped_roi_ids = {roi_id for ids in identity_groups.values() if len(ids) > 1 for roi_id in ids}

    for roi in rois:
        roi_id = str(roi.get("id"))
        item = ann["rois"].get(roi_id, {})
        cell_state = item.get("cell_state") or "unlabeled"
        trace_quality = item.get("trace_quality") or ""
        control_ready = item.get("control_ready") or ""
        artifact_class = item.get("artifact_class")
        needs_action = str(item.get("needs_action") or "").strip().lower()
        artifact_score = _as_float(roi.get("artifactScore"), 0.0)

        if (
            cell_state == "accepted"
            and trace_quality == "good"
            and control_ready in {"yes", "maybe"}
            and _is_empty_label(artifact_class)
            and artifact_score < 0.4
        ):
            _add_id(categories["strong_neuron"], "roi_ids", roi_id)

        if not _is_empty_label(artifact_class) or artifact_score >= 0.4:
            _add_id(categories["artifact_like"], "roi_ids", roi_id)

        if "merge" in needs_action or roi_id in grouped_roi_ids:
            _add_id(categories["merged_cluster"], "roi_ids", roi_id)

        if trace_quality in {"weak", "noisy", "unusable"}:
            _add_id(categories["weak_trace"], "roi_ids", roi_id)

        for event in roi.get("events", []):
            frame = event.get("frame")
            event_id = f"{roi_id}:{frame}"
            event_item = ann["events"].get(event_id, {})
            event_state = event_item.get("event_state") or "unlabeled"
            event_type = str(event_item.get("event_type") or "").strip().lower()
            timing_quality = event_item.get("timing_quality") or ""
            if (
                event_state in {"unlabeled", "unsure"}
                or event_type == "weak"
                or timing_quality in {"ambiguous", "slow_transient"}
            ):
                _add_id(categories["needs_event_review"], "event_ids", event_id)

    for virtual_id, virtual in ann.get("virtualRois", {}).items():
        if virtual.get("roi_kind") == "virtual_merge" or virtual.get("source_roi_ids"):
            _add_id(categories["merged_cluster"], "virtual_roi_ids", virtual_id)

    for suggestion in suggestions:
        suggestion_id = str(suggestion.get("id"))
        item = ann["suggestions"].get(suggestion_id, {})
        state = "promoted" if suggestion_id in ann.get("promotedRois", {}) else item.get("state") or "unlabeled"
        artifact_class = item.get("artifact_class", item.get("artifactClass"))
        artifact_cue = suggestion.get("artifactCue")
        artifact_score = _as_float(suggestion.get("artifactScore"), 0.0)

        if state in {"missed", "promoted"}:
            _add_id(categories["possible_missed_neuron"], "suggestion_ids", suggestion_id)

        if (
            state == "artifact"
            or not _is_empty_label(artifact_class)
            or not _is_empty_label(artifact_cue)
            or artifact_score >= 0.4
        ):
            _add_id(categories["artifact_like"], "suggestion_ids", suggestion_id)

    return categories


def compute_annotation_summary(review_data: Mapping[str, Any], annotations: Mapping[str, Any]) -> dict[str, Any]:
    ann = migrate_annotations_v3(annotations)
    rois = list(review_data.get("rois", []))
    suggestions = list(review_data.get("discovery", {}).get("suggestions", []))
    events = []
    for roi in rois:
        for event in roi.get("events", []):
            events.append((roi.get("id"), event.get("frame")))

    roi_states = {"accepted": 0, "rejected": 0, "unsure": 0, "unlabeled": 0}
    trace_quality = {"good": 0, "weak": 0, "noisy": 0, "unusable": 0, "unlabeled": 0}
    control_ready = {"yes": 0, "maybe": 0, "no": 0, "unlabeled": 0}
    for roi in rois:
        item = ann["rois"].get(str(roi.get("id")), {})
        state = item.get("cell_state") or "unlabeled"
        roi_states[state if state in roi_states else "unlabeled"] += 1
        tq = item.get("trace_quality") or "unlabeled"
        trace_quality[tq if tq in trace_quality else "unlabeled"] += 1
        cr = item.get("control_ready") or "unlabeled"
        control_ready[cr if cr in control_ready else "unlabeled"] += 1

    event_states = {"accepted": 0, "rejected": 0, "unsure": 0, "unlabeled": 0}
    for roi_id, frame in events:
        item = ann["events"].get(f"{roi_id}:{frame}", {})
        state = item.get("event_state") or "unlabeled"
        event_states[state if state in event_states else "unlabeled"] += 1

    suggestion_states = {"promoted": 0, "missed": 0, "artifact": 0, "unsure": 0, "unlabeled": 0}
    for suggestion in suggestions:
        item = ann["suggestions"].get(str(suggestion.get("id")), {})
        state = "promoted" if str(suggestion.get("id")) in ann.get("promotedRois", {}) else item.get("state") or "unlabeled"
        suggestion_states[state if state in suggestion_states else "unlabeled"] += 1

    triage_categories = compute_triage_categories(review_data, ann)

    return {
        "roi_count": len(rois),
        "event_count": len(events),
        "suggestion_count": len(suggestions),
        "roi_states": roi_states,
        "event_states": event_states,
        "suggestion_states": suggestion_states,
        "trace_quality": trace_quality,
        "control_ready": control_ready,
        "triage_categories": triage_categories,
        "triage_queue_counts": {
            name: triage_categories[name]["count"] for name in TRIAGE_CATEGORY_NAMES
        },
        "review_burden": {
            "candidate_rois_per_accepted_roi": len(rois) / max(1, roi_states["accepted"]),
            "candidate_events_per_accepted_event": len(events) / max(1, event_states["accepted"]),
        },
    }
