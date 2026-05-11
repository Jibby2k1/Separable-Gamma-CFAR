#!/usr/bin/env python3
"""Run the Fiji/Groovy neuron-review pipeline from a dataset manifest."""
from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from neurobench.manifests import load_dataset_manifest, manifest_path


DEFAULT_FIJI = Path("/home/jibby2k1/.local/bin/fiji")
DEFAULT_STAGES = [
    "high-pass",
    "event-denoise",
    "candidates",
    "temporal-scoring",
    "review-data",
    "workbench",
    "index",
]
STAGE_ALIASES = {
    "all": DEFAULT_STAGES,
    "highpass": ["high-pass"],
    "denoise": ["event-denoise"],
    "event-preserving-denoise": ["event-denoise"],
    "candidate-event-pipeline": ["candidates"],
    "temporal": ["temporal-scoring"],
    "review": ["review-data"],
    "build": ["workbench"],
}


def quote_cmd(command: Iterable[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in command)


def split_stages(value: str) -> list[str]:
    requested: list[str] = []
    for raw in value.split(","):
        stage = raw.strip()
        if not stage:
            continue
        requested.extend(STAGE_ALIASES.get(stage, [stage]))
    unknown = [stage for stage in requested if stage not in DEFAULT_STAGES]
    if unknown:
        raise SystemExit(f"Unknown stage(s): {', '.join(unknown)}")
    return requested


def require_outputs(paths: list[Path], *, stage: str, started_at: float) -> None:
    missing = [path for path in paths if not path.exists()]
    if missing:
        joined = "\n  ".join(str(path) for path in missing)
        raise SystemExit(f"{stage} did not produce expected output(s):\n  {joined}")
    if paths and not any(path.stat().st_mtime >= started_at - 2.0 for path in paths):
        joined = "\n  ".join(str(path) for path in paths)
        raise SystemExit(f"{stage} outputs were not refreshed; Fiji may have reported an internal script error:\n  {joined}")


def run(command: list[str], *, env: dict[str, str], dry_run: bool, expected: list[Path] | None = None, stage: str) -> None:
    print("+ " + quote_cmd(command), flush=True)
    if dry_run:
        return
    started_at = time.time()
    subprocess.run(command, cwd=PROJECT_ROOT, env=env, check=True)
    if expected is not None:
        require_outputs(expected, stage=stage, started_at=started_at)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Neurobench Fiji/Groovy review pipeline.")
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--fiji", type=Path, default=DEFAULT_FIJI)
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "Outputs")
    parser.add_argument("--stages", default="all", help="Comma-separated stage list, or all.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    manifest = load_dataset_manifest(args.dataset_manifest)
    dataset_id = str(manifest["dataset_id"])
    raw_video = manifest_path(manifest, "raw_video")
    app_dir = manifest_path(manifest, "app_dir") or (args.output_root / "NeuronReview" / dataset_id / "app")
    review_data = manifest_path(manifest, "review_data") or (app_dir / "review_data.json")
    architecture_runs = manifest_path(manifest, "architecture_runs")
    source_z_stack = args.output_root / "CandidateEventPipeline" / dataset_id / f"{dataset_id}_sigma06_robust_positive_z_float32.tif"
    high_pass_dir = args.output_root / "HighPass" / dataset_id
    candidate_dir = args.output_root / "CandidateEventPipeline" / dataset_id
    temporal_dir = args.output_root / "TemporalCandidateScoring" / dataset_id

    if raw_video is None:
        raise SystemExit("Manifest is missing paths.raw_video")
    if not raw_video.exists():
        raise SystemExit(f"Raw video not found: {raw_video}")
    if not args.dry_run and not args.fiji.exists():
        raise SystemExit(f"Fiji executable not found: {args.fiji}")

    env = os.environ.copy()
    env.update(
        {
            "NEUROBENCH_PROJECT_ROOT": str(PROJECT_ROOT),
            "NEUROBENCH_DATASET_ID": dataset_id,
            "NEUROBENCH_RAW_VIDEO": str(raw_video),
            "NEUROBENCH_OUTPUT_ROOT": str(args.output_root.resolve()),
            "NEUROBENCH_APP_DIR": str(app_dir),
            "NEUROBENCH_SOURCE_Z_STACK": str(source_z_stack),
        }
    )

    macro_args = ",".join(
        [
            f"dataset_id={dataset_id}",
            f"input_path={raw_video}",
            f"output_root={args.output_root.resolve()}",
        ]
    )
    commands = {
        "high-pass": [
            str(args.fiji),
            "--headless",
            "--console",
            "-macro",
            str(PROJECT_ROOT / "tools/temporal_highpass_gaussian.ijm"),
            macro_args,
        ],
        "event-denoise": [
            str(args.fiji),
            "--headless",
            "--run",
            str(PROJECT_ROOT / "tools/event_preserving_noise_suppression.groovy"),
        ],
        "candidates": [
            str(args.fiji),
            "--headless",
            "--run",
            str(PROJECT_ROOT / "tools/candidate_event_pipeline.groovy"),
        ],
        "temporal-scoring": [
            str(args.fiji),
            "--headless",
            "--run",
            str(PROJECT_ROOT / "tools/temporal_candidate_scoring.groovy"),
        ],
        "review-data": [
            str(args.fiji),
            "--headless",
            "--run",
            str(PROJECT_ROOT / "tools/generate_neuron_review_app.groovy"),
        ],
        "workbench": [
            sys.executable,
            str(PROJECT_ROOT / "tools/build_neuron_workbench_v2.py"),
            "--dataset-manifest",
            str(args.dataset_manifest),
            "--app-dir",
            str(app_dir),
            "--review-data",
            str(review_data),
        ],
        "index": [
            sys.executable,
            str(PROJECT_ROOT / "tools/build_workbench_index.py"),
            "--root",
            str(args.output_root / "NeuronReview"),
            "--out",
            str(args.output_root / "NeuronReview/index.html"),
        ],
    }
    if architecture_runs is not None:
        commands["workbench"].extend(["--architecture-runs", str(architecture_runs)])

    expected_outputs = {
        "high-pass": [
            high_pass_dir / f"{dataset_id}_hp_gaussian_sigma04f_float32.tif",
            high_pass_dir / f"{dataset_id}_hp_gaussian_sigma06f_float32.tif",
            high_pass_dir / f"{dataset_id}_hp_gaussian_sigma08f_float32.tif",
        ],
        "event-denoise": [
            args.output_root / "EventPreservingNoiseSuppression" / dataset_id / f"{dataset_id}_sigma06_positive_local_z_float32.tif",
        ],
        "candidates": [
            source_z_stack,
            candidate_dir / "candidate_events.tsv",
        ],
        "temporal-scoring": [
            temporal_dir / f"{dataset_id}_sigma06_balanced_seed017_grow009_min3_score_ge_050_mask.tif",
            temporal_dir / "temporal_candidates.tsv",
        ],
        "review-data": [
            review_data,
            app_dir / "roi_summary.tsv",
            app_dir / "frames" / "frame_001.png",
        ],
        "workbench": [
            app_dir / "index.html",
            app_dir / "workbench.js",
            app_dir / "annotations.json",
        ],
        "index": [
            args.output_root / "NeuronReview/index.html",
        ],
    }

    stages = split_stages(args.stages)
    print(f"Dataset: {dataset_id}", flush=True)
    print(f"Raw video: {raw_video}", flush=True)
    print(f"App dir: {app_dir}", flush=True)
    for stage in stages:
        run(
            commands[stage],
            env=env,
            dry_run=args.dry_run,
            expected=expected_outputs.get(stage),
            stage=stage,
        )


if __name__ == "__main__":
    main()
