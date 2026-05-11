#!/usr/bin/env python3
"""Create a dataset manifest for a calcium-imaging workbench run."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from neurobench.manifests import default_calcium_video_2_manifest, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a Neurobench dataset manifest.")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dataset-id", default="calcium_video_2")
    parser.add_argument("--name", default=None)
    parser.add_argument("--raw-video", default="Inputs/050126/050126/calcium video 2.tif")
    parser.add_argument("--app-dir", default="Outputs/NeuronReview/calcium_video_2/app")
    parser.add_argument("--architecture-runs", default=None)
    parser.add_argument("--frame-rate-hz", type=float, default=5.0)
    parser.add_argument("--pixel-size-microns", type=float, default=0.5)
    args = parser.parse_args()

    manifest = default_calcium_video_2_manifest()
    manifest["dataset_id"] = args.dataset_id
    manifest["name"] = args.name or Path(args.raw_video).name
    manifest["frame_rate_hz"] = args.frame_rate_hz
    manifest["pixel_size_microns"] = args.pixel_size_microns
    manifest["paths"]["raw_video"] = args.raw_video
    manifest["paths"]["app_dir"] = args.app_dir
    manifest["paths"]["review_data"] = str(Path(args.app_dir) / "review_data.json")
    manifest["paths"]["annotations"] = str(Path(args.app_dir) / "annotations.json")
    manifest["paths"]["architecture_runs"] = args.architecture_runs or str(
        Path("Outputs/ArchitectureRuns") / args.dataset_id / "architecture_runs.json"
    )
    write_json(args.out, manifest)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
