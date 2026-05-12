#!/usr/bin/env python3
"""Build a grouped planned parameter-sweep pack for Architecture Lab."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from neurobench.manifests import load_dataset_manifest, write_json
from neurobench.sweep_packs import build_sweep_pack


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a planned review sweep-pack manifest.")
    parser.add_argument("--dataset-id", default=None)
    parser.add_argument("--dataset-manifest", type=Path, default=None)
    parser.add_argument("--pack-id", default="review_pack_v1")
    parser.add_argument("--label", default="Review parameter pack v1")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    manifest = load_dataset_manifest(args.dataset_manifest) if args.dataset_manifest else {}
    dataset_id = args.dataset_id or manifest.get("dataset_id")
    if not dataset_id:
        raise SystemExit("--dataset-id is required when --dataset-manifest is not provided.")
    pack = build_sweep_pack(
        dataset_id=dataset_id,
        pack_id=args.pack_id,
        label=args.label,
        source_manifest=str(args.dataset_manifest) if args.dataset_manifest else None,
    )
    write_json(args.out, pack)
    print(f"Wrote {args.out} with {len(pack['runs'])} planned review-pack runs")


if __name__ == "__main__":
    main()
