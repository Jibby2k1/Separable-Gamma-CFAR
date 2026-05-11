#!/usr/bin/env python3
"""Create a Neurobench architecture-run manifest from OASIS trace outputs."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from neurobench.integrations.oasis_import import build_oasis_run
from neurobench.manifests import write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Import OASIS deconvolved traces as a Neurobench architecture run.")
    parser.add_argument("--traces", type=Path, required=True, help="OASIS .npy or .npz trace output.")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dataset-id", default="calcium_video_2")
    parser.add_argument("--run-id", default="oasis_import")
    parser.add_argument("--label", default="OASIS deconvolution")
    parser.add_argument("--key", help="Array key for .npz files. Defaults to common keys, then the first array.")
    parser.add_argument("--source-traces", type=Path, help="Optional source fluorescence trace artifact.")
    args = parser.parse_args()

    run = build_oasis_run(
        traces_path=args.traces,
        dataset_id=args.dataset_id,
        run_id=args.run_id,
        label=args.label,
        key=args.key,
        source_traces=args.source_traces,
    )
    write_json(args.out, {"schema_version": 1, "dataset_id": args.dataset_id, "runs": [run]})
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
