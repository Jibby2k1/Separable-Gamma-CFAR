"""Trace materialization helpers for annotation-layer ROI footprints."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence

from neurobench.data.video import open_video


def materialize_virtual_roi_traces(
    *,
    review_data: Mapping[str, Any],
    annotations: Mapping[str, Any],
    raw_video_path: str | Path,
    run_id: str | None = None,
    roi_ids: Sequence[str] | None = None,
    outer_radius_px: int = 15,
    neuropil_weight: float = 0.7,
    event_threshold_z: float = 2.4,
    kalman_gain: float = 0.06,
    spike_gain: float = 0.008,
    negative_gain: float = 0.11,
) -> dict[str, Any]:
    """Return annotations with fluorescence traces attached to virtual ROIs.

    The source ``review_data.json`` is not modified. Materialized traces are
    stored on the corresponding ``virtualRois`` entries inside the active run
    annotation bucket and mirrored to the top-level active working copy.
    """

    np = _load_numpy()
    video = open_video(raw_video_path, mmap=True)
    frames = np.asarray(video.as_array(), dtype=np.float32)
    if frames.ndim < 3:
        raise ValueError(f"Expected frame-first video, got shape {frames.shape}.")
    frames = frames.reshape((frames.shape[0], frames.shape[-2], frames.shape[-1]))
    frame_count, height, width = (int(frames.shape[0]), int(frames.shape[1]), int(frames.shape[2]))
    expected = review_data.get("video") or {}
    if expected.get("frames") and int(expected["frames"]) != frame_count:
        raise ValueError(f"Raw video has {frame_count} frames, review data expects {expected['frames']}.")
    if expected.get("width") and int(expected["width"]) != width:
        raise ValueError(f"Raw video width {width} does not match review data width {expected['width']}.")
    if expected.get("height") and int(expected["height"]) != height:
        raise ValueError(f"Raw video height {height} does not match review data height {expected['height']}.")

    out = deepcopy(dict(annotations))
    settings = dict(out.get("settings") or {})
    active_run_id = str(run_id or settings.get("activeRunId") or "")
    bucket = _active_bucket(out, active_run_id)
    virtual_rois = bucket.setdefault("virtualRois", {})
    selected_ids = {str(item) for item in roi_ids or []}
    any_roi = _any_roi_mask(review_data=review_data, virtual_rois=virtual_rois, width=width, height=height, np=np)
    frame_mean = frames.reshape(frame_count, -1).mean(axis=1)
    materialized: list[str] = []

    for roi_id, roi in list(virtual_rois.items()):
        if selected_ids and str(roi_id) not in selected_ids:
            continue
        points = roi.get("points") or []
        if not points:
            continue
        roi_mask = _points_mask(points, width=width, height=height, np=np)
        if not bool(roi_mask.any()):
            continue
        bg_mask = _ring_mask(
            roi_mask=roi_mask,
            any_roi=any_roi,
            outer_radius_px=max(1, int(outer_radius_px)),
            np=np,
        )
        raw_trace = _mean_trace(frames, roi_mask, np=np)
        bg_trace = _mean_trace(frames, bg_mask, np=np) if bool(bg_mask.any()) else frame_mean.astype(float)
        model = _trace_model(
            raw_trace,
            bg_trace,
            neuropil_weight=float(neuropil_weight),
            gain=float(kalman_gain),
            spike_gain=float(spike_gain),
            negative_gain=float(negative_gain),
            event_threshold=float(event_threshold_z),
            np=np,
        )
        updated = dict(roi)
        updated.update(
            {
                "rawTrace": _rounded(raw_trace, 2),
                "backgroundTrace": _rounded(bg_trace, 2),
                "dffTrace": _rounded(model["dff"], 5),
                "baselineTrace": _rounded(model["baseline"], 5),
                "eventTrace": _rounded(model["eventTrace"], 5),
                "zTrace": _rounded(model["zTrace"], 3),
                "noiseSigma": round(float(model["noiseSigma"]), 5),
                "traceSnr": round(float(model["traceSnr"]), 3),
                "backgroundCorrelation": round(float(_correlation(raw_trace, bg_trace, np=np)), 3),
                "eventSupport": round(float(len(model["events"]) / max(1, frame_count)), 3),
                "events": [
                    {
                        "frame": int(event["frame"]),
                        "z": round(float(event["z"]), 2),
                        "amplitude": round(float(event["amplitude"]), 5),
                    }
                    for event in model["events"]
                ],
                "trace_materialized": True,
                "trace_materialized_at": _now_iso(),
                "trace_materialization": {
                    "raw_video": str(raw_video_path),
                    "outer_radius_px": int(outer_radius_px),
                    "neuropil_weight": float(neuropil_weight),
                    "event_threshold_z": float(event_threshold_z),
                },
            }
        )
        virtual_rois[str(roi_id)] = updated
        materialized.append(str(roi_id))

    if active_run_id:
        out.setdefault("runs", {})[active_run_id] = bucket
        _mirror_active_bucket(out, bucket)
    else:
        out["virtualRois"] = virtual_rois
    out["updatedAt"] = _now_iso()
    out.setdefault("_materialization", {})["last_virtual_roi_trace_ids"] = materialized
    return {"annotations": out, "materialized_ids": materialized}


def _active_bucket(annotations: dict[str, Any], run_id: str) -> dict[str, Any]:
    if run_id and isinstance(annotations.get("runs"), dict):
        runs = annotations.setdefault("runs", {})
        bucket = runs.setdefault(
            run_id,
            {
                "rois": {},
                "events": {},
                "suggestions": {},
                "promotedRois": {},
                "virtualRois": {},
                "splitMergeDecisions": {},
            },
        )
        return bucket
    return annotations


def _mirror_active_bucket(annotations: dict[str, Any], bucket: Mapping[str, Any]) -> None:
    for key in ("rois", "events", "suggestions", "promotedRois", "virtualRois", "splitMergeDecisions"):
        annotations[key] = deepcopy(dict(bucket.get(key) or {}))


def _any_roi_mask(*, review_data: Mapping[str, Any], virtual_rois: Mapping[str, Any], width: int, height: int, np: Any) -> Any:
    mask = np.zeros((height, width), dtype=bool)
    for roi in list(review_data.get("rois") or []) + list(virtual_rois.values()):
        points = roi.get("points") if isinstance(roi, Mapping) else None
        if points:
            mask |= _points_mask(points, width=width, height=height, np=np)
    return mask


def _points_mask(points: Sequence[Any], *, width: int, height: int, np: Any) -> Any:
    mask = np.zeros((height, width), dtype=bool)
    for point in points:
        if not isinstance(point, Sequence) or len(point) < 2:
            continue
        x = int(round(float(point[0])))
        y = int(round(float(point[1])))
        if 0 <= x < width and 0 <= y < height:
            mask[y, x] = True
    return mask


def _ring_mask(*, roi_mask: Any, any_roi: Any, outer_radius_px: int, np: Any) -> Any:
    ys, xs = np.where(roi_mask)
    if len(xs) == 0:
        return np.zeros_like(roi_mask, dtype=bool)
    height, width = roi_mask.shape
    y0 = max(0, int(ys.min()) - outer_radius_px)
    y1 = min(height - 1, int(ys.max()) + outer_radius_px)
    x0 = max(0, int(xs.min()) - outer_radius_px)
    x1 = min(width - 1, int(xs.max()) + outer_radius_px)
    yy, xx = np.ogrid[y0 : y1 + 1, x0 : x1 + 1]
    local_ring = np.zeros((y1 - y0 + 1, x1 - x0 + 1), dtype=bool)
    r2 = float(outer_radius_px * outer_radius_px)
    for x, y in zip(xs, ys):
        local_ring |= (xx - x) ** 2 + (yy - y) ** 2 <= r2
    ring = np.zeros_like(roi_mask, dtype=bool)
    ring[y0 : y1 + 1, x0 : x1 + 1] = local_ring
    ring &= ~roi_mask
    ring &= ~any_roi
    return ring


def _mean_trace(frames: Any, mask: Any, *, np: Any) -> Any:
    if not bool(mask.any()):
        return np.zeros(frames.shape[0], dtype=float)
    pixels = frames[:, mask]
    return pixels.mean(axis=1).astype(float)


def _trace_model(
    raw_trace: Any,
    bg_trace: Any,
    *,
    neuropil_weight: float,
    gain: float,
    spike_gain: float,
    negative_gain: float,
    event_threshold: float,
    np: Any,
) -> dict[str, Any]:
    corrected = raw_trace - neuropil_weight * bg_trace
    base0 = float(np.percentile(corrected, 20))
    scale_base = max(1.0, abs(base0))
    dff = (corrected - base0) / scale_base
    center = float(np.median(dff))
    sigma = _mad_sigma(dff, center, np=np)
    baseline = center
    baseline_trace = np.zeros_like(dff, dtype=float)
    event_trace = np.zeros_like(dff, dtype=float)
    z_trace = np.zeros_like(dff, dtype=float)
    for idx, value in enumerate(dff):
        residual = float(value - baseline)
        k = gain
        if residual > 2.5 * sigma:
            k = spike_gain
        if residual < -1.0 * sigma:
            k = negative_gain
        baseline += k * residual
        baseline_trace[idx] = baseline
        innovation = max(0.0, float(value - baseline))
        event_trace[idx] = innovation
        z_trace[idx] = innovation / max(1.0e-6, sigma)
    events: list[dict[str, float | int]] = []
    last_event = -99
    for idx in range(1, len(z_trace) - 1):
        if z_trace[idx] >= event_threshold and z_trace[idx] >= z_trace[idx - 1] and z_trace[idx] >= z_trace[idx + 1] and idx - last_event >= 2:
            events.append({"frame": idx + 1, "z": float(z_trace[idx]), "amplitude": float(event_trace[idx])})
            last_event = idx
    return {
        "dff": dff,
        "baseline": baseline_trace,
        "eventTrace": event_trace,
        "zTrace": z_trace,
        "noiseSigma": sigma,
        "traceSnr": float(event_trace.max() / max(1.0e-6, sigma)) if len(event_trace) else 0.0,
        "events": events,
    }


def _mad_sigma(values: Any, center: float, *, np: Any) -> float:
    mad = float(np.median(np.abs(values - center)))
    sigma = 1.4826 * mad
    return sigma if sigma > 1.0e-6 else 1.0e-6


def _correlation(a: Any, b: Any, *, np: Any) -> float:
    if len(a) < 2 or len(b) < 2:
        return 0.0
    av = a - float(np.mean(a))
    bv = b - float(np.mean(b))
    denom = float(np.sqrt(np.sum(av * av) * np.sum(bv * bv)))
    if denom <= 1.0e-12:
        return 0.0
    return float(np.sum(av * bv) / denom)


def _rounded(values: Any, places: int) -> list[float]:
    return [round(float(v), places) for v in values]


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_numpy() -> Any:
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        raise RuntimeError("Manual ROI trace materialization requires NumPy.") from exc
    return np
