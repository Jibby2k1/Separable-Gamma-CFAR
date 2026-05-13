"""Deterministic next-review batch selection for annotation sessions."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from neurobench.annotations import migrate_annotations_v3


DEFAULT_TARGET_ROIS = 30
DEFAULT_TARGET_EVENTS = 30
DEFAULT_TARGET_SUGGESTIONS = 15
DEFAULT_TUNING_READY_ROIS = 20
DEFAULT_TUNING_READY_EVENTS = 20
GUIDED_REVIEW_QUEUE_IDS = (
    "unreviewed_high_priority",
    "uncertain",
    "likely_artifact",
    "possible_missed_neuron",
    "needs_second_reviewer",
)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _state(ann: Mapping[str, Any], primary: str, legacy: str) -> str:
    value = ann.get(primary) or ann.get(legacy) or ""
    return str(value).strip().lower()


def _is_reviewed(value: str) -> bool:
    return value in {"accepted", "rejected", "unsure", "accept", "reject"}


def _event_key(roi_id: Any, frame: Any) -> str:
    return f"{roi_id}:{frame}"


def _event_count(roi: Mapping[str, Any]) -> int:
    return len(list(roi.get("events", []) or []))


def roi_priority_score(roi: Mapping[str, Any], ann: Mapping[str, Any] | None = None) -> tuple[float, list[str]]:
    """Return a transparent review-priority score and short reason strings."""
    annotation = dict(ann or {})
    event_count = _event_count(roi)
    trace_snr = _as_float(roi.get("traceSnr"), 0.0)
    local_corr = _as_float(roi.get("localCorrelationMean"), 0.0)
    event_support = _as_float(roi.get("eventSupport"), 0.0)
    artifact_score = _as_float(roi.get("artifactScore"), 0.0)
    raw_priority = _as_float(roi.get("priorityScore"), 0.0)
    area = _as_float(roi.get("area"), 0.0)
    score = raw_priority
    score += min(event_count, 8) * 0.45
    score += min(max(trace_snr, 0.0), 6.0) * 0.25
    score += min(max(local_corr, 0.0), 1.0) * 1.2
    score += min(max(event_support, 0.0), 1.0) * 1.1
    score -= min(max(artifact_score, 0.0), 1.0) * 1.6
    if not _is_reviewed(_state(annotation, "cell_state", "state")):
        score += 2.0
    if annotation.get("needs_action"):
        score += 0.6
    if 20 <= area <= 180:
        score += 0.35

    reasons: list[str] = []
    if not _is_reviewed(_state(annotation, "cell_state", "state")):
        reasons.append("unlabeled ROI")
    if event_count:
        reasons.append(f"{event_count} candidate events")
    if trace_snr >= 1.5:
        reasons.append("usable trace SNR")
    elif trace_snr > 0:
        reasons.append("weak trace SNR")
    if local_corr >= 0.4:
        reasons.append("locally coherent")
    elif local_corr > 0:
        reasons.append("low local coherence")
    if event_support >= 0.35:
        reasons.append("event-supported footprint")
    if artifact_score >= 0.4:
        reasons.append("artifact risk")
    if annotation.get("needs_action"):
        reasons.append(f"needs {annotation.get('needs_action')}")
    return score, reasons or ["baseline candidate"]


def suggestion_priority_score(suggestion: Mapping[str, Any], ann: Mapping[str, Any] | None = None) -> tuple[float, list[str]]:
    annotation = dict(ann or {})
    raw_priority = _as_float(suggestion.get("priorityScore"), _as_float(suggestion.get("discoveryScore"), 0.0))
    artifact_score = _as_float(suggestion.get("artifactScore"), 0.0)
    local_corr = _as_float(suggestion.get("localCorrelationMean"), 0.0)
    event_support = _as_float(suggestion.get("eventSupport"), 0.0)
    state = str(annotation.get("state") or "").strip().lower()
    score = raw_priority + local_corr * 0.8 + event_support * 0.8
    if not state:
        score += 1.5
    if artifact_score >= 0.4 or suggestion.get("artifactCue") not in {None, "", "none"}:
        score += 0.7

    reasons: list[str] = []
    if not state:
        reasons.append("unlabeled suggestion")
    if artifact_score >= 0.4 or suggestion.get("artifactCue") not in {None, "", "none"}:
        reasons.append("artifact check")
    if local_corr >= 0.4:
        reasons.append("locally coherent")
    if event_support >= 0.35:
        reasons.append("event-supported")
    return score, reasons or ["discovery candidate"]


def _roi_category(roi: Mapping[str, Any], ann: Mapping[str, Any]) -> str:
    state = _state(ann, "cell_state", "state")
    if not _is_reviewed(state):
        if _as_float(roi.get("artifactScore"), 0.0) >= 0.4:
            return "artifact_check"
        if _as_float(roi.get("traceSnr"), 99.0) < 1.5:
            return "weak_trace_check"
        if _event_count(roi):
            return "event_supported_unlabeled"
        return "unlabeled_roi"
    if state == "accepted" and ann.get("control_ready") in {"", None, "unsure"}:
        return "control_readiness_check"
    return "reviewed_followup"


def build_annotation_batch(
    review_data: Mapping[str, Any],
    annotations: Mapping[str, Any] | None,
    *,
    target_rois: int = DEFAULT_TARGET_ROIS,
    target_events: int = DEFAULT_TARGET_EVENTS,
    target_suggestions: int = DEFAULT_TARGET_SUGGESTIONS,
) -> dict[str, Any]:
    """Select the next high-value ROIs, events, and suggestions to annotate."""
    ann = migrate_annotations_v3(annotations)
    rois = list(review_data.get("rois", []) or [])
    suggestions = list(review_data.get("discovery", {}).get("suggestions", []) or [])

    roi_rows: list[dict[str, Any]] = []
    for roi in rois:
        roi_id = str(roi.get("id"))
        roi_ann = ann["rois"].get(roi_id, {})
        score, reasons = roi_priority_score(roi, roi_ann)
        if not _is_reviewed(_state(roi_ann, "cell_state", "state")) or roi_ann.get("needs_action"):
            roi_rows.append(
                {
                    "roi_id": roi_id,
                    "score": round(score, 4),
                    "category": _roi_category(roi, roi_ann),
                    "event_count": _event_count(roi),
                    "area": roi.get("area"),
                    "trace_snr": roi.get("traceSnr"),
                    "artifact_score": roi.get("artifactScore"),
                    "reasons": reasons,
                }
            )
    roi_rows.sort(key=lambda row: (-_as_float(row["score"]), row["roi_id"]))

    selected_roi_ids = {row["roi_id"] for row in roi_rows[:target_rois]}
    event_rows = _rank_events(rois, ann, selected_roi_ids, target_events)

    suggestion_rows: list[dict[str, Any]] = []
    for suggestion in suggestions:
        suggestion_id = str(suggestion.get("id"))
        suggestion_ann = ann["suggestions"].get(suggestion_id, {})
        state = str(suggestion_ann.get("state") or "").strip().lower()
        if state or suggestion_id in ann.get("promotedRois", {}):
            continue
        score, reasons = suggestion_priority_score(suggestion, suggestion_ann)
        suggestion_rows.append(
            {
                "suggestion_id": suggestion_id,
                "score": round(score, 4),
                "area": suggestion.get("area"),
                "artifact_score": suggestion.get("artifactScore"),
                "artifact_cue": suggestion.get("artifactCue"),
                "reasons": reasons,
            }
        )
    suggestion_rows.sort(key=lambda row: (-_as_float(row["score"]), row["suggestion_id"]))

    batch = {
        "targets": {
            "rois": int(target_rois),
            "events": int(target_events),
            "suggestions": int(target_suggestions),
        },
        "rois": roi_rows[:target_rois],
        "events": event_rows,
        "suggestions": suggestion_rows[:target_suggestions],
    }
    batch["tasks"] = build_review_tasks(review_data, ann, batch=batch)
    return batch


def _reason_codes(reasons: Sequence[Any]) -> list[str]:
    codes = []
    for reason in reasons:
        text = str(reason).lower()
        if "unlabeled roi" in text:
            codes.append("unlabeled_roi")
        elif "unlabeled event" in text:
            codes.append("unlabeled_event")
        elif "unlabeled suggestion" in text:
            codes.append("unlabeled_suggestion")
        elif "artifact" in text:
            codes.append("artifact_check")
        elif "coherent" in text:
            codes.append("local_coherence")
        elif "event" in text:
            codes.append("event_support")
        elif "snr" in text:
            codes.append("trace_snr")
        elif "needs" in text:
            codes.append("needs_action")
    return sorted(set(codes))


def _task_prompt(task_type: str, row: Mapping[str, Any]) -> str:
    if task_type == "roi":
        category = str(row.get("category", "candidate")).replace("_", " ")
        return f"Decide whether ROI {row.get('roi_id')} is a neuron, artifact, or unsure case ({category})."
    if task_type == "event":
        return f"Review ROI {row.get('roi_id')} event at frame {row.get('frame')}."
    return f"Check whether suggestion {row.get('suggestion_id')} is a missed neuron or artifact."


def build_review_tasks(
    review_data: Mapping[str, Any],
    annotations: Mapping[str, Any] | None,
    *,
    batch: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build typed guided-review tasks from a selected annotation batch."""
    ann = migrate_annotations_v3(annotations)
    selected = dict(batch or build_annotation_batch(review_data, ann))
    tasks: list[dict[str, Any]] = []

    for row in selected.get("rois", []) or []:
        roi_id = str(row.get("roi_id"))
        tasks.append(
            {
                "task_id": f"roi:{roi_id}",
                "task_type": "roi",
                "subject_id": roi_id,
                "priority_score": row.get("score"),
                "prompt": _task_prompt("roi", row),
                "reason_codes": _reason_codes(row.get("reasons", [])),
                "reasons": list(row.get("reasons", [])),
                "recommended_context": ["video", "roi_crop", "trace", "event_filmstrip", "evidence_map"],
            }
        )

    for row in selected.get("events", []) or []:
        roi_id = str(row.get("roi_id"))
        frame = row.get("frame")
        tasks.append(
            {
                "task_id": f"event:{roi_id}:{frame}",
                "task_type": "event",
                "subject_id": f"{roi_id}:{frame}",
                "roi_id": roi_id,
                "frame": frame,
                "priority_score": row.get("score"),
                "prompt": _task_prompt("event", row),
                "reason_codes": _reason_codes(row.get("reasons", [])),
                "reasons": list(row.get("reasons", [])),
                "recommended_context": ["video", "trace", "event_filmstrip"],
            }
        )

    for row in selected.get("suggestions", []) or []:
        suggestion_id = str(row.get("suggestion_id"))
        tasks.append(
            {
                "task_id": f"suggestion:{suggestion_id}",
                "task_type": "suggestion",
                "subject_id": suggestion_id,
                "priority_score": row.get("score"),
                "prompt": _task_prompt("suggestion", row),
                "reason_codes": _reason_codes(row.get("reasons", [])),
                "reasons": list(row.get("reasons", [])),
                "recommended_context": ["video", "evidence_map", "suggestion_overlay"],
            }
        )

    tasks.sort(key=lambda task: (-_as_float(task.get("priority_score")), task["task_id"]))
    return tasks


def review_task_feature_rows(review_data: Mapping[str, Any], annotations: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Return feature rows suitable for active-learning experiments."""
    ann = migrate_annotations_v3(annotations)
    rows: list[dict[str, Any]] = []
    for roi in list(review_data.get("rois", []) or []):
        roi_id = str(roi.get("id"))
        roi_ann = ann["rois"].get(roi_id, {})
        score, reasons = roi_priority_score(roi, roi_ann)
        rows.append(
            {
                "subject_type": "roi",
                "subject_id": roi_id,
                "label_state": _state(roi_ann, "cell_state", "state") or "unlabeled",
                "priority_score": round(score, 4),
                "event_count": _event_count(roi),
                "area": roi.get("area"),
                "trace_snr": roi.get("traceSnr"),
                "local_correlation": roi.get("localCorrelationMean"),
                "event_support": roi.get("eventSupport"),
                "artifact_score": roi.get("artifactScore"),
                "reason_codes": ",".join(_reason_codes(reasons)),
            }
        )
    for suggestion in list(review_data.get("discovery", {}).get("suggestions", []) or []):
        suggestion_id = str(suggestion.get("id"))
        item = ann["suggestions"].get(suggestion_id, {})
        score, reasons = suggestion_priority_score(suggestion, item)
        rows.append(
            {
                "subject_type": "suggestion",
                "subject_id": suggestion_id,
                "label_state": str(item.get("state") or "unlabeled"),
                "priority_score": round(score, 4),
                "event_count": "",
                "area": suggestion.get("area"),
                "trace_snr": "",
                "local_correlation": suggestion.get("localCorrelationMean"),
                "event_support": suggestion.get("eventSupport"),
                "artifact_score": suggestion.get("artifactScore"),
                "reason_codes": ",".join(_reason_codes(reasons)),
            }
        )
    return rows


def build_guided_review_queues(
    review_data: Mapping[str, Any],
    annotations: Mapping[str, Any] | None,
    *,
    limit_per_queue: int | None = 30,
) -> dict[str, Any]:
    """Build deterministic guided-review queues for dashboard/report surfaces."""
    ann = migrate_annotations_v3(annotations)
    rois = list(review_data.get("rois", []) or [])
    suggestions = list(review_data.get("discovery", {}).get("suggestions", []) or [])
    queue_items = {queue_id: [] for queue_id in GUIDED_REVIEW_QUEUE_IDS}

    for roi in rois:
        roi_id = str(roi.get("id"))
        roi_ann = ann["rois"].get(roi_id, {})
        state = _state(roi_ann, "cell_state", "state")
        score, reasons = roi_priority_score(roi, roi_ann)
        item = _queue_item(
            "roi",
            roi_id,
            score,
            reasons,
            area=roi.get("area"),
            trace_snr=roi.get("traceSnr"),
            artifact_score=roi.get("artifactScore"),
            state=state or "unlabeled",
            confidence=roi_ann.get("confidence", ""),
        )

        if not _is_reviewed(state):
            queue_items["unreviewed_high_priority"].append(item)
        if state == "unsure" or roi_ann.get("confidence") in {"low", "medium"}:
            queue_items["uncertain"].append(_with_reasons(item, ["uncertain ROI label"]))
        if _as_float(roi.get("artifactScore"), 0.0) >= 0.4 or roi_ann.get("artifact_class"):
            queue_items["likely_artifact"].append(_with_reasons(item, ["artifact-like ROI"]))
        if _needs_second_reviewer(roi_ann):
            queue_items["needs_second_reviewer"].append(_with_reasons(item, ["needs second reviewer"]))

        for event in roi.get("events", []) or []:
            frame = event.get("frame")
            event_id = _event_key(roi_id, frame)
            event_ann = ann["events"].get(event_id, {})
            event_state = _state(event_ann, "event_state", "state")
            event_score = score + _as_float(event.get("z"), _as_float(event.get("score_z"), 0.0)) * 0.4
            event_item = _queue_item(
                "event",
                event_id,
                event_score,
                ["event review target"],
                roi_id=roi_id,
                frame=frame,
                z=event.get("z", event.get("score_z")),
                state=event_state or "unlabeled",
                confidence=event_ann.get("confidence", ""),
            )
            if event_state == "unsure" or event_ann.get("confidence") in {"low", "medium"}:
                queue_items["uncertain"].append(_with_reasons(event_item, ["uncertain event label"]))
            if _needs_second_reviewer(event_ann):
                queue_items["needs_second_reviewer"].append(_with_reasons(event_item, ["needs second reviewer"]))

    for suggestion in suggestions:
        suggestion_id = str(suggestion.get("id"))
        suggestion_ann = ann["suggestions"].get(suggestion_id, {})
        state = "promoted" if suggestion_id in ann.get("promotedRois", {}) else str(suggestion_ann.get("state") or "").strip().lower()
        score, reasons = suggestion_priority_score(suggestion, suggestion_ann)
        item = _queue_item(
            "suggestion",
            suggestion_id,
            score,
            reasons,
            area=suggestion.get("area"),
            artifact_score=suggestion.get("artifactScore"),
            artifact_cue=suggestion.get("artifactCue"),
            state=state or "unlabeled",
            confidence=suggestion_ann.get("confidence", ""),
        )
        artifact_like = _as_float(suggestion.get("artifactScore"), 0.0) >= 0.4 or suggestion.get("artifactCue") not in {None, "", "none"}
        if state in {"", "missed", "promoted"} and not artifact_like:
            queue_items["possible_missed_neuron"].append(_with_reasons(item, ["possible missed neuron"]))
        if state == "artifact" or artifact_like:
            queue_items["likely_artifact"].append(_with_reasons(item, ["artifact-like suggestion"]))
        if state == "unsure" or suggestion_ann.get("confidence") in {"low", "medium"}:
            queue_items["uncertain"].append(_with_reasons(item, ["uncertain suggestion label"]))
        if _needs_second_reviewer(suggestion_ann):
            queue_items["needs_second_reviewer"].append(_with_reasons(item, ["needs second reviewer"]))

    queues: dict[str, Any] = {}
    for queue_id in GUIDED_REVIEW_QUEUE_IDS:
        items = _rank_queue_items(queue_items[queue_id])
        if limit_per_queue is not None:
            items = items[: int(limit_per_queue)]
        queues[queue_id] = {
            "queue_id": queue_id,
            "label": _QUEUE_LABELS[queue_id],
            "description": _QUEUE_DESCRIPTIONS[queue_id],
            "count": len(queue_items[queue_id]),
            "items": items,
        }
    return queues


def _rank_events(
    rois: Sequence[Mapping[str, Any]],
    annotations: Mapping[str, Any],
    selected_roi_ids: set[str],
    target_events: int,
) -> list[dict[str, Any]]:
    event_rows: list[dict[str, Any]] = []
    for roi in rois:
        roi_id = str(roi.get("id"))
        roi_ann = annotations["rois"].get(roi_id, {})
        roi_score, _ = roi_priority_score(roi, roi_ann)
        for event in roi.get("events", []) or []:
            frame = event.get("frame")
            event_ann = annotations["events"].get(_event_key(roi_id, frame), {})
            if _is_reviewed(_state(event_ann, "event_state", "state")):
                continue
            event_score = roi_score + _as_float(event.get("z"), _as_float(event.get("score_z"), 0.0)) * 0.4
            if roi_id in selected_roi_ids:
                event_score += 1.0
            reasons = ["unlabeled event"]
            if roi_id in selected_roi_ids:
                reasons.append("selected ROI")
            if event.get("z") is not None or event.get("score_z") is not None:
                reasons.append("high event score")
            event_rows.append(
                {
                    "roi_id": roi_id,
                    "frame": frame,
                    "score": round(event_score, 4),
                    "z": event.get("z", event.get("score_z")),
                    "amplitude": event.get("amplitude"),
                    "reasons": reasons,
                }
            )
    event_rows.sort(key=lambda row: (-_as_float(row["score"]), row["roi_id"], _as_float(row["frame"])))
    return event_rows[:target_events]


_QUEUE_LABELS = {
    "unreviewed_high_priority": "Unreviewed high priority",
    "uncertain": "Uncertain labels",
    "likely_artifact": "Likely artifacts",
    "possible_missed_neuron": "Possible missed neurons",
    "needs_second_reviewer": "Needs second reviewer",
}

_QUEUE_DESCRIPTIONS = {
    "unreviewed_high_priority": "Unlabeled ROI candidates ranked by transparent priority features.",
    "uncertain": "ROIs, events, and suggestions with unsure labels or low/medium confidence.",
    "likely_artifact": "Candidates with artifact scores, artifact cues, or artifact labels.",
    "possible_missed_neuron": "Discovery suggestions that may represent neurons not covered by current ROIs.",
    "needs_second_reviewer": "Items explicitly tagged for another reviewer or low-confidence decisions.",
}


def _queue_item(subject_type: str, subject_id: str, score: float, reasons: Sequence[Any], **fields: Any) -> dict[str, Any]:
    item = {
        "subject_type": subject_type,
        "subject_id": str(subject_id),
        "priority_score": round(float(score), 4),
        "reason_codes": _reason_codes(reasons),
        "reasons": list(reasons),
    }
    item.update({key: value for key, value in fields.items() if value is not None})
    return item


def _with_reasons(item: Mapping[str, Any], extra_reasons: Sequence[Any]) -> dict[str, Any]:
    out = dict(item)
    reasons = list(out.get("reasons", []))
    for reason in extra_reasons:
        if reason not in reasons:
            reasons.append(reason)
    out["reasons"] = reasons
    out["reason_codes"] = _reason_codes(reasons)
    return out


def _rank_queue_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        key = (str(item.get("subject_type")), str(item.get("subject_id")))
        current = unique.get(key)
        if current is None or _as_float(item.get("priority_score")) > _as_float(current.get("priority_score")):
            unique[key] = dict(item)
    return sorted(
        unique.values(),
        key=lambda item: (-_as_float(item.get("priority_score")), str(item.get("subject_type")), str(item.get("subject_id"))),
    )


def _needs_second_reviewer(annotation: Mapping[str, Any]) -> bool:
    needs_action = str(annotation.get("needs_action") or "").strip().lower()
    reason_tags = {str(tag).strip().lower() for tag in annotation.get("reason_tags") or []}
    confidence = str(annotation.get("confidence") or "").strip().lower()
    return (
        "second" in needs_action
        or "second_review" in reason_tags
        or "needs_second_reviewer" in reason_tags
        or confidence == "low"
    )


def review_progress(
    review_data: Mapping[str, Any],
    annotations: Mapping[str, Any] | None,
    *,
    tuning_ready_rois: int = DEFAULT_TUNING_READY_ROIS,
    tuning_ready_events: int = DEFAULT_TUNING_READY_EVENTS,
) -> dict[str, Any]:
    """Summarize whether enough labels exist to begin parameter tuning."""
    ann = migrate_annotations_v3(annotations)
    rois = list(review_data.get("rois", []) or [])
    suggestions = list(review_data.get("discovery", {}).get("suggestions", []) or [])
    events = [(roi.get("id"), event.get("frame")) for roi in rois for event in (roi.get("events", []) or [])]

    reviewed_rois = sum(1 for roi in rois if _is_reviewed(_state(ann["rois"].get(str(roi.get("id")), {}), "cell_state", "state")))
    reviewed_events = sum(1 for roi_id, frame in events if _is_reviewed(_state(ann["events"].get(_event_key(roi_id, frame), {}), "event_state", "state")))
    reviewed_suggestions = sum(
        1
        for suggestion in suggestions
        if str(suggestion.get("id")) in ann.get("promotedRois", {})
        or bool(str(ann["suggestions"].get(str(suggestion.get("id")), {}).get("state") or "").strip())
    )
    accepted_rois = sum(1 for roi in rois if _state(ann["rois"].get(str(roi.get("id")), {}), "cell_state", "state") == "accepted")
    rejected_rois = sum(1 for roi in rois if _state(ann["rois"].get(str(roi.get("id")), {}), "cell_state", "state") == "rejected")
    accepted_events = sum(1 for roi_id, frame in events if _state(ann["events"].get(_event_key(roi_id, frame), {}), "event_state", "state") == "accepted")
    rejected_events = sum(1 for roi_id, frame in events if _state(ann["events"].get(_event_key(roi_id, frame), {}), "event_state", "state") == "rejected")

    return {
        "reviewed_rois": reviewed_rois,
        "reviewed_events": reviewed_events,
        "reviewed_suggestions": reviewed_suggestions,
        "accepted_rois": accepted_rois,
        "rejected_rois": rejected_rois,
        "accepted_events": accepted_events,
        "rejected_events": rejected_events,
        "roi_review_fraction": reviewed_rois / max(1, len(rois)),
        "event_review_fraction": reviewed_events / max(1, len(events)),
        "suggestion_review_fraction": reviewed_suggestions / max(1, len(suggestions)),
        "tuning_ready": reviewed_rois >= tuning_ready_rois and reviewed_events >= tuning_ready_events,
        "tuning_ready_targets": {
            "reviewed_rois": int(tuning_ready_rois),
            "reviewed_events": int(tuning_ready_events),
        },
    }
