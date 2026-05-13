#!/usr/bin/env python3
"""Export reviewed neuron traces and event features for inverse-dynamics work."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from neurobench.exports.inverse_dynamics import export_inverse_dynamics_bundle
from neurobench.manifests import load_dataset_manifest, load_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Export accepted/control-ready traces for inverse dynamics.")
    parser.add_argument("--review-data", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, help="Optional dataset manifest with behavior/sync metadata.")
    parser.add_argument("--include-pending", action="store_true", help="Export all candidate ROIs instead of only accepted/control-ready ROIs.")
    args = parser.parse_args()

    review = load_json(args.review_data)
    annotations = load_json(args.annotations)
    dataset_manifest = load_dataset_manifest(args.dataset_manifest) if args.dataset_manifest else None
    bundle = export_inverse_dynamics_bundle(
        review,
        annotations,
        args.out_dir,
        dataset_manifest=dataset_manifest,
        include_pending=args.include_pending,
        provenance={"review_data": str(args.review_data), "annotations": str(args.annotations)},
    )
    print(f"Wrote inverse-dynamics exports to {args.out_dir}")
    print(f"bundle: {args.out_dir / 'export_bundle.json'}")
    print(f"alignment_status: {bundle.alignment_status}")


if __name__ == "__main__":
    main()
