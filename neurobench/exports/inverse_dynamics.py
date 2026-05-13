"""Inverse-dynamics export helpers."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from neurobench.annotations import migrate_annotations_v3
from neurobench.exports.behavior_alignment import alignment_report as build_behavior_alignment_report
from neurobench.exports.behavior_alignment import frame_time_sec as behavior_frame_time_sec
from neurobench.models.exports import ExportBundle


TRACE_COLUMNS = ["roi_id", "frame", "time_sec", "dff", "event_trace", "z", "cell_state", "trace_quality", "control_ready"]
EVENT_COLUMNS = [
    "roi_id",
    "frame",
    "time_sec",
    "z",
    "amplitude",
    "event_state",
    "event_type",
    "timing_quality",
    "cell_state",
    "control_ready",
]
METADATA_COLUMNS = [
    "roi_id",
    "cell_state",
    "trace_quality",
    "control_ready",
    "artifact_class",
    "identity_group",
    "confidence",
    "reason_tags",
]


def export_inverse_dynamics_bundle(
    review_data: Mapping[str, Any],
    annotations: Mapping[str, Any] | None,
    out_dir: str | Path,
    *,
    dataset_manifest: Mapping[str, Any] | None = None,
    include_pending: bool = False,
    created_at: str | None = None,
    provenance: Mapping[str, Any] | None = None,
) -> ExportBundle:
    """Write inverse-dynamics tables and an ExportBundle manifest."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ann = migrate_annotations_v3(annotations)
    dataset_context = export_context(review_data, dataset_manifest)
    alignment = alignment_report(dataset_context)
    selected_rois = _selected_rois(review_data, ann, include_pending=include_pending)
    trace_rows = _trace_rows(selected_rois, ann, frame_rate_hz=dataset_context.get("frame_rate_hz"))
    event_rows = _event_rows(selected_rois, ann, frame_rate_hz=dataset_context.get("frame_rate_hz"))
    metadata_rows = _metadata_rows(selected_rois, ann)

    trace_path = out / "accepted_traces.tsv"
    event_path = out / "accepted_events.tsv"
    metadata_path = out / "neuron_metadata.tsv"
    alignment_path = out / "alignment_report.json"
    checksums_path = out / "checksums.json"
    report_path = out / "export_report.md"
    _write_tsv(trace_path, TRACE_COLUMNS, trace_rows)
    _write_tsv(event_path, EVENT_COLUMNS, event_rows)
    _write_tsv(metadata_path, METADATA_COLUMNS, metadata_rows)
    _write_json(alignment_path, alignment)

    files = [
        _file_record("accepted_traces", trace_path, "tsv", "Frame-wise traces for selected ROIs.", rows=len(trace_rows)),
        _file_record("accepted_events", event_path, "tsv", "Event rows for selected ROIs.", rows=len(event_rows)),
        _file_record("neuron_metadata", metadata_path, "tsv", "Selected ROI metadata.", rows=len(metadata_rows)),
        _file_record("alignment_report", alignment_path, "json", "Behavior/timebase alignment status."),
    ]
    checksums = {item["path"]: item["sha256"] for item in files if item.get("sha256")}
    _write_json(checksums_path, checksums)
    files.append(_file_record("checksums", checksums_path, "json", "SHA-256 checksums for exported files."))

    warnings = []
    if alignment["status"] != "validated":
        warnings.append(f"Alignment status is {alignment['status']}; behavior-coupled inverse dynamics should validate alignment before modeling.")
    warnings.extend(str(item) for item in alignment.get("warnings") or [])
    if include_pending:
        warnings.append("Export includes pending/unreviewed ROIs.")

    bundle = ExportBundle(
        schema_version=1,
        export_bundle_id="inverse_dynamics_export",
        dataset_id=str(dataset_context.get("dataset_id") or _dataset_id(review_data)),
        run_ids=_run_ids(review_data),
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
        profile="inverse_dynamics",
        selection_policy={
            "name": "inverse_dynamics_control_ready" if not include_pending else "inverse_dynamics_include_pending",
            "description": "Accepted, trace-usable, control-ready ROIs for inverse-dynamics modeling."
            if not include_pending
            else "All candidate ROIs for inverse-dynamics debugging.",
            "include_rois": "accepted_control_ready" if not include_pending else "all",
            "include_events": "selected_roi_events",
            "review_state_required": ["accepted"] if not include_pending else [],
            "trace_quality_allowed": ["good", "weak"] if not include_pending else [],
            "control_ready_allowed": ["yes", "maybe"] if not include_pending else [],
        },
        alignment_status=str(alignment["status"]),
        alignment=alignment,
        files=files,
        checksums={item["path"]: item["sha256"] for item in files if item.get("sha256")},
        warnings=warnings,
        provenance=dict(provenance or {}),
        extras={"dataset": dataset_context, "selected_roi_ids": [str(roi.get("id")) for roi in selected_rois]},
    )
    bundle.validate()
    _write_text(report_path, render_inverse_dynamics_export_report(bundle, trace_rows=len(trace_rows), event_rows=len(event_rows)))
    bundle.files.append(_file_record("export_report", report_path, "md", "Human-readable export summary."))
    bundle.checksums = {item["path"]: item["sha256"] for item in bundle.files if item.get("sha256")}
    _write_json(checksums_path, bundle.checksums)
    bundle.write_json(out / "export_bundle.json")
    return bundle


def render_inverse_dynamics_export_report(bundle: ExportBundle, *, trace_rows: int, event_rows: int) -> str:
    """Render a compact Markdown report for the inverse-dynamics export."""
    lines = [
        "# Inverse-Dynamics Export",
        "",
        f"- Dataset ID: `{bundle.dataset_id}`",
        f"- Selected ROIs: {len(bundle.extras.get('selected_roi_ids', []))}",
        f"- Trace rows: {trace_rows}",
        f"- Event rows: {event_rows}",
        f"- Alignment status: `{bundle.alignment_status}`",
        f"- Selection policy: `{bundle.selection_policy.get('name', '')}`",
        "",
        "## Files",
        "",
    ]
    for item in bundle.files:
        lines.append(f"- `{item['path']}`: {item.get('description', item['kind'])}")
    lines.extend(["", "## Limitations", ""])
    if bundle.warnings:
        lines.extend(f"- {warning}" for warning in bundle.warnings)
    else:
        lines.append("- No export warnings were reported.")
    return "\n".join(lines).rstrip() + "\n"


def export_context(review_data: Mapping[str, Any], dataset_manifest: Mapping[str, Any] | None) -> dict[str, Any]:
    """Collect dataset and behavior metadata relevant to inverse-dynamics export."""
    dataset = review_data.get("dataset", {}) if isinstance(review_data.get("dataset"), Mapping) else {}
    context = {
        "dataset_id": dataset.get("dataset_id") or review_data.get("dataset_id"),
        "frame_rate_hz": dataset.get("frame_rate_hz") or review_data.get("frame_rate_hz"),
        "pixel_size_microns": dataset.get("pixel_size_microns") or review_data.get("pixel_size_microns"),
    }
    video = review_data.get("video") if isinstance(review_data.get("video"), Mapping) else {}
    if video.get("frames") is not None:
        context["imaging_frame_count"] = video.get("frames")
    elif review_data.get("rois"):
        context["imaging_frame_count"] = max(
            (len(roi.get("dffTrace", []) or []) for roi in review_data.get("rois", []) if isinstance(roi, Mapping)),
            default=0,
        )
    for key in ("frame_timestamps_sec", "imaging_timestamps_sec", "timestamps_sec"):
        if review_data.get(key) is not None:
            context[key] = review_data[key]
    if dataset_manifest:
        for key in ("dataset_id", "name", "modality", "indicator", "frame_rate_hz", "pixel_size_microns"):
            if dataset_manifest.get(key) is not None:
                context[key] = dataset_manifest[key]
        if dataset_manifest.get("behavior"):
            context["behavior"] = dict(dataset_manifest.get("behavior") or {})
        paths = dict(dataset_manifest.get("paths") or {})
        behavior_paths = {
            key: paths[key]
            for key in ("behavior_video", "tail_motion", "tail_points", "stimulus_log", "sync_table")
            if paths.get(key)
        }
        if behavior_paths:
            context["behavior_paths"] = behavior_paths
    return context


def alignment_report(dataset_context: Mapping[str, Any]) -> dict[str, Any]:
    """Return an explicit alignment-status report using ExportBundle status names."""
    return build_behavior_alignment_report(dataset_context)


def frame_time_sec(frame_index_zero_based: int, frame_rate_hz: float | int | None) -> float | None:
    return behavior_frame_time_sec(frame_index_zero_based, frame_rate_hz)


def _selected_rois(review_data: Mapping[str, Any], ann: Mapping[str, Any], *, include_pending: bool) -> list[Mapping[str, Any]]:
    selected = []
    for roi in review_data.get("rois", []) or []:
        item = dict((ann.get("rois") or {}).get(str(roi.get("id")), {}))
        if include_pending or _include_control_ready_roi(item):
            selected.append(roi)
    return selected


def _include_control_ready_roi(item: Mapping[str, Any]) -> bool:
    return (
        item.get("cell_state") == "accepted"
        and item.get("trace_quality") in {"good", "weak"}
        and item.get("control_ready") in {"yes", "maybe"}
        and item.get("artifact_class") in {"", "none", None}
    )


def _trace_rows(rois: list[Mapping[str, Any]], ann: Mapping[str, Any], *, frame_rate_hz: Any) -> list[dict[str, str]]:
    rows = []
    for roi in rois:
        roi_id = str(roi.get("id"))
        item = dict((ann.get("rois") or {}).get(roi_id, {}))
        dff = list(roi.get("dffTrace", []) or [])
        event_trace = list(roi.get("eventTrace", []) or [])
        z_trace = list(roi.get("zTrace", []) or [])
        for index, value in enumerate(dff):
            rows.append(
                {
                    "roi_id": _clean(roi_id),
                    "frame": _clean(index + 1),
                    "time_sec": _clean(frame_time_sec(index, frame_rate_hz)),
                    "dff": _clean(value),
                    "event_trace": _clean(event_trace[index] if index < len(event_trace) else ""),
                    "z": _clean(z_trace[index] if index < len(z_trace) else ""),
                    "cell_state": _clean(item.get("cell_state", "")),
                    "trace_quality": _clean(item.get("trace_quality", "")),
                    "control_ready": _clean(item.get("control_ready", "")),
                }
            )
    return rows


def _event_rows(rois: list[Mapping[str, Any]], ann: Mapping[str, Any], *, frame_rate_hz: Any) -> list[dict[str, str]]:
    rows = []
    for roi in rois:
        roi_id = str(roi.get("id"))
        roi_item = dict((ann.get("rois") or {}).get(roi_id, {}))
        for event in roi.get("events", []) or []:
            frame = event.get("frame")
            event_item = dict((ann.get("events") or {}).get(f"{roi_id}:{frame}", {}))
            frame_index = _as_int(frame, default=1) - 1
            rows.append(
                {
                    "roi_id": _clean(roi_id),
                    "frame": _clean(frame),
                    "time_sec": _clean(frame_time_sec(frame_index, frame_rate_hz)),
                    "z": _clean(event.get("z")),
                    "amplitude": _clean(event.get("amplitude")),
                    "event_state": _clean(event_item.get("event_state", "")),
                    "event_type": _clean(event_item.get("event_type", "")),
                    "timing_quality": _clean(event_item.get("timing_quality", "")),
                    "cell_state": _clean(roi_item.get("cell_state", "")),
                    "control_ready": _clean(roi_item.get("control_ready", "")),
                }
            )
    return rows


def _metadata_rows(rois: list[Mapping[str, Any]], ann: Mapping[str, Any]) -> list[dict[str, str]]:
    rows = []
    for roi in rois:
        roi_id = str(roi.get("id"))
        item = dict((ann.get("rois") or {}).get(roi_id, {}))
        rows.append(
            {
                "roi_id": _clean(roi_id),
                "cell_state": _clean(item.get("cell_state", "")),
                "trace_quality": _clean(item.get("trace_quality", "")),
                "control_ready": _clean(item.get("control_ready", "")),
                "artifact_class": _clean(item.get("artifact_class", "")),
                "identity_group": _clean(item.get("identity_group", "")),
                "confidence": _clean(item.get("confidence", "")),
                "reason_tags": _clean(",".join(str(tag) for tag in item.get("reason_tags", []) or [])),
            }
        )
    return rows


def _write_tsv(path: Path, columns: list[str], rows: list[Mapping[str, Any]]) -> None:
    lines = ["\t".join(columns)]
    for row in rows:
        lines.append("\t".join(_clean(row.get(column, "")) for column in columns))
    _write_text(path, "\n".join(lines) + "\n")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    _write_text(path, json.dumps(dict(payload), indent=2, sort_keys=True) + "\n")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _file_record(kind: str, path: Path, file_format: str, description: str, *, rows: int | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "kind": kind,
        "path": path.name,
        "format": file_format,
        "sha256": _sha256_file(path),
        "description": description,
    }
    if rows is not None:
        record["rows"] = int(rows)
    return record


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _alignment_notes(status: str) -> str:
    if status == "validated":
        return "Behavior alignment is marked validated in dataset metadata."
    if status == "failed":
        return "Behavior alignment metadata reports failure."
    if status == "provided_unvalidated":
        return "Behavior metadata or paths were provided, but validation was not recorded."
    return "No behavior alignment metadata was provided."


def _dataset_id(review_data: Mapping[str, Any]) -> str:
    dataset = review_data.get("dataset") if isinstance(review_data.get("dataset"), Mapping) else {}
    return str(dataset.get("dataset_id") or review_data.get("dataset_id") or "unknown_dataset")


def _run_ids(review_data: Mapping[str, Any]) -> list[str]:
    runs = review_data.get("runs")
    if isinstance(runs, list):
        ids = [str(item.get("run_id")) for item in runs if isinstance(item, Mapping) and item.get("run_id")]
        if ids:
            return ids
    run_id = review_data.get("run_id")
    return [str(run_id)] if run_id else []


def _clean(value: Any) -> str:
    return str(value if value is not None else "").replace("\t", " ").replace("\n", " ")


def _as_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
