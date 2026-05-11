#!/usr/bin/env python3
"""Create a Neurobench architecture-run manifest from a PMD-denoised video."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from neurobench.integrations.pmd_import import build_pmd_run
from neurobench.manifests import write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Import PMD-denoised video metadata as a Neurobench architecture run.")
    parser.add_argument("--denoised-video", type=Path, required=True, help="PMD-denoised TIFF or movie artifact.")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dataset-id", default="calcium_video_2")
    parser.add_argument("--run-id", default="pmd_denoised")
    parser.add_argument("--label", default="PMD denoised video")
    parser.add_argument("--source-video", type=Path, help="Raw/source video used for PMD denoising.")
    parser.add_argument("--frame-count", type=int, help="Optional frame count for dashboard comparison.")
    parser.add_argument("--width", type=int, help="Optional frame width in pixels.")
    parser.add_argument("--height", type=int, help="Optional frame height in pixels.")
    parser.add_argument("--notes", help="Optional notes about PMD parameters or preprocessing.")
    args = parser.parse_args()

    run = build_pmd_run(
        denoised_video=args.denoised_video,
        dataset_id=args.dataset_id,
        run_id=args.run_id,
        label=args.label,
        source_video=args.source_video,
        frame_count=args.frame_count,
        width=args.width,
        height=args.height,
        notes=args.notes,
    )
    write_json(args.out, {"schema_version": 1, "dataset_id": args.dataset_id, "runs": [run]})
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
