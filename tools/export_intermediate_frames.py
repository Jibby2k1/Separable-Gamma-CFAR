#!/usr/bin/env python3
"""Export a TIFF stack as browser-readable PNG frames and attach it to a run."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from PIL import Image, ImageOps, ImageSequence


def normalize_frame(frame: Image.Image) -> Image.Image:
    gray = frame.convert("F")
    lo, hi = gray.getextrema()
    if hi <= lo:
        return Image.new("L", gray.size)
    scaled = gray.point(lambda value: max(0, min(255, int((value - lo) * 255.0 / (hi - lo)))))
    return ImageOps.autocontrast(scaled.convert("L"))


def relative_pattern(out_dir: Path, pattern: str, manifest_path: Path | None) -> str:
    pattern_path = out_dir / pattern
    if manifest_path is None:
        return pattern_path.as_posix()
    try:
        return pattern_path.resolve().relative_to(manifest_path.parent.resolve()).as_posix()
    except ValueError:
        return pattern_path.resolve().as_posix()


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_manifest(path: Path, data: dict) -> None:
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def attach_artifact(manifest: dict, run_id: str, artifact: dict) -> dict:
    for run in manifest.get("runs", []):
        if run.get("run_id") != run_id:
            continue
        artifacts = run.setdefault("artifacts", {})
        items = list(artifacts.get("intermediates") or [])
        artifact_id = artifact.get("id")
        items = [item for item in items if item.get("id") != artifact_id]
        items.append(artifact)
        artifacts["intermediates"] = items
        return manifest
    raise SystemExit(f"run_id not found in manifest: {run_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export TIFF-stack intermediate frames for Dataset QC.")
    parser.add_argument("--input-tif", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--stage-id", required=True)
    parser.add_argument("--step-id", default=None)
    parser.add_argument("--label", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--architecture-runs", type=Path, default=None)
    parser.add_argument("--frame-pattern", default="frame_%03d.png")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    with Image.open(args.input_tif) as imp:
        for index, frame in enumerate(ImageSequence.Iterator(imp), start=1):
            out = args.out_dir / (args.frame_pattern.replace("%03d", f"{index:03d}"))
            normalize_frame(frame).save(out)
            count = index

    artifact = {
        "id": args.step_id or args.stage_id,
        "label": args.label or args.stage_id.replace("_", " "),
        "stage_id": args.stage_id,
        "step_id": args.step_id or args.stage_id,
        "media_type": "frame_sequence",
        "frame_count": count,
        "frame_pattern": relative_pattern(args.out_dir, args.frame_pattern, args.architecture_runs),
        "source": str(args.input_tif),
    }

    if args.architecture_runs and args.run_id:
        manifest = attach_artifact(load_manifest(args.architecture_runs), args.run_id, artifact)
        write_manifest(args.architecture_runs, manifest)

    print(json.dumps(artifact, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
