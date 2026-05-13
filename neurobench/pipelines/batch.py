"""Batch execution helpers for pipeline specs."""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
import re
from typing import Any

from neurobench.manifests import load_json, write_json
from neurobench.pipelines.executor import execute_pipeline


def execute_batch(spec_paths: Sequence[str | Path], *, run_root: str | Path) -> dict[str, Any]:
    """Execute multiple pipeline specs while preserving successful runs."""
    root = Path(run_root)
    root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for index, spec_path_like in enumerate(spec_paths, start=1):
        spec_path = Path(spec_path_like)
        spec: dict[str, Any] | None = None
        run_id = spec_path.stem
        run_dir = root / f"{index:03d}_{_safe_name(run_id)}"
        try:
            spec = load_json(spec_path)
            run_id = str(spec.get("run_id") or spec_path.stem)
            run_dir = root / f"{index:03d}_{_safe_name(run_id)}"
            result = execute_pipeline(spec, run_root=run_dir)
            records.append(
                {
                    "spec_path": str(spec_path),
                    "run_id": result["pipeline_run"]["run_id"],
                    "run_root": _display_path(run_dir, root),
                    "status": "completed",
                    "artifact_count": len(result["pipeline_run"].get("artifacts", [])),
                }
            )
        except Exception as exc:
            records.append(
                {
                    "spec_path": str(spec_path),
                    "run_id": run_id,
                    "run_root": _display_path(run_dir, root),
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
    succeeded = sum(1 for record in records if record["status"] == "completed")
    failed = sum(1 for record in records if record["status"] == "failed")
    summary = {
        "schema_version": 1,
        "status": "completed" if failed == 0 else "completed_with_failures",
        "total": len(records),
        "succeeded": succeeded,
        "failed": failed,
        "runs": records,
    }
    write_json(root / "batch_summary.json", summary)
    return summary


def _safe_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return name or "run"


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())
