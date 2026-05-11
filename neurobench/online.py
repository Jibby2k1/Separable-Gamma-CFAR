"""Small online-processing primitives for 100 Hz feasibility checks."""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from time import perf_counter
from typing import Any, Mapping, Protocol

import numpy as np


class OnlineStage(Protocol):
    """Minimal streaming stage contract for future closed-loop candidates."""

    def initialize(self, first_frame: np.ndarray | None = None) -> None:
        ...

    def process_frame(self, frame: np.ndarray, frame_index: int, timestamp_sec: float | None = None) -> Mapping[str, Any]:
        ...

    def finalize(self) -> Mapping[str, Any]:
        ...

    def latency_summary(self) -> Mapping[str, float | int | None]:
        ...


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    arr = sorted(values)
    idx = min(len(arr) - 1, max(0, round((len(arr) - 1) * q)))
    return float(arr[idx])


@dataclass
class LatencyTracker:
    samples_ms: list[float]

    def __init__(self) -> None:
        self.samples_ms = []

    def add(self, elapsed_ms: float) -> None:
        self.samples_ms.append(float(elapsed_ms))

    def summary(self) -> dict[str, float | int | None]:
        if not self.samples_ms:
            return {"frames": 0, "p50_ms": None, "p95_ms": None, "p99_ms": None, "max_ms": None}
        return {
            "frames": len(self.samples_ms),
            "p50_ms": float(median(self.samples_ms)),
            "p95_ms": _percentile(self.samples_ms, 0.95),
            "p99_ms": _percentile(self.samples_ms, 0.99),
            "max_ms": max(self.samples_ms),
        }


class AdaptiveEwmaZStage:
    """Streaming per-pixel EWMA baseline/variance detector.

    This is intentionally simple: it is a benchmarkable online baseline, not a
    replacement for reviewed annotations or a final neuron detector.
    """

    def __init__(self, *, alpha: float = 0.02, threshold_z: float = 3.0, epsilon: float = 1.0) -> None:
        if not 0 < alpha <= 1:
            raise ValueError("alpha must be in (0, 1].")
        if threshold_z < 0:
            raise ValueError("threshold_z must be non-negative.")
        if epsilon < 0:
            raise ValueError("epsilon must be non-negative.")
        self.alpha = float(alpha)
        self.threshold_z = float(threshold_z)
        self.epsilon = float(epsilon)
        self.mean: np.ndarray | None = None
        self.var: np.ndarray | None = None
        self.latency = LatencyTracker()

    def initialize(self, first_frame: np.ndarray | None = None) -> None:
        if first_frame is None:
            self.mean = None
            self.var = None
            return
        frame = np.asarray(first_frame, dtype=np.float32)
        self.mean = frame.copy()
        self.var = np.ones_like(frame, dtype=np.float32)

    def process_frame(self, frame: np.ndarray, frame_index: int, timestamp_sec: float | None = None) -> dict[str, Any]:
        start = perf_counter()
        frame_f = np.asarray(frame, dtype=np.float32)
        if self.mean is None or self.var is None:
            self.initialize(frame_f)
        assert self.mean is not None and self.var is not None
        residual = frame_f - self.mean
        std = np.sqrt(np.maximum(self.var, 0.0)) + self.epsilon
        z = residual / std
        mask = z > self.threshold_z
        self.mean = (1.0 - self.alpha) * self.mean + self.alpha * frame_f
        self.var = (1.0 - self.alpha) * self.var + self.alpha * np.square(residual)
        self.latency.add((perf_counter() - start) * 1000.0)
        return {
            "frame_index": frame_index,
            "timestamp_sec": timestamp_sec,
            "z": z,
            "mask": mask,
            "candidate_pixel_count": int(mask.sum()),
        }

    def finalize(self) -> dict[str, Any]:
        return {"latency": self.latency_summary()}

    def latency_summary(self) -> dict[str, float | int | None]:
        return self.latency.summary()


def synthetic_event_video(
    *,
    frames: int = 64,
    height: int = 64,
    width: int = 64,
    event_frame: int = 20,
    event_y: int = 32,
    event_x: int = 32,
    event_amplitude: float = 8.0,
    noise_sigma: float = 1.0,
    seed: int = 0,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    video = rng.normal(0.0, noise_sigma, size=(frames, height, width)).astype(np.float32)
    if 0 <= event_frame < frames:
        yy, xx = np.ogrid[:height, :width]
        footprint = np.exp(-((yy - event_y) ** 2 + (xx - event_x) ** 2) / (2 * 2.0**2))
        video[event_frame] += event_amplitude * footprint.astype(np.float32)
    return video

