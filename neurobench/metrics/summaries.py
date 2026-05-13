"""Population time-series summaries for candidate events and traces."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any

import numpy as np

from neurobench.metrics.event_quality import event_object_id, event_onset_frame


SCHEMA_VERSION = 1


def event_raster_summary(
    events: Sequence[Mapping[str, Any]],
    *,
    frame_count: int | None = None,
    bin_size_frames: int = 1,
    object_ids: Sequence[Any] | None = None,
) -> dict[str, Any]:
    """Return a binned event raster summary grouped by object/ROI ID.

    Event records may use the same frame fields as event-quality metrics:
    ``frame``, ``start_frame``, or ``onset_frame``. Object labels are read from
    ``roi_id``, ``object_id``, ``candidate_id``, ``gt_id``, or ``neuron_id``.
    """

    records = _event_records(events)
    frame_count_value = _frame_count(records, frame_count)
    bin_size_value = int(bin_size_frames)
    bin_count = _bin_count(frame_count_value, bin_size_value)
    ids = _object_ids(records, object_ids)
    index_by_id = {object_id: index for index, object_id in enumerate(ids)}
    raster = np.zeros((len(ids), bin_count), dtype=int)
    dropped = 0

    for record in records:
        frame = int(record["frame"])
        if frame < 0 or frame >= frame_count_value:
            dropped += 1
            continue
        object_id = str(record["object_id"])
        if object_id not in index_by_id:
            dropped += 1
            continue
        raster[index_by_id[object_id], frame // bin_size_value] += 1

    row_sums = raster.sum(axis=1) if raster.size else np.zeros(len(ids), dtype=int)
    rows = [
        {
            "object_id": object_id,
            "event_count": int(row_sums[index]),
            "active_bin_count": int(np.count_nonzero(raster[index])) if bin_count else 0,
        }
        for index, object_id in enumerate(ids)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "summary_type": "event_raster",
        "parameters": {
            "frame_count": frame_count_value,
            "bin_size_frames": bin_size_value,
        },
        "event_count": len(records),
        "dropped_event_count": dropped,
        "object_count": len(ids),
        "bin_count": bin_count,
        "object_ids": ids,
        "bin_edges": _bin_edges(frame_count_value, bin_size_value, bin_count),
        "rows": rows,
        "raster": raster.astype(int).tolist(),
    }


def population_activity_summary(
    events: Sequence[Mapping[str, Any]],
    *,
    frame_count: int | None = None,
    bin_size_frames: int = 1,
    object_ids: Sequence[Any] | None = None,
) -> dict[str, Any]:
    """Return population activity curves derived from a binned event raster."""

    raster_summary = event_raster_summary(
        events,
        frame_count=frame_count,
        bin_size_frames=bin_size_frames,
        object_ids=object_ids,
    )
    raster = np.asarray(raster_summary["raster"], dtype=float)
    if raster.size:
        total_events = raster.sum(axis=0)
        active_objects = np.count_nonzero(raster, axis=0)
    else:
        total_events = np.zeros(raster_summary["bin_count"], dtype=float)
        active_objects = np.zeros(raster_summary["bin_count"], dtype=int)

    object_count = int(raster_summary["object_count"])
    active_fraction = active_objects / object_count if object_count else np.zeros_like(total_events)
    mean_events_per_active = np.divide(
        total_events,
        active_objects,
        out=np.zeros_like(total_events, dtype=float),
        where=active_objects > 0,
    )
    peak_bin_index = int(np.argmax(total_events)) if total_events.size else None
    return {
        "schema_version": SCHEMA_VERSION,
        "summary_type": "population_activity",
        "parameters": dict(raster_summary["parameters"]),
        "event_count": int(raster_summary["event_count"] - raster_summary["dropped_event_count"]),
        "object_count": object_count,
        "bin_count": int(raster_summary["bin_count"]),
        "bin_edges": list(raster_summary["bin_edges"]),
        "total_event_count_by_bin": total_events.astype(int).tolist(),
        "active_object_count_by_bin": active_objects.astype(int).tolist(),
        "active_fraction_by_bin": active_fraction.astype(float).tolist(),
        "mean_events_per_active_object_by_bin": mean_events_per_active.astype(float).tolist(),
        "coactive_bin_count": int(np.count_nonzero(active_objects >= 2)),
        "peak_bin_index": peak_bin_index,
        "peak_event_count": int(total_events[peak_bin_index]) if peak_bin_index is not None else 0,
    }


def event_correlation_summary(
    events: Sequence[Mapping[str, Any]],
    *,
    frame_count: int | None = None,
    bin_size_frames: int = 1,
    object_ids: Sequence[Any] | None = None,
) -> dict[str, Any]:
    """Return pairwise Pearson correlations between object event rasters."""

    raster_summary = event_raster_summary(
        events,
        frame_count=frame_count,
        bin_size_frames=bin_size_frames,
        object_ids=object_ids,
    )
    matrix, pairwise, undefined = _correlation_matrix(
        np.asarray(raster_summary["raster"], dtype=float),
        list(raster_summary["object_ids"]),
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "summary_type": "event_correlation",
        "parameters": dict(raster_summary["parameters"]),
        "event_count": int(raster_summary["event_count"] - raster_summary["dropped_event_count"]),
        "object_count": int(raster_summary["object_count"]),
        "bin_count": int(raster_summary["bin_count"]),
        "object_ids": list(raster_summary["object_ids"]),
        "correlation_matrix": matrix,
        "pairwise_correlations": pairwise,
        "statistics": _correlation_statistics(pairwise, undefined),
    }


def trace_correlation_summary(
    traces: Mapping[Any, Sequence[float]] | Sequence[Any],
    *,
    object_ids: Sequence[Any] | None = None,
) -> dict[str, Any]:
    """Return pairwise Pearson correlations between object traces."""

    ids, trace_array = _trace_array(traces, object_ids=object_ids)
    matrix, pairwise, undefined = _correlation_matrix(trace_array, ids)
    return {
        "schema_version": SCHEMA_VERSION,
        "summary_type": "trace_correlation",
        "parameters": {"trace_length": int(trace_array.shape[1]) if trace_array.ndim == 2 else 0},
        "trace_count": int(trace_array.shape[0]) if trace_array.ndim == 2 else 0,
        "object_count": len(ids),
        "object_ids": ids,
        "correlation_matrix": matrix,
        "pairwise_correlations": pairwise,
        "statistics": _correlation_statistics(pairwise, undefined),
    }


def population_time_series_summary(
    *,
    events: Sequence[Mapping[str, Any]] | None = None,
    traces: Mapping[Any, Sequence[float]] | Sequence[Any] | None = None,
    frame_count: int | None = None,
    bin_size_frames: int = 1,
    object_ids: Sequence[Any] | None = None,
) -> dict[str, Any]:
    """Return a combined schema-versioned summary for events and/or traces."""

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "summary_type": "population_time_series",
        "parameters": {
            "frame_count": frame_count,
            "bin_size_frames": int(bin_size_frames),
        },
    }
    if events is not None:
        payload["event_raster"] = event_raster_summary(
            events,
            frame_count=frame_count,
            bin_size_frames=bin_size_frames,
            object_ids=object_ids,
        )
        payload["population_activity"] = population_activity_summary(
            events,
            frame_count=frame_count,
            bin_size_frames=bin_size_frames,
            object_ids=object_ids,
        )
        payload["event_correlation"] = event_correlation_summary(
            events,
            frame_count=frame_count,
            bin_size_frames=bin_size_frames,
            object_ids=object_ids,
        )
    if traces is not None:
        payload["trace_correlation"] = trace_correlation_summary(traces, object_ids=object_ids)
    return payload


def _event_records(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for index, event in enumerate(events):
        records.append(
            {
                "index": index,
                "frame": event_onset_frame(event),
                "object_id": event_object_id(event) or "unassigned",
            }
        )
    return records


def _frame_count(records: Sequence[Mapping[str, Any]], frame_count: int | None) -> int:
    if frame_count is not None:
        if int(frame_count) < 0:
            raise ValueError("frame_count must be non-negative")
        return int(frame_count)
    nonnegative_frames = [int(record["frame"]) for record in records if int(record["frame"]) >= 0]
    return max(nonnegative_frames) + 1 if nonnegative_frames else 0


def _bin_count(frame_count: int, bin_size_frames: int) -> int:
    if int(bin_size_frames) <= 0:
        raise ValueError("bin_size_frames must be positive")
    return int(math.ceil(frame_count / int(bin_size_frames))) if frame_count else 0


def _object_ids(records: Sequence[Mapping[str, Any]], object_ids: Sequence[Any] | None) -> list[str]:
    if object_ids is not None:
        return [str(object_id) for object_id in object_ids]
    return sorted({str(record["object_id"]) for record in records})


def _bin_edges(frame_count: int, bin_size_frames: int, bin_count: int) -> list[list[int]]:
    return [
        [index * int(bin_size_frames), min(frame_count, (index + 1) * int(bin_size_frames))]
        for index in range(bin_count)
    ]


def _trace_array(
    traces: Mapping[Any, Sequence[float]] | Sequence[Any],
    *,
    object_ids: Sequence[Any] | None,
) -> tuple[list[str], np.ndarray]:
    if isinstance(traces, Mapping):
        keys = list(object_ids) if object_ids is not None else sorted(traces, key=lambda value: str(value))
        ids = [str(object_id) for object_id in keys]
        rows = [traces[key] if key in traces else traces[str(key)] for key in keys]
    else:
        ids, rows = _trace_rows_from_sequence(traces, object_ids)

    array = np.asarray(rows, dtype=float)
    if array.ndim != 2:
        raise ValueError("traces must form a two-dimensional array")
    if array.shape[1] == 0:
        raise ValueError("traces must contain at least one sample")
    if len(ids) != array.shape[0]:
        raise ValueError("object_ids length must match trace count")
    return ids, array


def _trace_rows_from_sequence(
    traces: Sequence[Any],
    object_ids: Sequence[Any] | None,
) -> tuple[list[str], list[Any]]:
    ids: list[str] = []
    rows: list[Any] = []
    for index, item in enumerate(traces):
        if isinstance(item, Mapping):
            ids.append(_trace_object_id(item, index))
            rows.append(_trace_values(item))
        else:
            ids.append(str(index))
            rows.append(item)
    if object_ids is not None:
        ids = [str(object_id) for object_id in object_ids]
    return ids, rows


def _trace_object_id(item: Mapping[str, Any], fallback_index: int) -> str:
    for key in ("roi_id", "object_id", "candidate_id", "neuron_id", "id"):
        if key in item and item[key] is not None:
            return str(item[key])
    return str(fallback_index)


def _trace_values(item: Mapping[str, Any]) -> Any:
    for key in ("trace", "dff", "activity", "values", "spikes"):
        if key in item and item[key] is not None:
            return item[key]
    raise ValueError(f"Trace record is missing trace values: {item!r}")


def _correlation_matrix(trace_array: np.ndarray, object_ids: list[str]) -> tuple[list[list[float]], list[dict[str, Any]], int]:
    object_count = int(trace_array.shape[0]) if trace_array.ndim == 2 else 0
    matrix = np.eye(object_count, dtype=float)
    undefined = 0
    for i in range(object_count):
        for j in range(i + 1, object_count):
            correlation, is_defined = _pearson(trace_array[i], trace_array[j])
            if not is_defined:
                undefined += 1
            matrix[i, j] = correlation
            matrix[j, i] = correlation

    pairwise = [
        {
            "object_id_a": object_ids[i],
            "object_id_b": object_ids[j],
            "correlation": float(matrix[i, j]),
        }
        for i in range(object_count)
        for j in range(i + 1, object_count)
    ]
    return matrix.astype(float).tolist(), pairwise, undefined


def _pearson(a: np.ndarray, b: np.ndarray) -> tuple[float, bool]:
    if a.size != b.size:
        raise ValueError("trace rows must have equal length")
    if a.size == 0:
        return 0.0, False
    centered_a = a.astype(float) - float(np.mean(a))
    centered_b = b.astype(float) - float(np.mean(b))
    denom = float(np.linalg.norm(centered_a) * np.linalg.norm(centered_b))
    if denom == 0.0:
        return 0.0, False
    return float(np.dot(centered_a, centered_b) / denom), True


def _correlation_statistics(pairwise: Sequence[Mapping[str, Any]], undefined_pair_count: int) -> dict[str, float | int]:
    values = [float(item["correlation"]) for item in pairwise]
    return {
        "pair_count": len(values),
        "undefined_pair_count": int(undefined_pair_count),
        "mean_correlation": float(sum(values) / len(values)) if values else 0.0,
        "min_correlation": float(min(values)) if values else 0.0,
        "max_correlation": float(max(values)) if values else 0.0,
    }
