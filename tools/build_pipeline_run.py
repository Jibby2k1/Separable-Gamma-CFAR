#!/usr/bin/env python3
"""Build a deterministic planned architecture-run manifest from a pipeline spec."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from neurobench.architecture_runs import build_planned_manifest
from neurobench.manifests import load_json, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a planned architecture-run manifest from a pipeline spec.")
    parser.add_argument("--spec", type=Path, required=True, help="Structured pipeline spec JSON.")
    parser.add_argument("--out", type=Path, required=True, help="Output architecture-run manifest JSON.")
    parser.add_argument("--run-id", default=None, help="Override the run_id in the spec.")
    parser.add_argument("--label", default=None, help="Override the label in the spec.")
    args = parser.parse_args()

    spec = load_json(args.spec)
    if args.run_id is not None:
        spec["run_id"] = args.run_id
    if args.label is not None:
        spec["label"] = args.label

    manifest = build_planned_manifest(spec)
    write_json(args.out, manifest)
    run_count = len(manifest["runs"])
    if run_count == 1:
        print(f"Wrote {args.out} with planned run {manifest['runs'][0]['run_id']}")
    else:
        print(f"Wrote {args.out} with {run_count} planned runs")


if __name__ == "__main__":
    main()
