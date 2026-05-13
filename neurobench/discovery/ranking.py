"""Candidate feature tables for discovery ranking and review triage."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any

from neurobench.metrics.detection import object_centroid, object_id, object_pixels


REQUIRED_FEATURE_COLUMNS = (
    "candidate_id",
    "centroid_x",
    "centroid_y",
    "area_px",
    "bbox_x",
    "bbox_y",
    "bbox_width_px",
    "bbox_height_px",
    "bbox_area_px",
    "fill_fraction",
    "aspect_ratio",
    "edge_distance_px",
    "event_count",
    "event_max_z",
    "event_mean_z",
    "event_max_amplitude",
    "peak_z",
    "trace_snr",
    "local_correlation",
    "event_support",
    "artifact_score",
    "raw_priority_score",
)


DEFAULT_RANKING_WEIGHTS = {
    "raw_priority_weight": 1.0,
    "peak_z_weight": 0.2,
    "event_count_weight": 0.45,
    "trace_snr_weight": 0.25,
    "local_correlation_weight": 0.2,
    "event_support_weight": 0.2,
    "artifact_weight": -0.15,
    "edge_penalty_weight": -0.05,
}


def build_candidate_feature_table(
    candidates: Sequence[Mapping[str, Any]],
    *,
    video_shape: Sequence[int] | Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return deterministic feature rows for candidate neurons.

    The input may be executor-style ``roi_candidates.json`` rows, workbench
    ``rois`` entries, or object-metric style candidates with pixels/masks.
    """
    dimensions = _video_dimensions(video_shape)
    rows = [_candidate_feature_row(candidate, index, dimensions) for index, candidate in enumerate(candidates)]
    rows.sort(key=lambda row: (_natural_id_key(row["candidate_id"]), row["centroid_y"], row["centroid_x"]))
    validate_candidate_feature_table(rows)
    return rows


def rank_candidate_features(
    feature_rows: Sequence[Mapping[str, Any]],
    *,
    weights: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Rank feature rows with transparent weighted contributions."""
    validate_candidate_feature_table(feature_rows)
    resolved_weights = _ranking_weights(weights)
    ranked = [_ranked_candidate_row(row, resolved_weights) for row in feature_rows]
    ranked.sort(key=lambda row: (-float(row["priority_score"]), str(row["candidate_id"])))
    for rank, row in enumerate(ranked, start=1):
        row["rank"] = rank
    return ranked


def rank_candidates(
    candidates: Sequence[Mapping[str, Any]],
    *,
    video_shape: Sequence[int] | Mapping[str, Any] | None = None,
    weights: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build feature rows and ranked candidates in one deterministic payload."""
    features = build_candidate_feature_table(candidates, video_shape=video_shape)
    ranked = rank_candidate_features(features, weights=weights)
    return {
        "schema_version": 1,
        "candidate_count": len(ranked),
        "weights": _ranking_weights(weights),
        "features": features,
        "ranked_candidates": ranked,
    }


def validate_candidate_feature_table(rows: Sequence[Mapping[str, Any]]) -> None:
    """Validate the public candidate feature row contract."""
    seen: set[str] = set()
    for index, row in enumerate(rows):
        missing = [column for column in REQUIRED_FEATURE_COLUMNS if column not in row]
        if missing:
            raise ValueError(f"Candidate feature row {index} is missing required columns: {', '.join(missing)}")
        candidate_id = str(row["candidate_id"])
        if not candidate_id:
            raise ValueError(f"Candidate feature row {index} has an empty candidate_id.")
        if candidate_id in seen:
            raise ValueError(f"Duplicate candidate_id in feature table: {candidate_id}")
        seen.add(candidate_id)
        for column in REQUIRED_FEATURE_COLUMNS:
            if column == "candidate_id":
                continue
            value = row[column]
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
                raise ValueError(f"Candidate feature row {candidate_id} column {column} must be a finite number.")


def _ranked_candidate_row(row: Mapping[str, Any], weights: Mapping[str, float]) -> dict[str, Any]:
    feature_values = {
        "raw_priority": float(row["raw_priority_score"]),
        "peak_z": min(max(float(row["peak_z"]), 0.0), 12.0),
        "event_count": min(float(row["event_count"]), 8.0),
        "trace_snr": min(max(float(row["trace_snr"]), 0.0), 6.0),
        "local_correlation": min(max(float(row["local_correlation"]), 0.0), 1.0),
        "event_support": min(max(float(row["event_support"]), 0.0), 1.0),
        "artifact": min(max(float(row["artifact_score"]), 0.0), 1.0),
        "edge_penalty": 1.0 if float(row["edge_distance_px"]) <= 2.0 else 0.0,
    }
    contribution_specs = (
        ("raw_priority", "raw_priority_weight", "existing proposal priority"),
        ("peak_z", "peak_z_weight", "peak evidence score"),
        ("event_count", "event_count_weight", "candidate event support"),
        ("trace_snr", "trace_snr_weight", "trace signal-to-noise"),
        ("local_correlation", "local_correlation_weight", "local temporal coherence"),
        ("event_support", "event_support_weight", "event-triggered footprint support"),
        ("artifact", "artifact_weight", "artifact-risk penalty"),
        ("edge_penalty", "edge_penalty_weight", "near-edge penalty"),
    )
    contributions: list[dict[str, Any]] = []
    score = 0.0
    for feature, weight_name, label in contribution_specs:
        weight = float(weights[weight_name])
        value = feature_values[feature]
        contribution = value * weight
        score += contribution
        if value != 0.0 or contribution != 0.0:
            contributions.append(
                {
                    "feature": feature,
                    "label": label,
                    "value": round(value, 6),
                    "weight": round(weight, 6),
                    "contribution": round(contribution, 6),
                }
            )
    contributions.sort(key=lambda item: (-abs(float(item["contribution"])), str(item["feature"])))
    reasons = _ranking_reasons(row, contributions)
    return {
        "candidate_id": str(row["candidate_id"]),
        "priority_score": round(score, 6),
        "rank": 0,
        "reasons": reasons,
        "reason_codes": _reason_codes(reasons),
        "explanation": {
            "summary": "; ".join(reasons[:3]) if reasons else "baseline candidate",
            "contributions": contributions,
        },
        "features": dict(row),
    }


def _ranking_reasons(row: Mapping[str, Any], contributions: Sequence[Mapping[str, Any]]) -> list[str]:
    reasons: list[str] = []
    if float(row["event_count"]) > 0:
        reasons.append(f"{int(row['event_count'])} candidate events")
    if float(row["trace_snr"]) >= 1.5:
        reasons.append("usable trace SNR")
    elif float(row["trace_snr"]) > 0:
        reasons.append("weak trace SNR")
    if float(row["local_correlation"]) >= 0.4:
        reasons.append("locally coherent")
    elif float(row["local_correlation"]) > 0:
        reasons.append("low local coherence")
    if float(row["event_support"]) >= 0.35:
        reasons.append("event-supported footprint")
    if float(row["artifact_score"]) >= 0.4:
        reasons.append("artifact risk")
    if float(row["edge_distance_px"]) <= 2.0:
        reasons.append("near video edge")
    if not reasons and contributions:
        top = contributions[0]
        reasons.append(str(top["label"]))
    return reasons or ["baseline candidate"]


def _reason_codes(reasons: Sequence[str]) -> list[str]:
    codes: list[str] = []
    for reason in reasons:
        text = reason.lower()
        if "event" in text:
            codes.append("event_support")
        if "snr" in text:
            codes.append("trace_snr")
        if "coherent" in text or "coherence" in text:
            codes.append("local_coherence")
        if "artifact" in text:
            codes.append("artifact_risk")
        if "edge" in text:
            codes.append("edge_risk")
    return sorted(set(codes))


def _ranking_weights(weights: Mapping[str, Any] | None) -> dict[str, float]:
    resolved = {key: float(value) for key, value in DEFAULT_RANKING_WEIGHTS.items()}
    for key, value in dict(weights or {}).items():
        if key in resolved:
            resolved[key] = _as_float(value, resolved[key])
        elif key in {"local_correlation_weight", "event_support_weight", "artifact_weight"}:
            resolved[key] = _as_float(value, resolved[key])
    return resolved


def _candidate_feature_row(
    candidate: Mapping[str, Any],
    index: int,
    dimensions: tuple[int | None, int | None],
) -> dict[str, Any]:
    candidate_id = object_id(candidate, index)
    centroid_x, centroid_y = object_centroid(candidate)
    bbox = _bbox_features(candidate, centroid_x, centroid_y)
    events = list(candidate.get("events", []) or [])
    event_z_values = [_as_float(event.get("z", event.get("event_z"))) for event in events if isinstance(event, Mapping)]
    event_amplitudes = [
        _as_float(event.get("amplitude", event.get("event_amplitude"))) for event in events if isinstance(event, Mapping)
    ]
    area_px = _candidate_area(candidate, bbox)
    bbox_area = bbox["bbox_width_px"] * bbox["bbox_height_px"]
    row = {
        "candidate_id": candidate_id,
        "centroid_x": round(float(centroid_x), 6),
        "centroid_y": round(float(centroid_y), 6),
        "area_px": round(float(area_px), 6),
        "bbox_x": round(float(bbox["bbox_x"]), 6),
        "bbox_y": round(float(bbox["bbox_y"]), 6),
        "bbox_width_px": round(float(bbox["bbox_width_px"]), 6),
        "bbox_height_px": round(float(bbox["bbox_height_px"]), 6),
        "bbox_area_px": round(float(bbox_area), 6),
        "fill_fraction": round(_safe_ratio(area_px, bbox_area), 6),
        "aspect_ratio": round(_safe_ratio(bbox["bbox_width_px"], bbox["bbox_height_px"], default=1.0), 6),
        "edge_distance_px": round(_edge_distance(centroid_x, centroid_y, dimensions), 6),
        "event_count": int(len(events)),
        "event_max_z": round(max(event_z_values) if event_z_values else 0.0, 6),
        "event_mean_z": round(sum(event_z_values) / len(event_z_values) if event_z_values else 0.0, 6),
        "event_max_amplitude": round(max(event_amplitudes) if event_amplitudes else 0.0, 6),
        "peak_z": round(_first_number(candidate, ("peak_z", "peakZ", "max_z", "z")), 6),
        "trace_snr": round(_first_number(candidate, ("trace_snr", "traceSnr", "snr")), 6),
        "local_correlation": round(
            _first_number(candidate, ("local_correlation", "localCorrelationMean", "local_corr")),
            6,
        ),
        "event_support": round(_first_number(candidate, ("event_support", "eventSupport")), 6),
        "artifact_score": round(_first_number(candidate, ("artifact_score", "artifactScore")), 6),
        "raw_priority_score": round(_first_number(candidate, ("priority_score", "priorityScore")), 6),
    }
    return row


def _candidate_area(candidate: Mapping[str, Any], bbox: Mapping[str, float]) -> float:
    for key in ("area_px", "area", "pixel_count", "size_px"):
        if key in candidate:
            return max(0.0, _as_float(candidate.get(key)))
    pixels = _explicit_pixels(candidate)
    if pixels:
        return float(len(pixels))
    return float(bbox["bbox_width_px"] * bbox["bbox_height_px"])


def _bbox_features(candidate: Mapping[str, Any], centroid_x: float, centroid_y: float) -> dict[str, float]:
    pixels = _explicit_pixels(candidate)
    if pixels:
        xs = [point[0] for point in pixels]
        ys = [point[1] for point in pixels]
        x0 = min(xs)
        y0 = min(ys)
        return {
            "bbox_x": float(x0),
            "bbox_y": float(y0),
            "bbox_width_px": float(max(xs) - x0 + 1),
            "bbox_height_px": float(max(ys) - y0 + 1),
        }
    bbox = candidate.get("bbox")
    if isinstance(bbox, Mapping):
        x = _as_float(bbox.get("x", bbox.get("xmin", bbox.get("x_min"))), centroid_x)
        y = _as_float(bbox.get("y", bbox.get("ymin", bbox.get("y_min"))), centroid_y)
        width = _as_float(bbox.get("width", bbox.get("w")), 1.0)
        height = _as_float(bbox.get("height", bbox.get("h")), 1.0)
        return _normalized_bbox(x, y, width, height, centroid_x, centroid_y)
    if isinstance(bbox, Sequence) and not isinstance(bbox, (str, bytes, bytearray)) and len(bbox) >= 4:
        x0 = _as_float(bbox[0], centroid_x)
        y0 = _as_float(bbox[1], centroid_y)
        third = _as_float(bbox[2], 1.0)
        fourth = _as_float(bbox[3], 1.0)
        if third >= centroid_x and fourth >= centroid_y:
            return _normalized_bbox(x0, y0, third - x0 + 1.0, fourth - y0 + 1.0, centroid_x, centroid_y)
        return _normalized_bbox(x0, y0, third, fourth, centroid_x, centroid_y)
    radius = max(1.0, math.sqrt(max(1.0, _as_float(candidate.get("area_px", candidate.get("area")), 1.0)) / math.pi))
    return _normalized_bbox(centroid_x - radius, centroid_y - radius, radius * 2.0, radius * 2.0, centroid_x, centroid_y)


def _normalized_bbox(x: float, y: float, width: float, height: float, centroid_x: float, centroid_y: float) -> dict[str, float]:
    width = max(1.0, float(width))
    height = max(1.0, float(height))
    return {
        "bbox_x": float(x),
        "bbox_y": float(y),
        "bbox_width_px": width,
        "bbox_height_px": height,
    }


def _video_dimensions(video_shape: Sequence[int] | Mapping[str, Any] | None) -> tuple[int | None, int | None]:
    if video_shape is None:
        return None, None
    if isinstance(video_shape, Mapping):
        width = video_shape.get("width")
        height = video_shape.get("height")
        return _optional_int(width), _optional_int(height)
    values = list(video_shape)
    if len(values) >= 3:
        return _optional_int(values[2]), _optional_int(values[1])
    if len(values) == 2:
        return _optional_int(values[1]), _optional_int(values[0])
    return None, None


def _edge_distance(centroid_x: float, centroid_y: float, dimensions: tuple[int | None, int | None]) -> float:
    width, height = dimensions
    if width is None or height is None:
        return 0.0
    return max(0.0, min(float(centroid_x), float(centroid_y), width - 1.0 - float(centroid_x), height - 1.0 - float(centroid_y)))


def _first_number(candidate: Mapping[str, Any], keys: Sequence[str], default: float = 0.0) -> float:
    for key in keys:
        if key in candidate:
            return _as_float(candidate.get(key), default)
    return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return float(default)
    return result if math.isfinite(result) else float(default)


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_ratio(numerator: float, denominator: float, *, default: float = 0.0) -> float:
    return float(numerator) / float(denominator) if denominator else default


def _natural_id_key(value: Any) -> tuple[str, int]:
    text = str(value)
    digits = "".join(ch for ch in text if ch.isdigit())
    return text.rstrip(digits), int(digits or 0)


def _explicit_pixels(candidate: Mapping[str, Any]) -> set[tuple[int, int]]:
    if "pixels" not in candidate and "mask" not in candidate:
        return set()
    return object_pixels(candidate)
