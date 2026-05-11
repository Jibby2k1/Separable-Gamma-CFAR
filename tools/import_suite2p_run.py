#!/usr/bin/env python3
"""Create a Neurobench architecture-run manifest from Suite2p output files."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from neurobench.integrations.suite2p_import import build_suite2p_run
from neurobench.manifests import write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Suite2p output as a Neurobench architecture run.")
    parser.add_argument("--suite2p-dir", type=Path, required=True, help="Directory containing stat.npy, F.npy, etc.")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dataset-id", default="calcium_video_2")
    parser.add_argument("--run-id", default="suite2p_import")
    parser.add_argument("--label", default="Suite2p import")
    args = parser.parse_args()

    run = build_suite2p_run(args.suite2p_dir, args.dataset_id, args.run_id, args.label)
    write_json(args.out, {"schema_version": 1, "dataset_id": args.dataset_id, "runs": [run]})
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
