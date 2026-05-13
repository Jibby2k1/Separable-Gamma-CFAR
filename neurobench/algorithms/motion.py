"""Small CPU-safe motion/drift estimation helpers."""
from __future__ import annotations

from typing import Any

from neurobench.pipelines.devices import resolve_device


def _load_numpy():
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        raise RuntimeError("NumPy is required for motion estimation.") from exc
    return np


def shift_frame_integer(frame, dy: int, dx: int):
    """Shift a 2D frame by integer pixels with edge-free zero fill."""
    np = _load_numpy()
    source = np.asarray(frame)
    if source.ndim != 2:
        raise ValueError(f"Expected a 2D frame, got shape {source.shape}.")
    shifted = np.zeros_like(source)
    height, width = source.shape
    src_y0 = max(0, -dy)
    src_y1 = min(height, height - dy)
    src_x0 = max(0, -dx)
    src_x1 = min(width, width - dx)
    dst_y0 = max(0, dy)
    dst_y1 = min(height, height + dy)
    dst_x0 = max(0, dx)
    dst_x1 = min(width, width + dx)
    if src_y0 < src_y1 and src_x0 < src_x1:
        shifted[dst_y0:dst_y1, dst_x0:dst_x1] = source[src_y0:src_y1, src_x0:src_x1]
    return shifted


def estimate_integer_shift(reference, frame, *, max_shift_px: int = 4) -> dict[str, Any]:
    """Estimate the integer correction shift that best aligns a frame to a reference."""
    np = _load_numpy()
    reference_array = np.asarray(reference, dtype=np.float32)
    frame_array = np.asarray(frame, dtype=np.float32)
    if reference_array.shape != frame_array.shape or reference_array.ndim != 2:
        raise ValueError("reference and frame must be 2D arrays with the same shape.")
    max_shift_px = int(max_shift_px)
    if max_shift_px < 0:
        raise ValueError("max_shift_px must be non-negative.")

    best = {"dy": 0, "dx": 0, "score": float("-inf")}
    ref_centered = reference_array - float(np.mean(reference_array))
    for dy in range(-max_shift_px, max_shift_px + 1):
        for dx in range(-max_shift_px, max_shift_px + 1):
            shifted = shift_frame_integer(frame_array, dy, dx)
            shifted_centered = shifted - float(np.mean(shifted))
            score = float(np.sum(ref_centered * shifted_centered))
            if score > best["score"]:
                best = {"dy": int(dy), "dx": int(dx), "score": score}
    return best


def estimate_rigid_shifts(video, *, max_shift_px: int = 4, reference: str = "first", device: str = "cpu") -> dict[str, Any]:
    """Estimate and correct frame-wise integer rigid shifts for a 3D video."""
    device_spec = resolve_device(device)
    np = _load_numpy()
    array = np.asarray(video, dtype=np.float32)
    if array.ndim != 3:
        raise ValueError(f"Motion estimation expects a frame-first 3D video, got shape {array.shape}.")
    if array.shape[0] == 0:
        raise ValueError("Motion estimation requires at least one frame.")
    max_shift_px = int(max_shift_px)
    if max_shift_px < 0:
        raise ValueError("max_shift_px must be non-negative.")

    if reference == "first":
        reference_frame = array[0]
    elif reference == "mean":
        reference_frame = np.mean(array, axis=0)
    elif reference == "median":
        reference_frame = np.median(array, axis=0)
    else:
        raise ValueError("reference must be one of: first, mean, median.")

    registered = np.empty_like(array, dtype=np.float32)
    shifts: list[dict[str, Any]] = []
    for frame_index, frame in enumerate(array):
        shift = estimate_integer_shift(reference_frame, frame, max_shift_px=max_shift_px)
        registered[frame_index] = shift_frame_integer(frame, shift["dy"], shift["dx"])
        shifts.append(
            {
                "frame": int(frame_index),
                "dy": int(shift["dy"]),
                "dx": int(shift["dx"]),
                "score": float(shift["score"]),
            }
        )

    magnitudes = [abs(item["dy"]) + abs(item["dx"]) for item in shifts]
    return {
        "registered_video": registered,
        "shifts": shifts,
        "summary": {
            "frames": int(array.shape[0]),
            "max_shift_px": max_shift_px,
            "reference": reference,
            "max_abs_l1_shift_px": int(max(magnitudes) if magnitudes else 0),
            "mean_abs_l1_shift_px": float(np.mean(magnitudes) if magnitudes else 0.0),
            "device": device_spec.as_dict(),
        },
    }
