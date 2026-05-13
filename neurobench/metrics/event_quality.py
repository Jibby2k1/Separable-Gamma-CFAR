"""Event-level timing and quality metrics."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def match_events(
    ground_truth: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    *,
    onset_tolerance_frames: int = 2,
    require_same_object: bool = True,
) -> dict[str, Any]:
    """Greedily match candidate events to ground truth events.

    Event records may use ``frame`` only, or richer fields such as
    ``start_frame``, ``peak_frame``, and ``end_frame``. When
    ``require_same_object`` is true, records with comparable ROI/object IDs are
    only matched within the same object.
    """

    gt = [dict(item) for item in ground_truth]
    pred = [dict(item) for item in candidates]
    eligible: list[dict[str, Any]] = []
    for gt_idx, gt_event in enumerate(gt):
        for candidate_idx, candidate in enumerate(pred):
            if require_same_object and not _same_object(gt_event, candidate):
                continue
            onset_error = event_onset_frame(candidate) - event_onset_frame(gt_event)
            if abs(onset_error) > onset_tolerance_frames:
                continue
            peak_error = event_peak_frame(candidate) - event_peak_frame(gt_event)
            duration_error = event_duration_frames(candidate) - event_duration_frames(gt_event)
            eligible.append(
                {
                    "gt_index": gt_idx,
                    "candidate_index": candidate_idx,
                    "gt_event_id": event_id(gt_event, gt_idx),
                    "candidate_event_id": event_id(candidate, candidate_idx),
                    "gt_object_id": event_object_id(gt_event),
                    "candidate_object_id": event_object_id(candidate),
                    "onset_timing_error_frames": onset_error,
                    "peak_timing_error_frames": peak_error,
                    "duration_error_frames": duration_error,
                    "absolute_onset_error_frames": abs(onset_error),
                    "absolute_peak_error_frames": abs(peak_error),
                }
            )

    eligible.sort(
        key=lambda item: (
            int(item["absolute_onset_error_frames"]),
            int(item["absolute_peak_error_frames"]),
            int(item["gt_index"]),
            int(item["candidate_index"]),
        )
    )
    matched_gt: set[int] = set()
    matched_candidates: set[int] = set()
    matches: list[dict[str, Any]] = []
    for pair in eligible:
        gt_idx = int(pair["gt_index"])
        candidate_idx = int(pair["candidate_index"])
        if gt_idx in matched_gt or candidate_idx in matched_candidates:
            continue
        matched_gt.add(gt_idx)
        matched_candidates.add(candidate_idx)
        matches.append(pair)

    return {
        "matches": matches,
        "false_positives": [
            {"candidate_index": idx, "candidate_event_id": event_id(item, idx)}
            for idx, item in enumerate(pred)
            if idx not in matched_candidates
        ],
        "false_negatives": [
            {"gt_index": idx, "gt_event_id": event_id(item, idx)}
            for idx, item in enumerate(gt)
            if idx not in matched_gt
        ],
        "eligible_pair_count": len(eligible),
    }


def event_timing_metrics(
    ground_truth: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    *,
    onset_tolerance_frames: int = 2,
    require_same_object: bool = True,
) -> dict[str, Any]:
    """Return event precision/recall and timing-quality summaries."""

    result = match_events(
        ground_truth,
        candidates,
        onset_tolerance_frames=onset_tolerance_frames,
        require_same_object=require_same_object,
    )
    tp = len(result["matches"])
    fp = len(result["false_positives"])
    fn = len(result["false_negatives"])
    candidate_count = len(candidates)
    gt_count = len(ground_truth)
    matched_candidates = [candidates[int(match["candidate_index"])] for match in result["matches"]]
    return {
        "event_count_gt": gt_count,
        "event_count_candidate": candidate_count,
        "TP": tp,
        "FP": fp,
        "FN": fn,
        "event_precision": tp / candidate_count if candidate_count else 0.0,
        "event_recall": tp / gt_count if gt_count else 0.0,
        "mean_onset_timing_error_frames": _mean(match["onset_timing_error_frames"] for match in result["matches"]),
        "mean_abs_onset_timing_error_frames": _mean(match["absolute_onset_error_frames"] for match in result["matches"]),
        "mean_peak_timing_error_frames": _mean(match["peak_timing_error_frames"] for match in result["matches"]),
        "mean_abs_peak_timing_error_frames": _mean(match["absolute_peak_error_frames"] for match in result["matches"]),
        "mean_duration_error_frames": _mean(match["duration_error_frames"] for match in result["matches"]),
        "amplitude_distribution": _distribution(event_amplitude(event) for event in matched_candidates),
        "event_snr": _distribution(event.get("snr", event.get("event_snr")) for event in matched_candidates),
        "event_isolation": _distribution(event.get("isolation", event.get("event_isolation")) for event in matched_candidates),
        "matches": result["matches"],
        "false_positives": result["false_positives"],
        "false_negatives": result["false_negatives"],
    }


def event_onset_frame(event: Mapping[str, Any]) -> int:
    for key in ("start_frame", "onset_frame", "frame"):
        if key in event and event[key] is not None:
            return int(event[key])
    raise ValueError(f"Event is missing onset/frame information: {event!r}")


def event_peak_frame(event: Mapping[str, Any]) -> int:
    for key in ("peak_frame", "frame", "start_frame", "onset_frame"):
        if key in event and event[key] is not None:
            return int(event[key])
    raise ValueError(f"Event is missing peak/frame information: {event!r}")


def event_end_frame(event: Mapping[str, Any]) -> int:
    if "end_frame" in event and event["end_frame"] is not None:
        return int(event["end_frame"])
    if "duration_frames" in event and event["duration_frames"] is not None:
        return event_onset_frame(event) + max(0, int(event["duration_frames"]) - 1)
    return event_peak_frame(event)


def event_duration_frames(event: Mapping[str, Any]) -> int:
    if "duration_frames" in event and event["duration_frames"] is not None:
        return int(event["duration_frames"])
    return max(1, event_end_frame(event) - event_onset_frame(event) + 1)


def event_amplitude(event: Mapping[str, Any]) -> float | None:
    for key in ("amplitude", "peak_amplitude", "dff", "z"):
        if key in event and event[key] is not None:
            return float(event[key])
    return None


def event_id(event: Mapping[str, Any], fallback_index: int) -> str:
    for key in ("event_id", "id"):
        if key in event:
            return str(event[key])
    object_id = event_object_id(event)
    try:
        return f"{object_id}:{event_onset_frame(event)}" if object_id else str(event_onset_frame(event))
    except ValueError:
        return str(fallback_index)


def event_object_id(event: Mapping[str, Any]) -> str:
    for key in ("roi_id", "object_id", "candidate_id", "gt_id", "neuron_id"):
        if key in event and event[key] is not None:
            return str(event[key])
    return ""


def _same_object(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    object_a = event_object_id(a)
    object_b = event_object_id(b)
    if not object_a or not object_b:
        return True
    return object_a == object_b


def _distribution(values: Any) -> dict[str, float | int]:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return {"count": 0, "mean": 0.0, "min": 0.0, "max": 0.0}
    return {
        "count": len(clean),
        "mean": sum(clean) / len(clean),
        "min": min(clean),
        "max": max(clean),
    }


def _mean(values: Any) -> float:
    items = [float(value) for value in values]
    return sum(items) / len(items) if items else 0.0
