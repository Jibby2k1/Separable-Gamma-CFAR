#!/usr/bin/env python3
"""Convert current review_data.json into a standardized architecture run."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from neurobench.annotation_metrics import compute_annotation_summary
from neurobench.manifests import load_json, write_json


def build_run(review_data_path: Path, dataset_id: str, run_id: str, label: str, annotations_path: Path | None = None) -> dict:
    review_data = load_json(review_data_path)
    app_dir = review_data_path.parent
    run = {
        "schema_version": 1,
        "run_id": run_id,
        "dataset_id": dataset_id,
        "label": label,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pipeline": [
            {"name": "review_data_import"},
            {"name": "trace_event_scoring", "params": {"event_threshold_z": review_data.get("parameters", {}).get("eventZThreshold")}},
        ],
        "parameters": review_data.get("parameters", {}),
        "summary": {
            "roi_count": len(review_data.get("rois", [])),
            "event_count": sum(len(roi.get("events", [])) for roi in review_data.get("rois", [])),
            "suggestion_count": len(review_data.get("discovery", {}).get("suggestions", [])),
            "frame_count": review_data.get("video", {}).get("frames"),
        },
        "artifacts": {
            "review_data": str(review_data_path),
            "frames": str(app_dir / "frames"),
            "evidence_maps": review_data.get("discovery", {}).get("evidenceMaps", []),
            "roi_summary_tsv": str(app_dir / "roi_summary.tsv"),
            "discovery_suggestions_tsv": str(app_dir / "discovery_suggestions.tsv"),
        },
    }
    if annotations_path and annotations_path.exists():
        run["annotation_summary"] = compute_annotation_summary(review_data, load_json(annotations_path))
        run["artifacts"]["annotations"] = str(annotations_path)
    return run


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a standardized architecture-run manifest from review_data.json.")
    parser.add_argument("--review-data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dataset-id", default="calcium_video_2")
    parser.add_argument("--run-id", default="current_fiji_groovy_review")
    parser.add_argument("--label", default="Current Fiji/Groovy review pipeline")
    parser.add_argument("--annotations", type=Path, default=None)
    args = parser.parse_args()

    run = build_run(args.review_data, args.dataset_id, args.run_id, args.label, args.annotations)
    write_json(args.out, {"schema_version": 1, "dataset_id": args.dataset_id, "runs": [run]})
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
