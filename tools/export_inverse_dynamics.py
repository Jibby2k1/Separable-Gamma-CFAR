#!/usr/bin/env python3
"""Export reviewed neuron traces and event features for inverse-dynamics work."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from neurobench.annotations import migrate_annotations_v3
from neurobench.manifests import load_dataset_manifest, load_json, write_json


def clean(value) -> str:
    return str(value if value is not None else "").replace("\t", " ").replace("\n", " ")


def include_roi(item: dict, include_pending: bool) -> bool:
    if include_pending:
        return True
    return (
        item.get("cell_state") == "accepted"
        and item.get("trace_quality") in {"good", "weak"}
        and item.get("control_ready") in {"yes", "maybe"}
        and item.get("artifact_class") in {"", "none", None}
    )


def export_context(review: dict, dataset_manifest: dict | None) -> dict:
    dataset = review.get("dataset", {})
    context = {
        "dataset_id": dataset.get("dataset_id") or review.get("dataset_id"),
        "frame_rate_hz": dataset.get("frame_rate_hz"),
        "pixel_size_microns": dataset.get("pixel_size_microns"),
    }
    if not dataset_manifest:
        return context

    for key in ["dataset_id", "name", "modality", "indicator", "frame_rate_hz", "pixel_size_microns"]:
        if key in dataset_manifest and dataset_manifest[key] is not None:
            context[key] = dataset_manifest[key]

    behavior = dataset_manifest.get("behavior")
    if behavior:
        context["behavior"] = behavior
    paths = dataset_manifest.get("paths", {})
    behavior_paths = {
        key: paths[key]
        for key in ["behavior_video", "tail_motion", "tail_points", "stimulus_log", "sync_table"]
        if paths.get(key)
    }
    if behavior_paths:
        context["behavior_paths"] = behavior_paths
    return context


def frame_time_sec(frame_index_zero_based: int, frame_rate_hz: float | int | None) -> float | None:
    try:
        rate = float(frame_rate_hz)
    except (TypeError, ValueError):
        return None
    if rate <= 0:
        return None
    return frame_index_zero_based / rate


def alignment_status(dataset_context: dict) -> dict:
    behavior_paths = dataset_context.get("behavior_paths", {})
    behavior = dataset_context.get("behavior", {})
    has_behavior = bool(behavior_paths)
    return {
        "status": "metadata_ready" if has_behavior else "not_aligned",
        "has_behavior_paths": has_behavior,
        "sync_offset_frames": behavior.get("sync_offset_frames"),
        "notes": "Tail-motion alignment not computed by this export.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export accepted/control-ready traces for inverse dynamics.")
    parser.add_argument("--review-data", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, help="Optional dataset manifest with behavior/sync metadata.")
    parser.add_argument("--include-pending", action="store_true", help="Export all candidate ROIs instead of only accepted/control-ready ROIs.")
    args = parser.parse_args()

    review = load_json(args.review_data)
    ann = migrate_annotations_v3(load_json(args.annotations))
    dataset_manifest = load_dataset_manifest(args.dataset_manifest) if args.dataset_manifest else None
    dataset_context = export_context(review, dataset_manifest)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    frame_rate_hz = dataset_context.get("frame_rate_hz")
    trace_rows = ["roi_id\tframe\ttime_sec\tdff\tevent_trace\tz\tcell_state\ttrace_quality\tcontrol_ready"]
    event_rows = ["roi_id\tframe\ttime_sec\tz\tamplitude\tevent_state\tevent_type\ttiming_quality\tcell_state\tcontrol_ready"]
    selected = []
    for roi in review.get("rois", []):
        roi_id = str(roi.get("id"))
        item = ann["rois"].get(roi_id, {})
        if not include_roi(item, args.include_pending):
            continue
        selected.append(int(roi.get("id")))
        dff = roi.get("dffTrace", [])
        event_trace = roi.get("eventTrace", [])
        z_trace = roi.get("zTrace", [])
        for i, value in enumerate(dff):
            trace_rows.append(
                "\t".join(
                    [
                        clean(roi_id),
                        clean(i + 1),
                        clean(frame_time_sec(i, frame_rate_hz)),
                        clean(value),
                        clean(event_trace[i] if i < len(event_trace) else ""),
                        clean(z_trace[i] if i < len(z_trace) else ""),
                        clean(item.get("cell_state", "")),
                        clean(item.get("trace_quality", "")),
                        clean(item.get("control_ready", "")),
                    ]
                )
            )
        for event in roi.get("events", []):
            event_item = ann["events"].get(f"{roi_id}:{event.get('frame')}", {})
            try:
                event_frame_index = int(event.get("frame", 1)) - 1
            except (TypeError, ValueError):
                event_frame_index = 0
            event_rows.append(
                "\t".join(
                    [
                        clean(roi_id),
                        clean(event.get("frame")),
                        clean(frame_time_sec(event_frame_index, frame_rate_hz)),
                        clean(event.get("z")),
                        clean(event.get("amplitude")),
                        clean(event_item.get("event_state", "")),
                        clean(event_item.get("event_type", "")),
                        clean(event_item.get("timing_quality", "")),
                        clean(item.get("cell_state", "")),
                        clean(item.get("control_ready", "")),
                    ]
                )
            )

    (args.out_dir / "control_ready_traces.tsv").write_text("\n".join(trace_rows) + "\n")
    (args.out_dir / "event_features.tsv").write_text("\n".join(event_rows) + "\n")
    write_json(
        args.out_dir / "inverse_dynamics_export_summary.json",
        {
            "source_review_data": str(args.review_data),
            "source_annotations": str(args.annotations),
            "include_pending": args.include_pending,
            "selected_roi_count": len(selected),
            "selected_roi_ids": selected,
            "frame_count": review.get("video", {}).get("frames"),
            "frame_rate_hz": dataset_context.get("frame_rate_hz"),
            "dataset": dataset_context,
            "alignment": alignment_status(dataset_context),
        },
    )
    print(f"Wrote inverse-dynamics exports to {args.out_dir}")


if __name__ == "__main__":
    main()
