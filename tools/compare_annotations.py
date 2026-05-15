#!/usr/bin/env python3
"""Compare two Neurobench annotation files for inter-rater review."""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from neurobench.manifests import load_json, write_json
from neurobench.review.agreement import (
    agreement_report_markdown,
    annotation_agreement_report,
    disagreement_tsv_rows,
)


def annotation_scope(payload: dict[str, Any], run_id: str | None) -> dict[str, Any]:
    """Return top-level annotations or a run-scoped annotation bucket."""

    if not run_id:
        return payload
    bucket = (payload.get("runs") or {}).get(run_id)
    if bucket is None:
        raise SystemExit(f"Run '{run_id}' was not found in annotations file.")
    scoped = {
        "schema_version": payload.get("schema_version", 3),
        "updatedAt": payload.get("updatedAt"),
        "settings": dict(payload.get("settings") or {}, activeRunId=run_id),
        "reviewStats": payload.get("reviewStats") or {},
    }
    for key in ("rois", "events", "suggestions", "promotedRois", "virtualRois", "splitMergeDecisions"):
        scoped[key] = dict(bucket.get(key) or {})
    return scoped


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "subject_group",
        "subject_id",
        "label_a",
        "label_b",
        "reviewer_a",
        "reviewer_b",
        "both_labeled",
        "exact_agreement",
        "confidence_a",
        "confidence_b",
        "artifact_a",
        "artifact_b",
        "source_reviewer_id_a",
        "source_reviewer_id_b",
        "updated_at_a",
        "updated_at_b",
        "reason_tags_a",
        "reason_tags_b",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two Neurobench annotation files.")
    parser.add_argument("--annotations-a", type=Path, required=True)
    parser.add_argument("--annotations-b", type=Path, required=True)
    parser.add_argument("--reviewer-a", default="reviewer_a")
    parser.add_argument("--reviewer-b", default="reviewer_b")
    parser.add_argument("--run-id", default=None, help="Compare a specific run-scoped annotation bucket.")
    parser.add_argument(
        "--subject-groups",
        default="rois,events,suggestions",
        help="Comma-separated groups to compare. Default: rois,events,suggestions.",
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--max-markdown-disagreements", type=int, default=50)
    parser.add_argument(
        "--require-reviewer-provenance",
        action="store_true",
        help="Exit with status 2 if either compared annotation file has reviewed labels missing reviewer_id.",
    )
    args = parser.parse_args()

    groups = [item.strip() for item in args.subject_groups.split(",") if item.strip()]
    annotations_a = annotation_scope(load_json(args.annotations_a), args.run_id)
    annotations_b = annotation_scope(load_json(args.annotations_b), args.run_id)
    report = annotation_agreement_report(
        annotations_a,
        annotations_b,
        reviewer_a_id=args.reviewer_a,
        reviewer_b_id=args.reviewer_b,
        subject_groups=groups,
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / "agreement_report.json"
    md_path = args.out_dir / "agreement_report.md"
    tsv_path = args.out_dir / "disagreement_queue.tsv"
    write_json(json_path, report)
    md_path.write_text(agreement_report_markdown(report, max_disagreements=args.max_markdown_disagreements), encoding="utf-8")
    write_tsv(tsv_path, disagreement_tsv_rows(report))
    print(f"Wrote agreement report to {json_path}")
    print(f"Wrote disagreement queue to {tsv_path}")
    print(f"Wrote Markdown brief to {md_path}")
    print(f"disagreements: {len(report.get('disagreement_queue', []) or [])}")
    missing = {
        reviewer: int((summary or {}).get("missing_reviewer_total", 0))
        for reviewer, summary in (report.get("reviewer_provenance", {}) or {}).items()
    }
    missing_total = sum(missing.values())
    if missing_total:
        detail = ", ".join(f"{reviewer}: {count}" for reviewer, count in missing.items() if count)
        print(f"missing reviewer provenance: {missing_total} ({detail})")
    if args.require_reviewer_provenance and missing_total:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
