#!/usr/bin/env python3
"""Build a reproducible next-review annotation batch."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from neurobench.manifests import load_json, write_json
from neurobench.review_batches import (
    DEFAULT_TARGET_EVENTS,
    DEFAULT_TARGET_ROIS,
    DEFAULT_TARGET_SUGGESTIONS,
    build_annotation_batch,
    review_task_feature_rows,
    review_progress,
)


def _write_tsv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            flattened = dict(row)
            flattened["reasons"] = "; ".join(str(item) for item in row.get("reasons", []))
            if isinstance(row.get("reason_codes"), list):
                flattened["reason_codes"] = ",".join(str(item) for item in row.get("reason_codes", []))
            writer.writerow(flattened)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a next-review annotation batch from review data and annotations.")
    parser.add_argument("--review-data", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="Output JSON batch path.")
    parser.add_argument("--out-dir", type=Path, default=None, help="Optional directory for TSV exports.")
    parser.add_argument("--target-rois", type=int, default=DEFAULT_TARGET_ROIS)
    parser.add_argument("--target-events", type=int, default=DEFAULT_TARGET_EVENTS)
    parser.add_argument("--target-suggestions", type=int, default=DEFAULT_TARGET_SUGGESTIONS)
    args = parser.parse_args()

    review_data = load_json(args.review_data)
    annotations = load_json(args.annotations)
    batch = build_annotation_batch(
        review_data,
        annotations,
        target_rois=args.target_rois,
        target_events=args.target_events,
        target_suggestions=args.target_suggestions,
    )
    payload = {
        "dataset_id": review_data.get("dataset", {}).get("dataset_id") or review_data.get("video", {}).get("name"),
        "review_data": str(args.review_data),
        "annotations": str(args.annotations),
        "review_progress": review_progress(review_data, annotations),
        "batch": batch,
    }
    write_json(args.out, payload)

    if args.out_dir:
        _write_tsv(
            args.out_dir / "next_rois.tsv",
            batch["rois"],
            ["roi_id", "score", "category", "event_count", "area", "trace_snr", "artifact_score", "reasons"],
        )
        _write_tsv(
            args.out_dir / "next_events.tsv",
            batch["events"],
            ["roi_id", "frame", "score", "z", "amplitude", "reasons"],
        )
        _write_tsv(
            args.out_dir / "next_suggestions.tsv",
            batch["suggestions"],
            ["suggestion_id", "score", "area", "artifact_score", "artifact_cue", "reasons"],
        )
        _write_tsv(
            args.out_dir / "review_tasks.tsv",
            batch["tasks"],
            ["task_id", "task_type", "subject_id", "priority_score", "prompt", "reason_codes", "reasons"],
        )
        _write_tsv(
            args.out_dir / "review_task_features.tsv",
            review_task_feature_rows(review_data, annotations),
            [
                "subject_type",
                "subject_id",
                "label_state",
                "priority_score",
                "event_count",
                "area",
                "trace_snr",
                "local_correlation",
                "event_support",
                "artifact_score",
                "reason_codes",
            ],
        )

    print(
        "Wrote "
        f"{args.out} with {len(batch['rois'])} ROIs, "
        f"{len(batch['events'])} events, and {len(batch['suggestions'])} suggestions"
    )


if __name__ == "__main__":
    main()
