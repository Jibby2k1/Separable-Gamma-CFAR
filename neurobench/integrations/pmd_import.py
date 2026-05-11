"""Import PMD denoising outputs as Neurobench architecture-run metadata."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def build_pmd_run(
    denoised_video: str | Path,
    dataset_id: str,
    run_id: str = "pmd_denoised",
    label: str = "PMD denoised video",
    source_video: str | Path | None = None,
    frame_count: int | None = None,
    width: int | None = None,
    height: int | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Create a lightweight run manifest for a PMD-denoised video artifact.

    This importer intentionally does not read the video file. PMD outputs vary
    across labs, and keeping this metadata-only lets us attach denoised evidence
    to the Architecture Lab without forcing image I/O dependencies.
    """

    denoised_path = Path(denoised_video).expanduser()
    parameters: dict[str, Any] = {"source": str(denoised_path), "method": "pmd"}
    if source_video is not None:
        parameters["raw_source"] = str(Path(source_video).expanduser())
    if notes:
        parameters["notes"] = notes

    summary = {
        "roi_count": 0,
        "event_count": 0,
        "suggestion_count": 0,
        "frame_count": frame_count,
        "width": width,
        "height": height,
    }

    artifacts: dict[str, Any] = {"denoised_video": str(denoised_path)}
    if source_video is not None:
        artifacts["source_video"] = str(Path(source_video).expanduser())

    return {
        "schema_version": 1,
        "run_id": run_id,
        "dataset_id": dataset_id,
        "label": label,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pipeline": [{"name": "pmd_denoising"}],
        "parameters": parameters,
        "summary": summary,
        "artifacts": artifacts,
    }
