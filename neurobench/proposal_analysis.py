"""Missed-neuron proposal and artifact-risk analysis for review data."""
from __future__ import annotations

from collections import Counter
from typing import Any, Mapping


def _num(item: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    try:
        value = item.get(key, default)
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _bbox_shape(item: Mapping[str, Any]) -> tuple[float, float, float]:
    bbox = item.get("bbox") or []
    if not isinstance(bbox, list | tuple) or len(bbox) != 4:
        return 1.0, 1.0, 1.0
    width = max(1.0, _num({"v": bbox[2]}, "v") - _num({"v": bbox[0]}, "v") + 1.0)
    height = max(1.0, _num({"v": bbox[3]}, "v") - _num({"v": bbox[1]}, "v") + 1.0)
    return width, height, max(width / height, height / width)


def _near_border(item: Mapping[str, Any], video: Mapping[str, Any] | None) -> bool:
    bbox = item.get("bbox") or []
    if not video or not isinstance(bbox, list | tuple) or len(bbox) != 4:
        return False
    width = _num(video, "width", 0)
    height = _num(video, "height", 0)
    if width <= 0 or height <= 0:
        return False
    return bbox[0] <= 1 or bbox[1] <= 1 or bbox[2] >= width - 2 or bbox[3] >= height - 2


def _annotation_for(annotations: Mapping[str, Any] | None, section: str, subject_id: Any) -> Mapping[str, Any]:
    if not annotations:
        return {}
    items = annotations.get(section) or {}
    ann = items.get(str(subject_id)) if isinstance(items, Mapping) else None
    return ann if isinstance(ann, Mapping) else {}


def artifact_reasons_for_item(
    item: Mapping[str, Any],
    *,
    video: Mapping[str, Any] | None = None,
    annotation: Mapping[str, Any] | None = None,
) -> list[str]:
    """Return human-readable artifact cues for an ROI or discovery suggestion."""
    reasons: list[str] = []
    area = _num(item, "area", 0)
    artifact_score = _num(item, "artifactScore", 0)
    background_corr = _num(item, "backgroundCorrelation", 0)
    local_corr = _num(item, "localCorrelationMean", 0)
    _, _, elongation = _bbox_shape(item)
    cue = str(item.get("artifactCue") or "none")
    ann = annotation or {}
    ann_artifact = str(ann.get("artifact_class") or ann.get("artifactClass") or "")

    if artifact_score >= 0.4:
        reasons.append("artifact score")
    if background_corr >= 0.55:
        reasons.append("background correlated")
    if 0 < local_corr < 0.35:
        reasons.append("low local coherence")
    if area and area < 8:
        reasons.append("too small")
    if area >= 180:
        reasons.append("large or merged")
    if elongation >= 5:
        reasons.append("elongated")
    if _near_border(item, video):
        reasons.append("near border")
    if cue and cue != "none":
        reasons.append(cue.replace("_", " "))
    if ann_artifact and ann_artifact != "none":
        reasons.append(ann_artifact.replace("_", " "))
    return list(dict.fromkeys(reasons))


def artifact_score_for_roi(
    roi: Mapping[str, Any],
    *,
    video: Mapping[str, Any] | None = None,
    annotation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Score likely artifact ROIs using explicit interpretable cues."""
    area = _num(roi, "area", 0)
    artifact_score = _num(roi, "artifactScore", 0)
    background_corr = _num(roi, "backgroundCorrelation", 0)
    local_corr = _num(roi, "localCorrelationMean", 0)
    trace_snr = _num(roi, "traceSnr", 0)
    _, _, elongation = _bbox_shape(roi)
    reasons = artifact_reasons_for_item(roi, video=video, annotation=annotation)
    score = 0.0
    score += 0.45 * _clamp(artifact_score)
    score += 0.20 * _clamp((background_corr - 0.35) / 0.45)
    score += 0.15 * _clamp((0.40 - local_corr) / 0.40) if local_corr > 0 else 0.0
    score += 0.10 * _clamp((area - 140) / 160)
    score += 0.08 * _clamp((8 - area) / 8) if area else 0.0
    score += 0.10 * _clamp((elongation - 3) / 4)
    score += 0.08 if _near_border(roi, video) else 0.0
    score += 0.08 * _clamp((1.5 - trace_snr) / 1.5) if trace_snr > 0 else 0.0
    score += 0.15 if annotation and (annotation.get("artifact_class") or annotation.get("artifactClass")) not in {None, "", "none"} else 0.0
    return {
        "roi_id": str(roi.get("id")),
        "artifact_risk": round(_clamp(score), 3),
        "artifact_score": round(artifact_score, 3),
        "background_correlation": round(background_corr, 3),
        "local_correlation_mean": round(local_corr, 3),
        "trace_snr": round(trace_snr, 3),
        "area": int(area) if area.is_integer() else round(area, 2),
        "elongation": round(elongation, 2),
        "reasons": reasons,
        "annotation_state": annotation.get("cell_state") or annotation.get("state") if annotation else "",
    }


def _suggestion_annotation_state(annotation: Mapping[str, Any]) -> str:
    return str(annotation.get("state") or annotation.get("suggestion_state") or "")


def score_missed_neuron_suggestion(
    suggestion: Mapping[str, Any],
    *,
    video: Mapping[str, Any] | None = None,
    annotation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Score a discovery suggestion as a candidate missed neuron."""
    priority = _num(suggestion, "priorityScore", _num(suggestion, "discoveryScore", 0))
    discovery = _num(suggestion, "discoveryScore", priority)
    event_support = _num(suggestion, "eventSupport", 0)
    local_corr = _num(suggestion, "localCorrelationMean", 0)
    compactness = _num(suggestion, "compactness", 0)
    max_z = _num(suggestion, "maxZ", 0)
    active_frames = _num(suggestion, "activeFrames", 0)
    artifact_score = _num(suggestion, "artifactScore", 0)
    area = _num(suggestion, "area", 0)
    _, _, elongation = _bbox_shape(suggestion)
    ann_state = _suggestion_annotation_state(annotation or {})
    artifact_reasons = artifact_reasons_for_item(suggestion, video=video, annotation=annotation)
    reasons = ["uncovered discovery suggestion"]
    if event_support >= 0.35:
        reasons.append("event-supported")
    if local_corr >= 0.45:
        reasons.append("locally coherent")
    if compactness >= 0.45:
        reasons.append("compact footprint")
    if max_z >= 3:
        reasons.append("strong positive evidence")
    if active_frames >= 4:
        reasons.append("repeated activity")
    if artifact_reasons:
        reasons.append("artifact cue: " + ", ".join(artifact_reasons[:3]))
    if ann_state:
        reasons.append(f"annotation: {ann_state}")

    score = 0.35 * _clamp(priority)
    score += 0.20 * _clamp(discovery)
    score += 0.18 * _clamp(event_support)
    score += 0.14 * _clamp(local_corr)
    score += 0.08 * _clamp(compactness)
    score += 0.06 * _clamp(max_z / 6)
    score += 0.04 * _clamp(active_frames / 20)
    score -= 0.22 * _clamp(artifact_score)
    score -= 0.08 * _clamp((area - 180) / 180)
    score -= 0.08 * _clamp((elongation - 3) / 4)
    score -= 0.05 if _near_border(suggestion, video) else 0.0
    if ann_state in {"reject", "rejected", "artifact"}:
        score -= 0.35
    elif ann_state in {"accept", "accepted"}:
        score += 0.10

    return {
        "suggestion_id": str(suggestion.get("id")),
        "proposal_score": round(_clamp(score), 3),
        "priority_score": round(priority, 3),
        "discovery_score": round(discovery, 3),
        "event_support": round(event_support, 3),
        "local_correlation_mean": round(local_corr, 3),
        "compactness": round(compactness, 3),
        "max_z": round(max_z, 3),
        "active_frames": int(active_frames) if active_frames.is_integer() else round(active_frames, 2),
        "artifact_score": round(artifact_score, 3),
        "artifact_cue": suggestion.get("artifactCue") or "none",
        "area": int(area) if area.is_integer() else round(area, 2),
        "centroid_x": round(_num(suggestion, "centroidX", 0), 2),
        "centroid_y": round(_num(suggestion, "centroidY", 0), 2),
        "annotation_state": ann_state,
        "reasons": reasons,
    }


def build_proposal_analysis(
    review_data: Mapping[str, Any],
    annotations: Mapping[str, Any] | None = None,
    *,
    limit: int = 50,
) -> dict[str, Any]:
    """Build browser-readable proposal and artifact triage tables."""
    video = review_data.get("video") if isinstance(review_data.get("video"), Mapping) else {}
    artifact_rows = [
        artifact_score_for_roi(roi, video=video, annotation=_annotation_for(annotations, "rois", roi.get("id")))
        for roi in review_data.get("rois", [])
        if isinstance(roi, Mapping)
    ]
    artifact_rows.sort(key=lambda row: (row["artifact_risk"], row["artifact_score"]), reverse=True)
    proposal_rows = [
        score_missed_neuron_suggestion(
            suggestion,
            video=video,
            annotation=_annotation_for(annotations, "suggestions", suggestion.get("id")),
        )
        for suggestion in (review_data.get("discovery", {}) or {}).get("suggestions", [])
        if isinstance(suggestion, Mapping)
    ]
    proposal_rows.sort(key=lambda row: row["proposal_score"], reverse=True)
    reason_counts = Counter(reason for row in artifact_rows for reason in row["reasons"])
    high_risk = [row for row in artifact_rows if row["artifact_risk"] >= 0.4]
    return {
        "schema_version": 1,
        "dataset_id": (review_data.get("dataset") or {}).get("dataset_id") or review_data.get("dataset_id") or "",
        "video": {
            "name": video.get("name"),
            "width": video.get("width"),
            "height": video.get("height"),
            "frames": video.get("frames"),
        },
        "artifact_classifier": {
            "rows": artifact_rows[:limit],
            "reason_counts": dict(sorted(reason_counts.items())),
            "high_risk_count": len(high_risk),
            "roi_count": len(artifact_rows),
        },
        "missed_neuron_proposals": {
            "rows": proposal_rows[:limit],
            "summary": {
                "proposal_count": len(proposal_rows),
                "shown_count": min(limit, len(proposal_rows)),
                "high_confidence_count": sum(1 for row in proposal_rows if row["proposal_score"] >= 0.65),
                "artifact_cued_count": sum(1 for row in proposal_rows if row["artifact_cue"] not in {"", "none", None}),
            },
        },
    }
