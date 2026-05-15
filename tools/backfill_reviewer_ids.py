#!/usr/bin/env python3
"""Backfill reviewer_id provenance into reviewed Neurobench annotations."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from neurobench.manifests import load_json, write_json
from neurobench.review.provenance import backfill_reviewer_ids, reviewer_provenance_summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill reviewer_id on reviewed Neurobench annotation items.")
    parser.add_argument("--annotations", type=Path, required=True, help="Input annotations.json path.")
    parser.add_argument("--reviewer-id", default="", help="Reviewer ID/initials to stamp.")
    parser.add_argument("--out", type=Path, default=None, help="Output annotations path. Required unless --in-place is set.")
    parser.add_argument("--in-place", action="store_true", help="Overwrite the input annotations file.")
    parser.add_argument("--run-id", default=None, help="Only stamp one run-scoped annotation bucket.")
    parser.add_argument("--all-runs", action="store_true", help="Stamp every run-scoped annotation bucket instead of top-level annotations.")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing reviewer_id values.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be stamped without writing an annotation file.")
    parser.add_argument("--audit-only", action="store_true", help="Only report reviewer provenance coverage; do not stamp labels.")
    parser.add_argument("--summary-json", type=Path, default=None, help="Optional path for the provenance summary JSON.")
    args = parser.parse_args()

    if args.audit_only and args.reviewer_id:
        raise SystemExit("--audit-only does not use --reviewer-id.")
    if not args.audit_only and not args.reviewer_id:
        raise SystemExit("--reviewer-id is required unless --audit-only is set.")
    if args.in_place and args.out:
        raise SystemExit("Use either --out or --in-place, not both.")
    if not args.audit_only and not args.dry_run and not args.in_place and not args.out:
        raise SystemExit("--out is required unless --in-place is set.")
    if (args.dry_run or args.audit_only) and (args.in_place or args.out):
        raise SystemExit("--dry-run cannot be combined with --out or --in-place.")

    annotations = load_json(args.annotations)
    if args.audit_only:
        summary = reviewer_provenance_summary(annotations, run_id=args.run_id, all_runs=args.all_runs)
    else:
        payload = backfill_reviewer_ids(
            annotations,
            args.reviewer_id,
            run_id=args.run_id,
            all_runs=args.all_runs,
            overwrite=args.overwrite,
        )
        summary = payload["reviewer_provenance_backfill"]
    if args.summary_json:
        write_json(args.summary_json, summary)
    if args.audit_only:
        print("Audit only: no annotation file written")
    elif args.dry_run:
        print("Dry run: no annotation file written")
    else:
        out_path = args.annotations if args.in_place else args.out
        write_json(out_path, payload)
        print(f"Wrote reviewer provenance to {out_path}")
    if args.audit_only:
        print(f"reviewed: {summary['reviewed_total']}")
        print(f"with_reviewer: {summary['with_reviewer_total']}")
        print(f"missing_reviewer: {summary['missing_reviewer_total']}")
    else:
        print(f"reviewer_id: {summary['reviewer_id']}")
        print(f"stamped: {summary['stamped_total']}")
        print(f"skipped: {summary['skipped_total']}")
    if (args.dry_run or args.audit_only) and not args.summary_json:
        print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
