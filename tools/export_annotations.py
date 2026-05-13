#!/usr/bin/env python3
"""Export migrated v3 annotations through explicit selection profiles."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from neurobench.exports.annotations import EXPORT_PROFILES, export_annotation_profile
from neurobench.manifests import load_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Neurobench annotations.")
    parser.add_argument("--review-data", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--profile",
        choices=sorted(EXPORT_PROFILES),
        default="accepted_only",
        help="Selection profile to export. Default: accepted_only.",
    )
    args = parser.parse_args()

    review = load_json(args.review_data)
    annotations = load_json(args.annotations)
    bundle = export_annotation_profile(review, annotations, args.out_dir, profile=args.profile)
    print(f"Wrote {args.profile} annotation export to {args.out_dir}")
    print(f"bundle: {args.out_dir / 'export_bundle.json'}")
    print(f"files: {len(bundle.files)}")


if __name__ == "__main__":
    main()
