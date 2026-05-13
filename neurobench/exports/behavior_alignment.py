"""Behavior/imaging alignment diagnostics for inverse-dynamics exports."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
import statistics
from typing import Any


SCHEMA_VERSION = 1
DEFAULT_GAP_FACTOR = 1.5


def alignment_report(dataset_context: Mapping[str, Any]) -> dict[str, Any]:
    """Return a schema-versioned behavior alignment diagnostics report."""
    behavior = dict(dataset_context.get("behavior") or {})
    behavior_paths = dict(dataset_context.get("behavior_paths") or {})
    raw_status = str(behavior.get("alignment_status") or behavior.get("status") or "").strip().lower()
    if raw_status in {"validated", "failed", "provided_unvalidated", "not_provided"}:
        status = raw_status
    elif behavior.get("validated") is True or behavior.get("sync_validated") is True:
        status = "validated"
    elif behavior.get("alignment_failed") is True:
        status = "failed"
    elif behavior or behavior_paths:
        status = "provided_unvalidated"
    else:
        status = "not_provided"

    frame_mapping = frame_time_mapping_diagnostics(dataset_context)
    sync_behavior = dict(behavior)
    if sync_behavior.get("frame_rate_hz") is None:
        sync_behavior["frame_rate_hz"] = dataset_context.get("frame_rate_hz")
    sync = sync_diagnostics(sync_behavior)
    resampling = resampling_diagnostics(dataset_context, behavior, frame_mapping)
    warnings = _combined_warnings(frame_mapping, sync, resampling)
    errors = _combined_errors(frame_mapping, sync, resampling)

    if sync.get("status") == "failed" or frame_mapping.get("status") == "failed":
        status = "failed"
    elif status == "validated" and warnings:
        status = "provided_unvalidated"

    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "has_behavior_metadata": bool(behavior),
        "has_behavior_paths": bool(behavior_paths),
        "behavior_paths": behavior_paths,
        "sync_offset_frames": behavior.get("sync_offset_frames"),
        "sync_offset_sec": behavior.get("sync_offset_sec"),
        "frame_rate_hz": _as_float(dataset_context.get("frame_rate_hz")),
        "timebase": behavior.get("timebase", "imaging_frames"),
        "frame_time_mapping": frame_mapping,
        "sync": sync,
        "resampling": resampling,
        "warnings": warnings,
        "errors": errors,
        "notes": _alignment_notes(status),
    }


def frame_time_sec(frame_index_zero_based: int, frame_rate_hz: float | int | None) -> float | None:
    """Map a zero-based imaging frame index to seconds."""
    rate = _as_float(frame_rate_hz)
    if rate is None or rate <= 0:
        return None
    return frame_index_zero_based / rate


def frame_time_mapping_diagnostics(dataset_context: Mapping[str, Any]) -> dict[str, Any]:
    """Check whether exported frame indices can be mapped to time consistently."""
    frame_rate_hz = _as_float(dataset_context.get("frame_rate_hz"))
    frame_count = _as_int(
        dataset_context.get("imaging_frame_count")
        or dataset_context.get("frame_count")
        or dataset_context.get("frames"),
        default=0,
    )
    timestamps = _timestamp_sequence(
        dataset_context,
        ("frame_timestamps_sec", "imaging_timestamps_sec", "timestamps_sec"),
    )
    timestamp_checks = timestamp_diagnostics(timestamps, label="imaging") if timestamps else _empty_timestamp_report("imaging")
    warnings = list(timestamp_checks.get("warnings") or [])
    errors: list[str] = []

    if frame_rate_hz is None or frame_rate_hz <= 0:
        errors.append("Frame/time mapping requires a positive frame_rate_hz.")
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "failed",
            "frame_rate_hz": frame_rate_hz,
            "frame_count": frame_count,
            "frame_index_base": 1,
            "time_formula": None,
            "timestamps": timestamp_checks,
            "warnings": warnings,
            "errors": errors,
        }

    frame_period_sec = 1.0 / frame_rate_hz
    if frame_count <= 0 and timestamps:
        frame_count = len(timestamps)
    computed = [index * frame_period_sec for index in range(frame_count)]
    max_abs_timestamp_error_sec = None
    finite_timestamps = _finite_values(timestamps)
    if finite_timestamps and computed:
        count = min(len(finite_timestamps), len(computed))
        max_abs_timestamp_error_sec = max(abs(finite_timestamps[index] - computed[index]) for index in range(count))
        tolerance = _as_float(dataset_context.get("frame_time_tolerance_sec")) or frame_period_sec * 0.5
        if max_abs_timestamp_error_sec > tolerance:
            warnings.append(
                f"Imaging timestamps differ from frame_rate_hz mapping by up to {max_abs_timestamp_error_sec:.6g} sec."
            )
        if len(finite_timestamps) != frame_count:
            warnings.append(f"Imaging timestamp count {len(finite_timestamps)} does not match frame count {frame_count}.")

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "warning" if warnings else "ok",
        "frame_rate_hz": frame_rate_hz,
        "frame_period_sec": frame_period_sec,
        "frame_count": frame_count,
        "frame_index_base": 1,
        "time_formula": "(frame - 1) / frame_rate_hz",
        "first_frame_time_sec": 0.0 if frame_count > 0 else None,
        "last_frame_time_sec": (frame_count - 1) * frame_period_sec if frame_count > 0 else None,
        "max_abs_timestamp_error_sec": max_abs_timestamp_error_sec,
        "timestamps": timestamp_checks,
        "warnings": warnings,
        "errors": errors,
    }


def sync_diagnostics(behavior: Mapping[str, Any]) -> dict[str, Any]:
    """Check explicit sync points or sync error arrays when provided."""
    sync_errors = _number_sequence(behavior, ("sync_errors_sec", "sync_error_sec"))
    sync_points = behavior.get("sync_points") or behavior.get("sync_events") or []
    offset_sec = _as_float(behavior.get("sync_offset_sec"))
    if offset_sec is None:
        offset_frames = _as_float(behavior.get("sync_offset_frames"))
        frame_rate_hz = _as_float(behavior.get("frame_rate_hz"))
        if offset_frames is not None and frame_rate_hz and frame_rate_hz > 0:
            offset_sec = offset_frames / frame_rate_hz
    if offset_sec is None:
        offset_sec = 0.0

    errors = list(sync_errors)
    if isinstance(sync_points, Sequence) and not isinstance(sync_points, (str, bytes)):
        for point in sync_points:
            if not isinstance(point, Mapping):
                continue
            direct_error = _as_float(point.get("error_sec"))
            if direct_error is not None:
                errors.append(direct_error)
                continue
            imaging_time = _first_float(point, ("imaging_time_sec", "frame_time_sec", "expected_time_sec"))
            behavior_time = _first_float(point, ("behavior_time_sec", "observed_time_sec", "tail_time_sec"))
            point_offset = _as_float(point.get("sync_offset_sec"))
            if imaging_time is not None and behavior_time is not None:
                errors.append(imaging_time - (behavior_time + (point_offset if point_offset is not None else offset_sec)))

    tolerance = _as_float(behavior.get("sync_tolerance_sec")) or 0.05
    warnings: list[str] = []
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "not_tested",
        "sync_point_count": len(sync_points) if isinstance(sync_points, Sequence) and not isinstance(sync_points, (str, bytes)) else 0,
        "sync_error_count": len(errors),
        "sync_offset_sec": offset_sec,
        "tolerance_sec": tolerance,
        "max_abs_error_sec": None,
        "mean_abs_error_sec": None,
        "warnings": warnings,
        "errors": [],
    }
    if not errors:
        return report

    abs_errors = [abs(value) for value in errors if math.isfinite(value)]
    if not abs_errors:
        report["status"] = "failed"
        report["errors"] = ["Sync diagnostics contain no finite error values."]
        return report

    max_abs = max(abs_errors)
    report["max_abs_error_sec"] = max_abs
    report["mean_abs_error_sec"] = sum(abs_errors) / len(abs_errors)
    if max_abs > tolerance:
        message = f"Sync error {max_abs:.6g} sec exceeds tolerance {tolerance:.6g} sec."
        report["status"] = "failed"
        report["warnings"] = [message]
        report["errors"] = [message]
    else:
        report["status"] = "ok"
    return report


def resampling_diagnostics(
    dataset_context: Mapping[str, Any],
    behavior: Mapping[str, Any],
    frame_mapping: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Check source behavior timestamps against the imaging target timebase."""
    source = _timestamp_sequence(
        behavior,
        (
            "behavior_timestamps_sec",
            "tail_timestamps_sec",
            "timestamps_sec",
            "time_sec",
            "sample_times_sec",
        ),
    )
    target = _timestamp_sequence(
        dataset_context,
        ("frame_timestamps_sec", "imaging_timestamps_sec", "timestamps_sec"),
    )
    if not target:
        frame_count = _as_int((frame_mapping or {}).get("frame_count"), default=0)
        frame_rate_hz = _as_float((frame_mapping or {}).get("frame_rate_hz") or dataset_context.get("frame_rate_hz"))
        if frame_count > 0 and frame_rate_hz and frame_rate_hz > 0:
            target = [index / frame_rate_hz for index in range(frame_count)]

    source_checks = timestamp_diagnostics(source, label="behavior") if source else _empty_timestamp_report("behavior")
    target_checks = timestamp_diagnostics(target, label="imaging") if target else _empty_timestamp_report("imaging")
    warnings = list(source_checks.get("warnings") or []) + list(target_checks.get("warnings") or [])
    errors = list(source_checks.get("errors") or []) + list(target_checks.get("errors") or [])

    source_dt = _median_positive_delta(source)
    target_dt = _median_positive_delta(target)
    finite_source = _finite_values(source)
    finite_target = _finite_values(target)
    if finite_source and finite_target:
        if finite_target[0] < finite_source[0] or finite_target[-1] > finite_source[-1]:
            warnings.append("Imaging target time range extends outside behavior timestamp range.")
    status = "not_tested"
    if finite_source and finite_target:
        status = "failed" if errors else "warning" if warnings else "ok"

    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "policy": str(behavior.get("resampling_policy") or behavior.get("resampling") or "not_specified"),
        "interpolation": str(behavior.get("interpolation_policy") or behavior.get("interpolation") or "not_specified"),
        "source_sample_count": len(source),
        "target_sample_count": len(target),
        "source_start_sec": finite_source[0] if finite_source else None,
        "source_end_sec": finite_source[-1] if finite_source else None,
        "target_start_sec": finite_target[0] if finite_target else None,
        "target_end_sec": finite_target[-1] if finite_target else None,
        "source_median_dt_sec": source_dt,
        "target_median_dt_sec": target_dt,
        "source_rate_hz_estimate": (1.0 / source_dt) if source_dt else None,
        "target_rate_hz_estimate": (1.0 / target_dt) if target_dt else None,
        "source_timestamps": source_checks,
        "target_timestamps": target_checks,
        "warnings": warnings,
        "errors": errors,
    }


def timestamp_diagnostics(timestamps: Sequence[Any], *, label: str = "timestamps") -> dict[str, Any]:
    """Report missing, duplicate, non-finite, and non-monotonic timestamp issues."""
    values = [_as_float(value) for value in timestamps]
    finite = [value for value in values if value is not None and math.isfinite(value)]
    warnings: list[str] = []
    errors: list[str] = []
    missing_count = len(values) - len(finite)
    if missing_count:
        warnings.append(f"{label} has {missing_count} missing or non-finite timestamp value(s).")

    duplicate_count = 0
    nonmonotonic_count = 0
    large_gap_count = 0
    median_dt = _median_positive_delta(finite)
    largest_gap = None
    if len(finite) >= 2:
        deltas = [finite[index + 1] - finite[index] for index in range(len(finite) - 1)]
        duplicate_count = sum(1 for delta in deltas if delta == 0)
        nonmonotonic_count = sum(1 for delta in deltas if delta < 0)
        positive = [delta for delta in deltas if delta > 0]
        largest_gap = max(positive) if positive else None
        if duplicate_count:
            warnings.append(f"{label} has {duplicate_count} duplicate timestamp interval(s).")
        if nonmonotonic_count:
            errors.append(f"{label} has {nonmonotonic_count} non-monotonic timestamp interval(s).")
        if median_dt and median_dt > 0:
            threshold = median_dt * DEFAULT_GAP_FACTOR
            large_gap_count = sum(1 for delta in positive if delta > threshold)
            if large_gap_count:
                warnings.append(f"{label} has {large_gap_count} large timestamp gap(s), suggesting missing samples.")

    return {
        "schema_version": SCHEMA_VERSION,
        "label": label,
        "count": len(values),
        "finite_count": len(finite),
        "missing_count": missing_count,
        "duplicate_count": duplicate_count,
        "nonmonotonic_count": nonmonotonic_count,
        "large_gap_count": large_gap_count,
        "median_dt_sec": median_dt,
        "largest_gap_sec": largest_gap,
        "start_sec": finite[0] if finite else None,
        "end_sec": finite[-1] if finite else None,
        "status": "failed" if errors else "warning" if warnings else "ok",
        "warnings": warnings,
        "errors": errors,
    }


def _timestamp_sequence(source: Mapping[str, Any], keys: Sequence[str]) -> list[Any]:
    return list(_first_sequence(source, keys))


def _number_sequence(source: Mapping[str, Any], keys: Sequence[str]) -> list[float]:
    values = _first_sequence(source, keys)
    return [value for value in (_as_float(item) for item in values) if value is not None]


def _first_sequence(source: Mapping[str, Any], keys: Sequence[str]) -> Sequence[Any]:
    for key in keys:
        value = source.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            return value
    return []


def _first_float(source: Mapping[str, Any], keys: Sequence[str]) -> float | None:
    for key in keys:
        value = _as_float(source.get(key))
        if value is not None:
            return value
    return None


def _median_positive_delta(values: Sequence[float]) -> float | None:
    finite = _finite_values(values)
    if len(finite) < 2:
        return None
    deltas = [finite[index + 1] - finite[index] for index in range(len(finite) - 1)]
    positive = [delta for delta in deltas if delta > 0 and math.isfinite(delta)]
    if not positive:
        return None
    return float(statistics.median(positive))


def _finite_values(values: Sequence[Any]) -> list[float]:
    return [value for value in (_as_float(item) for item in values) if value is not None]


def _combined_warnings(*reports: Mapping[str, Any]) -> list[str]:
    warnings: list[str] = []
    for report in reports:
        warnings.extend(str(item) for item in report.get("warnings") or [])
    return warnings


def _combined_errors(*reports: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    for report in reports:
        errors.extend(str(item) for item in report.get("errors") or [])
    return errors


def _empty_timestamp_report(label: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "label": label,
        "count": 0,
        "finite_count": 0,
        "missing_count": 0,
        "duplicate_count": 0,
        "nonmonotonic_count": 0,
        "large_gap_count": 0,
        "median_dt_sec": None,
        "largest_gap_sec": None,
        "start_sec": None,
        "end_sec": None,
        "status": "not_tested",
        "warnings": [],
        "errors": [],
    }


def _alignment_notes(status: str) -> str:
    if status == "validated":
        return "Behavior alignment is marked validated and diagnostics did not report warnings."
    if status == "failed":
        return "Behavior alignment diagnostics reported a failure."
    if status == "provided_unvalidated":
        return "Behavior metadata or paths were provided, but validation is incomplete or diagnostic warnings remain."
    return "No behavior alignment metadata was provided."


def _as_float(value: Any) -> float | None:
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None
    return converted if math.isfinite(converted) else None


def _as_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
