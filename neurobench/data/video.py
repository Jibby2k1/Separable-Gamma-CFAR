"""Memory-aware frame-first video access helpers."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


@dataclass(frozen=True)
class VideoChunk:
    """One contiguous frame chunk from a frame-first video."""

    start_frame: int
    end_frame: int
    data: Any

    @property
    def frame_count(self) -> int:
        return int(self.end_frame - self.start_frame)


class VideoStore:
    """Small abstraction for frame-first videos backed by arrays or files.

    The first implementation intentionally supports in-memory arrays and NumPy
    ``.npy`` files. ``.npy`` paths are opened with ``mmap_mode='r'`` by default
    so callers can iterate frame chunks without reading the whole movie eagerly.
    """

    def __init__(
        self,
        array: Any,
        *,
        source_path: str | Path = "",
        storage_mode: str = "array",
    ) -> None:
        np = _load_numpy()
        self._array = array
        self.source_path = str(source_path)
        self.storage_mode = str(storage_mode)
        self.shape = tuple(int(value) for value in array.shape)
        if len(self.shape) < 3:
            raise ValueError(f"Expected a frame-first video with at least 3 dimensions, got shape {self.shape}.")
        self.dtype = np.dtype(array.dtype)

    @classmethod
    def from_array(cls, array: Any, *, source_path: str | Path = "") -> "VideoStore":
        """Create a store from an existing frame-first array-like object."""
        np = _load_numpy()
        return cls(np.asarray(array), source_path=source_path, storage_mode="array")

    @classmethod
    def from_path(cls, path: str | Path, *, mmap: bool = True) -> "VideoStore":
        """Open a supported video path.

        NumPy ``.npy`` files are memory-mapped by default. TIFF files are loaded
        through ``tifffile`` when available; they are marked as eager arrays
        because memory mapping is not guaranteed across TIFF encodings.
        """
        source = Path(path).expanduser()
        if not source.exists():
            raise FileNotFoundError(f"Video path does not exist: {source}")
        suffix = source.suffix.lower()
        if suffix == ".npy":
            np = _load_numpy()
            array = np.load(source, mmap_mode="r" if mmap else None)
            return cls(array, source_path=source, storage_mode="npy_memmap" if mmap else "npy_array")
        if suffix in {".tif", ".tiff"}:
            try:
                import tifffile  # type: ignore
            except ModuleNotFoundError as exc:
                raise RuntimeError("TIFF video access requires tifffile. Use .npy or install tifffile.") from exc
            return cls(tifffile.imread(source), source_path=source, storage_mode="tiff_array")
        raise ValueError(f"Unsupported video format: {source.suffix}")

    @property
    def frame_count(self) -> int:
        return int(self.shape[0])

    @property
    def height(self) -> int:
        return int(self.shape[-2])

    @property
    def width(self) -> int:
        return int(self.shape[-1])

    @property
    def nbytes(self) -> int:
        return int(getattr(self._array, "nbytes", 0))

    def metadata(self) -> dict[str, Any]:
        """Return stable video metadata for manifests, QC, and reports."""
        return {
            "shape": [int(value) for value in self.shape],
            "frames": self.frame_count,
            "height": self.height,
            "width": self.width,
            "dtype": str(self.dtype),
            "nbytes": self.nbytes,
            "source_path": self.source_path,
            "storage_mode": self.storage_mode,
        }

    def frame(self, index: int) -> Any:
        """Return one frame by zero-based index."""
        if index < 0 or index >= self.frame_count:
            raise IndexError(f"Frame index {index} is outside [0, {self.frame_count}).")
        return self._array[index]

    def iter_chunks(self, chunk_size: int) -> Iterator[VideoChunk]:
        """Yield contiguous frame chunks with half-open frame bounds."""
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive.")
        for start in range(0, self.frame_count, int(chunk_size)):
            end = min(self.frame_count, start + int(chunk_size))
            yield VideoChunk(start_frame=start, end_frame=end, data=self._array[start:end])

    def as_array(self) -> Any:
        """Return the underlying array-like object."""
        return self._array

    def __array__(self, dtype: Any | None = None) -> Any:
        np = _load_numpy()
        return np.asarray(self._array, dtype=dtype)


def open_video(path: str | Path, *, mmap: bool = True) -> VideoStore:
    """Open a supported video path as a ``VideoStore``."""
    return VideoStore.from_path(path, mmap=mmap)


def as_video_store(video: Any) -> VideoStore:
    """Return ``video`` as a ``VideoStore`` without copying when possible."""
    if isinstance(video, VideoStore):
        return video
    return VideoStore.from_array(video)


def _load_numpy():
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        raise RuntimeError("NumPy is required for video access.") from exc
    return np
