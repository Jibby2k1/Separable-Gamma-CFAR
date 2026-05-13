"""Realtime frame-source primitives for online pipeline experiments."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Mapping, Protocol

from neurobench.data.video import VideoStore, as_video_store, open_video


@dataclass(frozen=True)
class FramePacket:
    """One frame plus timing/provenance metadata."""

    frame_index: int
    timestamp_sec: float
    frame: Any
    source_id: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self, *, include_frame: bool = False) -> dict[str, Any]:
        payload = {
            "frame_index": int(self.frame_index),
            "timestamp_sec": float(self.timestamp_sec),
            "source_id": self.source_id,
            "metadata": dict(self.metadata),
        }
        if include_frame:
            payload["frame"] = self.frame
        return payload


class FrameSource(Protocol):
    """Minimal iterable frame source contract for realtime experiments."""

    def __iter__(self) -> Iterator[FramePacket]:
        ...

    def metadata(self) -> dict[str, Any]:
        ...


class VideoFrameSource:
    """Frame source backed by a frame-first ``VideoStore``."""

    def __init__(self, video: Any, *, frame_rate_hz: float, source_id: str = "video") -> None:
        if frame_rate_hz <= 0:
            raise ValueError("frame_rate_hz must be positive.")
        self.store = as_video_store(video)
        self.frame_rate_hz = float(frame_rate_hz)
        self.source_id = str(source_id)

    @classmethod
    def from_path(cls, path: str | Path, *, frame_rate_hz: float, source_id: str | None = None, mmap: bool = True) -> "VideoFrameSource":
        source = Path(path)
        return cls(open_video(source, mmap=mmap), frame_rate_hz=frame_rate_hz, source_id=source_id or source.stem)

    def __iter__(self) -> Iterator[FramePacket]:
        for frame_index in range(self.store.frame_count):
            yield FramePacket(
                frame_index=frame_index,
                timestamp_sec=frame_index / self.frame_rate_hz,
                frame=self.store.frame(frame_index),
                source_id=self.source_id,
                metadata={"frame_rate_hz": self.frame_rate_hz},
            )

    def metadata(self) -> dict[str, Any]:
        payload = self.store.metadata()
        payload.update(
            {
                "source_id": self.source_id,
                "frame_rate_hz": self.frame_rate_hz,
                "duration_sec": self.store.frame_count / self.frame_rate_hz,
            }
        )
        return payload


class SyntheticFrameSource(VideoFrameSource):
    """Deterministic synthetic frame stream for tests and latency smoke checks."""

    def __init__(
        self,
        *,
        frames: int = 64,
        height: int = 64,
        width: int = 64,
        frame_rate_hz: float = 100.0,
        event_frame: int = 20,
        event_y: int | None = None,
        event_x: int | None = None,
        event_amplitude: float = 8.0,
        noise_sigma: float = 1.0,
        seed: int = 0,
        source_id: str = "synthetic_stream",
    ) -> None:
        np = _load_numpy()
        if frames <= 0 or height <= 0 or width <= 0:
            raise ValueError("frames, height, and width must be positive.")
        event_y = height // 2 if event_y is None else int(event_y)
        event_x = width // 2 if event_x is None else int(event_x)
        rng = np.random.default_rng(seed)
        video = rng.normal(0.0, noise_sigma, size=(frames, height, width)).astype(np.float32)
        if 0 <= event_frame < frames:
            yy, xx = np.ogrid[:height, :width]
            footprint = np.exp(-((yy - event_y) ** 2 + (xx - event_x) ** 2) / (2 * 2.0**2))
            video[event_frame] += event_amplitude * footprint.astype(np.float32)
        self.event = {
            "frame": int(event_frame),
            "x": int(event_x),
            "y": int(event_y),
            "amplitude": float(event_amplitude),
        }
        super().__init__(VideoStore.from_array(video), frame_rate_hz=frame_rate_hz, source_id=source_id)

    def metadata(self) -> dict[str, Any]:
        payload = super().metadata()
        payload["synthetic_event"] = dict(self.event)
        return payload


def collect_frame_packets(source: FrameSource, *, limit: int | None = None) -> list[FramePacket]:
    """Collect packets from a source for tests, demos, and smoke checks."""
    packets: list[FramePacket] = []
    for packet in source:
        packets.append(packet)
        if limit is not None and len(packets) >= limit:
            break
    return packets


def _load_numpy():
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        raise RuntimeError("NumPy is required for realtime frame sources.") from exc
    return np
