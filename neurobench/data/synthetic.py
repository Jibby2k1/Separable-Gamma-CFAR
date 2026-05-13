"""Tiny synthetic calcium-imaging fixtures for tests."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class SyntheticEvent:
    """Known synthetic event location and timing."""

    event_id: int
    x: float
    y: float
    start_frame: int
    end_frame: int
    amplitude: float = 5.0


@dataclass
class SyntheticDataset:
    """Small generated video plus ground-truth metadata."""

    video: np.ndarray
    gt_data: dict[int, list[tuple[float, float, int]]]
    events: list[SyntheticEvent]
    artifact_locations: list[dict[str, Any]] = field(default_factory=list)

    @property
    def shape(self) -> tuple[int, int, int]:
        return tuple(int(v) for v in self.video.shape)

    def write(self, out_dir: str | Path, *, dataset_id: str = "synthetic_neurobench") -> dict[str, str]:
        """Write a tiny fixture bundle using portable text/NumPy files."""
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        video_path = out / "video.npy"
        gt_path = out / "ground_truth.csv"
        manifest_path = out / "dataset_manifest.json"

        np.save(video_path, self.video)
        with gt_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["ID", "Start Frame", "End Frame", "X", "Y"])
            writer.writeheader()
            for event in self.events:
                writer.writerow(
                    {
                        "ID": event.event_id,
                        "Start Frame": event.start_frame,
                        "End Frame": event.end_frame,
                        "X": event.x,
                        "Y": event.y,
                    }
                )
        manifest = {
            "schema_version": 1,
            "dataset_id": dataset_id,
            "name": "Synthetic Neurobench fixture",
            "modality": "synthetic_calcium",
            "frame_rate_hz": 10.0,
            "pixel_size_microns": 1.0,
            "paths": {
                "raw_video": str(video_path),
                "app_dir": str(out / "app"),
                "review_data": str(out / "app" / "review_data.json"),
                "ground_truth": str(gt_path),
            },
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {"video": str(video_path), "ground_truth": str(gt_path), "manifest": str(manifest_path)}


def _default_events() -> list[SyntheticEvent]:
    return [
        SyntheticEvent(event_id=1, x=10.0, y=9.0, start_frame=5, end_frame=8, amplitude=6.0),
        SyntheticEvent(event_id=2, x=22.0, y=20.0, start_frame=13, end_frame=16, amplitude=5.0),
    ]


def _event_trace(frames: int, start: int, end: int, amplitude: float) -> np.ndarray:
    trace = np.zeros(frames, dtype=np.float32)
    duration = max(1, end - start + 1)
    for frame in range(start, min(frames, end + 1)):
        dt = frame - start
        rise = min(1.0, (dt + 1) / max(1, duration // 2))
        decay = np.exp(-max(0, dt - 1) / max(1.0, duration / 2.0))
        trace[frame] = amplitude * rise * decay
    return trace


def generate_synthetic_calcium_dataset(
    *,
    frames: int = 24,
    height: int = 32,
    width: int = 32,
    events: list[SyntheticEvent] | None = None,
    noise_sigma: float = 0.03,
    background_gradient: bool = True,
    include_impulse_artifact: bool = True,
    include_drift: bool = False,
    seed: int = 7,
) -> SyntheticDataset:
    """Generate a tiny deterministic video with known neuron events."""
    if frames <= 0 or height <= 0 or width <= 0:
        raise ValueError("frames, height, and width must be positive.")
    rng = np.random.default_rng(seed)
    y_grid, x_grid = np.mgrid[0:height, 0:width]
    video = rng.normal(0.0, noise_sigma, size=(frames, height, width)).astype(np.float32)
    if background_gradient:
        gradient = (x_grid / max(1, width - 1) * 0.15 + y_grid / max(1, height - 1) * 0.10).astype(np.float32)
        video += gradient[None, :, :]

    event_list = events or _default_events()
    gt_data: dict[int, list[tuple[float, float, int]]] = {}
    for event in event_list:
        trace = _event_trace(frames, event.start_frame, event.end_frame, event.amplitude)
        for frame in range(max(0, event.start_frame), min(frames, event.end_frame + 1)):
            drift_x = 1.0 if include_drift and frame >= frames // 2 else 0.0
            cx = event.x + drift_x
            cy = event.y
            footprint = np.exp(-(((x_grid - cx) ** 2) + ((y_grid - cy) ** 2)) / (2 * 1.3**2)).astype(np.float32)
            video[frame] += trace[frame] * footprint
            gt_data.setdefault(frame, []).append((float(cx), float(cy), int(event.event_id)))

    artifact_locations: list[dict[str, Any]] = []
    if include_impulse_artifact:
        artifact = {"frame": min(frames - 1, 18), "x": min(width - 3, 27), "y": min(height - 3, 5), "kind": "impulse"}
        video[artifact["frame"], artifact["y"], artifact["x"]] += 12.0
        artifact_locations.append(artifact)

    return SyntheticDataset(
        video=video.astype(np.float32, copy=False),
        gt_data=gt_data,
        events=event_list,
        artifact_locations=artifact_locations,
    )
