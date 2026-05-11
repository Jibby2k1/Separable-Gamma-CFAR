"""Import Suite2p outputs as Neurobench architecture-run metadata."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _load_numpy():
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        raise RuntimeError("Suite2p import requires NumPy to read .npy outputs.") from exc
    return np


def suite2p_summary(suite2p_dir: str | Path) -> dict[str, Any]:
    np = _load_numpy()
    root = Path(suite2p_dir)
    stat_path = root / "stat.npy"
    if not stat_path.exists():
        raise FileNotFoundError(f"Suite2p stat.npy not found: {stat_path}")
    stat = np.load(stat_path, allow_pickle=True)
    f_path = root / "F.npy"
    spks_path = root / "spks.npy"
    f = np.load(f_path, allow_pickle=False) if f_path.exists() else None
    spks = np.load(spks_path, allow_pickle=False) if spks_path.exists() else None
    return {
        "roi_count": int(len(stat)),
        "trace_count": int(f.shape[0]) if f is not None and f.ndim >= 2 else 0,
        "frame_count": int(f.shape[1]) if f is not None and f.ndim >= 2 else None,
        "spks_trace_count": int(spks.shape[0]) if spks is not None and spks.ndim >= 2 else 0,
    }


def build_suite2p_run(
    suite2p_dir: str | Path,
    dataset_id: str,
    run_id: str = "suite2p_import",
    label: str = "Suite2p import",
) -> dict[str, Any]:
    root = Path(suite2p_dir)
    summary = suite2p_summary(root)
    return {
        "schema_version": 1,
        "run_id": run_id,
        "dataset_id": dataset_id,
        "label": label,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pipeline": [{"name": "suite2p_import"}],
        "parameters": {"source": str(root)},
        "summary": {
            "roi_count": summary["roi_count"],
            "event_count": 0,
            "suggestion_count": 0,
            "frame_count": summary["frame_count"],
            "trace_count": summary["trace_count"],
            "spks_trace_count": summary["spks_trace_count"],
        },
        "artifacts": {
            "suite2p_dir": str(root),
            "stat_npy": str(root / "stat.npy"),
            "f_npy": str(root / "F.npy"),
            "fneu_npy": str(root / "Fneu.npy"),
            "spks_npy": str(root / "spks.npy"),
            "ops_npy": str(root / "ops.npy"),
        },
    }
