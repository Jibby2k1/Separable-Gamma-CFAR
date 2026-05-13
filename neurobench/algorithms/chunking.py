"""Chunked processing helpers for frame-first videos."""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from neurobench.data.video import as_video_store


def process_independent_frame_chunks(
    video: Any,
    processor: Callable[[Any], Mapping[str, Any]],
    *,
    chunk_size: int,
    concatenate_keys: Sequence[str],
) -> dict[str, Any]:
    """Apply a frame-independent processor to chunks and concatenate outputs.

    This helper is intentionally conservative. It is only for algorithms whose
    result for a frame does not depend on neighboring frames. Temporal filters
    should use an overlap/state-aware helper instead of this function.
    """
    np = _load_numpy()
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive.")
    keys = tuple(str(key) for key in concatenate_keys)
    if not keys:
        raise ValueError("concatenate_keys must include at least one output key.")

    store = as_video_store(video)
    pieces: dict[str, list[Any]] = {key: [] for key in keys}
    chunk_ranges: list[dict[str, int]] = []
    for chunk in store.iter_chunks(chunk_size):
        result = processor(chunk.data)
        if not isinstance(result, Mapping):
            raise TypeError("processor must return a mapping.")
        for key in keys:
            if key not in result:
                raise KeyError(f"Chunk processor result is missing key '{key}'.")
            value = np.asarray(result[key])
            if value.ndim == 0 or int(value.shape[0]) != chunk.frame_count:
                raise ValueError(
                    f"Chunk output '{key}' must have first dimension {chunk.frame_count}, got shape {value.shape}."
                )
            pieces[key].append(value)
        chunk_ranges.append({"start_frame": int(chunk.start_frame), "end_frame": int(chunk.end_frame)})

    output = {key: np.concatenate(values, axis=0) if values else np.empty((0,)) for key, values in pieces.items()}
    output["chunk_ranges"] = chunk_ranges
    return output


def _load_numpy():
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        raise RuntimeError("NumPy is required for chunked processing.") from exc
    return np
