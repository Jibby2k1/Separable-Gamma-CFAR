"""Dataset quality-control summaries."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


def compute_video_qc(video: Any, *, dataset_id: str = "", source_path: str = "") -> dict[str, Any]:
    """Compute lightweight QC metrics for a frame-first video array."""

    np = _load_numpy()
    store = None
    if hasattr(video, "as_array") and hasattr(video, "metadata"):
        store = video
        array = np.asarray(video.as_array())
    else:
        array = np.asarray(video)
    if array.ndim < 3:
        raise ValueError(f"Expected a frame-first video with at least 3 dimensions, got shape {array.shape}.")
    frame_axis = int(array.shape[0])
    finite = np.isfinite(array)
    finite_values = array[finite]
    warnings: list[str] = []
    if frame_axis == 0 or finite_values.size == 0:
        warnings.append("Video has no finite frame data.")
        finite_values = np.array([0.0], dtype=np.float32)
    if not bool(finite.all()):
        warnings.append("Video contains non-finite values.")

    frame_means = np.mean(array.astype(np.float64), axis=tuple(range(1, array.ndim))) if frame_axis else np.array([])
    frame_diffs = np.diff(array.astype(np.float32), axis=0) if frame_axis > 1 else np.array([])
    stats = {
        "min": float(np.min(finite_values)),
        "max": float(np.max(finite_values)),
        "mean": float(np.mean(finite_values)),
        "std": float(np.std(finite_values)),
        "p01": float(np.percentile(finite_values, 1)),
        "p50": float(np.percentile(finite_values, 50)),
        "p99": float(np.percentile(finite_values, 99)),
    }
    saturation = _saturation_summary(array, stats["min"], stats["max"])
    drift = _drift_summary(frame_means)
    temporal = {
        "frame_mean_std": float(np.std(frame_means)) if frame_means.size else 0.0,
        "frame_mean_range": float(np.max(frame_means) - np.min(frame_means)) if frame_means.size else 0.0,
        "median_abs_frame_diff": float(np.median(np.abs(frame_diffs))) if frame_diffs.size else 0.0,
    }
    warnings.extend(_qc_warnings(stats, saturation, drift, array.nbytes))
    video_summary = {
        "shape": [int(value) for value in array.shape],
        "frames": int(array.shape[0]),
        "height": int(array.shape[-2]),
        "width": int(array.shape[-1]),
        "dtype": str(array.dtype),
        "nbytes": int(array.nbytes),
    }
    if store is not None:
        video_summary.update(
            {
                key: value
                for key, value in store.metadata().items()
                if key in {"source_path", "storage_mode"} and value
            }
        )
    return {
        "schema_version": 1,
        "dataset_id": str(dataset_id),
        "source_path": str(source_path),
        "video": video_summary,
        "intensity": stats,
        "saturation": saturation,
        "drift": drift,
        "temporal": temporal,
        "warnings": warnings,
    }


def compute_dataset_qc_from_manifest(manifest: Mapping[str, Any] | str | Path) -> dict[str, Any]:
    """Load a dataset manifest and compute QC for its raw video path."""

    from neurobench.manifests import load_dataset_manifest, manifest_path

    payload = load_dataset_manifest(manifest) if not isinstance(manifest, Mapping) else dict(manifest)
    raw_path = manifest_path(payload, "raw_video")
    if raw_path is None:
        raise ValueError("Dataset manifest does not define paths.raw_video.")
    video = load_video_for_qc(raw_path)
    return compute_video_qc(video, dataset_id=str(payload.get("dataset_id", "")), source_path=str(raw_path))


def load_video_for_qc(path: str | Path) -> Any:
    """Load a small QC-compatible video array.

    NumPy ``.npy`` files are always supported. TIFF files are supported when
    ``tifffile`` is installed in the environment.
    """

    source = Path(path).expanduser()
    if not source.exists():
        raise FileNotFoundError(f"Video path does not exist: {source}")
    if source.suffix.lower() == ".npy":
        from neurobench.data.video import open_video

        return open_video(source)
    if source.suffix.lower() in {".tif", ".tiff"}:
        try:
            import tifffile  # type: ignore
        except ModuleNotFoundError as exc:
            raise RuntimeError("TIFF QC requires tifffile. Use .npy or install tifffile.") from exc
        return tifffile.imread(source)
    raise ValueError(f"Unsupported QC video format: {source.suffix}")


def render_dataset_qc_markdown(qc: Mapping[str, Any]) -> str:
    """Render a concise Markdown QC report."""

    video = qc.get("video", {})
    intensity = qc.get("intensity", {})
    drift = qc.get("drift", {})
    temporal = qc.get("temporal", {})
    lines = [
        f"# Dataset QC: {qc.get('dataset_id') or 'dataset'}",
        "",
        "## Video",
        "",
        f"- Source: `{qc.get('source_path', '')}`",
        f"- Shape: `{video.get('shape', [])}`",
        f"- Frames: {video.get('frames', 0)}",
        f"- Size: {video.get('height', 0)} x {video.get('width', 0)}",
        f"- Dtype: `{video.get('dtype', '')}`",
        "",
        "## Intensity",
        "",
        f"- Mean +/- std: {_fmt(intensity.get('mean'))} +/- {_fmt(intensity.get('std'))}",
        f"- Range: {_fmt(intensity.get('min'))} to {_fmt(intensity.get('max'))}",
        f"- P01 / P50 / P99: {_fmt(intensity.get('p01'))} / {_fmt(intensity.get('p50'))} / {_fmt(intensity.get('p99'))}",
        "",
        "## Temporal Stability",
        "",
        f"- Mean drift delta: {_fmt(drift.get('mean_delta'))}",
        f"- Relative drift: {_fmt(drift.get('relative_delta'))}",
        f"- Frame mean std: {_fmt(temporal.get('frame_mean_std'))}",
        f"- Median absolute frame difference: {_fmt(temporal.get('median_abs_frame_diff'))}",
        "",
        "## Warnings",
        "",
    ]
    warnings = list(qc.get("warnings") or [])
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("No QC warnings reported.")
    return "\n".join(lines).rstrip() + "\n"


def _saturation_summary(array: Any, min_value: float, max_value: float) -> dict[str, float]:
    np = _load_numpy()
    count = max(1, int(array.size))
    return {
        "min_fraction": float(np.count_nonzero(array == min_value) / count),
        "max_fraction": float(np.count_nonzero(array == max_value) / count),
        "zero_fraction": float(np.count_nonzero(array == 0) / count),
    }


def _drift_summary(frame_means: Any) -> dict[str, float]:
    np = _load_numpy()
    if frame_means.size < 2:
        return {"first_half_mean": 0.0, "second_half_mean": 0.0, "mean_delta": 0.0, "relative_delta": 0.0}
    split = max(1, int(frame_means.size // 2))
    first = float(np.mean(frame_means[:split]))
    second = float(np.mean(frame_means[split:]))
    delta = second - first
    scale = max(abs(first), 1e-9)
    return {
        "first_half_mean": first,
        "second_half_mean": second,
        "mean_delta": delta,
        "relative_delta": delta / scale,
    }


def _qc_warnings(stats: Mapping[str, float], saturation: Mapping[str, float], drift: Mapping[str, float], nbytes: int) -> list[str]:
    warnings = []
    if stats["std"] <= 1e-12:
        warnings.append("Video has near-zero intensity variance.")
    if saturation["max_fraction"] >= 0.01:
        warnings.append("At least 1% of pixels are at the observed maximum intensity.")
    if abs(drift["relative_delta"]) >= 0.10:
        warnings.append("Frame mean changed by at least 10% between first and second half.")
    if nbytes >= 4_000_000_000:
        warnings.append("Video is larger than 4 GB; chunked processing is recommended.")
    return warnings


def _fmt(value: Any) -> str:
    try:
        return f"{float(value):.4g}"
    except (TypeError, ValueError):
        return "n/a"


def _load_numpy():
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        raise RuntimeError("NumPy is required for dataset QC.") from exc
    return np
