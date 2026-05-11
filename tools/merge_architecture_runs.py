#!/usr/bin/env python3
"""Merge multiple Neurobench architecture-run manifests into one file."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from neurobench.architecture_runs import merge_run_manifests
from neurobench.manifests import load_json, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge Neurobench architecture-run manifests.")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--replace", action="store_true", help="Replace duplicate run_id entries instead of failing.")
    parser.add_argument("manifests", nargs="+", type=Path)
    args = parser.parse_args()

    merged = merge_run_manifests([load_json(path) for path in args.manifests], replace=args.replace)
    write_json(args.out, merged)
    print(f"Wrote {args.out} with {len(merged['runs'])} runs")


if __name__ == "__main__":
    main()
