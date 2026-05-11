"""Import OASIS deconvolution outputs as Neurobench architecture-run metadata."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _load_numpy():
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        raise RuntimeError("OASIS import requires NumPy to read .npy or .npz outputs.") from exc
    return np


def _select_array(data: Any, key: str | None):
    if hasattr(data, "files"):
        if key:
            if key not in data.files:
                raise KeyError(f"Array key {key!r} not found. Available keys: {', '.join(data.files)}")
            return data[key], key
        for candidate in ["spikes", "spks", "deconvolved", "oasis", "S", "C"]:
            if candidate in data.files:
                return data[candidate], candidate
        if not data.files:
            raise ValueError("No arrays found in OASIS .npz output.")
        first = data.files[0]
        return data[first], first
    if key:
        raise ValueError("Array keys are only supported for .npz files.")
    return data, None


def oasis_summary(traces_path: str | Path, key: str | None = None) -> dict[str, Any]:
    np = _load_numpy()
    path = Path(traces_path).expanduser()
    data = np.load(path, allow_pickle=False)
    traces, selected_key = _select_array(data, key)
    shape = tuple(int(value) for value in getattr(traces, "shape", ()))
    return {
        "array_key": selected_key,
        "shape": list(shape),
        "trace_count": shape[0] if len(shape) >= 1 else 0,
        "frame_count": shape[1] if len(shape) >= 2 else None,
    }


def build_oasis_run(
    traces_path: str | Path,
    dataset_id: str,
    run_id: str = "oasis_import",
    label: str = "OASIS deconvolution",
    key: str | None = None,
    source_traces: str | Path | None = None,
) -> dict[str, Any]:
    path = Path(traces_path).expanduser()
    summary = oasis_summary(path, key)
    artifacts: dict[str, Any] = {"oasis_traces": str(path)}
    if source_traces is not None:
        artifacts["source_traces"] = str(Path(source_traces).expanduser())
    parameters: dict[str, Any] = {"source": str(path), "array_key": summary["array_key"]}
    if "source_traces" in artifacts:
        parameters["source_traces"] = artifacts["source_traces"]

    return {
        "schema_version": 1,
        "run_id": run_id,
        "dataset_id": dataset_id,
        "label": label,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pipeline": [{"name": "oasis_deconvolution"}],
        "parameters": parameters,
        "summary": {
            "roi_count": summary["trace_count"],
            "event_count": 0,
            "suggestion_count": 0,
            "frame_count": summary["frame_count"],
            "trace_count": summary["trace_count"],
            "array_shape": summary["shape"],
        },
        "artifacts": artifacts,
    }
