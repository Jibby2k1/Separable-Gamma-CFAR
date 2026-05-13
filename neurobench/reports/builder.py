"""Build MetricsReport objects from pipeline-run manifests."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from neurobench.models.metrics import MetricsReport
from neurobench.models.pipeline import PipelineRun


METRIC_SECTIONS = ("pixel_level", "object_level", "event_level", "annotation", "runtime")


def build_metrics_report_from_pipeline_runs(
    runs_or_paths: Sequence[PipelineRun | str | Path],
    *,
    metrics_report_id: str | None = None,
    created_at: str | None = None,
) -> MetricsReport:
    """Create a MetricsReport from one or more pipeline_run.json manifests."""

    runs, paths = _load_runs(runs_or_paths)
    if not runs:
        raise ValueError("At least one pipeline run is required.")
    dataset_ids = sorted({run.dataset_id for run in runs})
    run_ids = [run.run_id for run in runs]
    metrics = _metrics_from_runs(runs)
    warnings = [f"{run.run_id}: {warning}" for run in runs for warning in run.warnings]
    provenance = _provenance_from_runs(runs, paths)
    report = MetricsReport(
        schema_version=1,
        metrics_report_id=metrics_report_id or f"metrics_{'_'.join(run_ids)}",
        dataset_id=dataset_ids[0] if len(dataset_ids) == 1 else "multiple_datasets",
        run_ids=run_ids,
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
        metrics=metrics,
        figures=[],
        warnings=warnings,
        provenance=provenance,
        extras={"dataset_ids": dataset_ids} if len(dataset_ids) > 1 else {},
    )
    report.validate()
    return report


def build_metrics_report_from_pipeline_run(
    run_or_path: PipelineRun | str | Path,
    *,
    metrics_report_id: str | None = None,
    created_at: str | None = None,
) -> MetricsReport:
    """Convenience wrapper for a single pipeline run."""

    return build_metrics_report_from_pipeline_runs(
        [run_or_path],
        metrics_report_id=metrics_report_id,
        created_at=created_at,
    )


def _load_runs(runs_or_paths: Sequence[PipelineRun | str | Path]) -> tuple[list[PipelineRun], list[str]]:
    runs: list[PipelineRun] = []
    paths: list[str] = []
    for item in runs_or_paths:
        if isinstance(item, PipelineRun):
            runs.append(item)
            paths.append("")
        else:
            path = Path(item)
            runs.append(PipelineRun.load_json(path))
            paths.append(str(path))
    return runs, paths


def _metrics_from_runs(runs: Sequence[PipelineRun]) -> dict[str, Any]:
    if len(runs) == 1:
        metrics = dict(runs[0].metrics)
        for section in METRIC_SECTIONS:
            metrics.setdefault(section, {})
        metrics["runtime"] = {**_runtime_metrics(runs[0]), **dict(metrics.get("runtime") or {})}
        return metrics

    by_run = {}
    for run in runs:
        run_metrics = dict(run.metrics)
        run_metrics["runtime"] = {**_runtime_metrics(run), **dict(run_metrics.get("runtime") or {})}
        by_run[run.run_id] = run_metrics
    return {
        "pixel_level": {},
        "object_level": {},
        "event_level": {},
        "annotation": {},
        "runtime": {
            "run_count": len(runs),
            "completed_count": sum(1 for run in runs if run.status == "completed"),
            "failed_count": sum(1 for run in runs if run.status == "failed"),
        },
        "by_run": by_run,
    }


def _runtime_metrics(run: PipelineRun) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "status": run.status,
        "artifact_count": len(run.artifacts),
        "warning_count": len(run.warnings),
        "log_count": len(run.logs),
    }
    duration = _duration_seconds(run.created_at, run.completed_at)
    if duration is not None:
        metrics["duration_seconds"] = duration
    return metrics


def _duration_seconds(start: str, end: str | None) -> float | None:
    if not start or not end:
        return None
    try:
        started = datetime.fromisoformat(start.replace("Z", "+00:00"))
        finished = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0.0, (finished - started).total_seconds())


def _provenance_from_runs(runs: Sequence[PipelineRun], paths: Sequence[str]) -> dict[str, Any]:
    artifact_paths = []
    for run in runs:
        for artifact in run.artifacts:
            if hasattr(artifact, "path"):
                artifact_paths.append(str(artifact.path))
            elif isinstance(artifact, dict) and artifact.get("path"):
                artifact_paths.append(str(artifact["path"]))
    return {
        "pipeline_run_paths": [path for path in paths if path],
        "pipeline_spec_ids": [run.pipeline_spec_id for run in runs],
        "parameter_hashes": {run.run_id: run.parameter_hash for run in runs},
        "artifact_paths": sorted(set(artifact_paths)),
        "logs": {run.run_id: list(run.logs) for run in runs if run.logs},
        "code": {run.run_id: dict(run.code) for run in runs if run.code},
        "environment": {run.run_id: dict(run.environment) for run in runs if run.environment},
    }
