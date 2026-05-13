"""Dry-run pipeline executor and execution planning helpers."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from neurobench.data.checksums import checksum_file
from neurobench.models.pipeline import PipelineRun
from neurobench.pipeline_catalog import normalize_pipeline
from neurobench.pipelines.artifacts import ArtifactStore
from neurobench.pipelines.devices import resolve_device_from_spec
from neurobench.pipelines.specs import pipeline_spec_parameter_hash
from neurobench.pipelines.stages import StageRegistry, default_stage_registry
from neurobench.logging import RunLogger


@dataclass(frozen=True)
class DryRunStep:
    """One validated stage in a dry-run execution plan."""

    step_id: str
    stage_id: str
    input_artifact: str
    output_artifact: str
    params: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "stage_id": self.stage_id,
            "input_artifact": self.input_artifact,
            "output_artifact": self.output_artifact,
            "params": dict(self.params),
        }


def dry_run_pipeline(
    spec_or_pipeline: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    registry: StageRegistry | None = None,
    require_executable: bool = True,
    validate_artifacts: bool = False,
    initial_artifacts: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Validate a structured pipeline and return an inspectable execution plan.

    The dry run does not execute image processing code. It validates stage IDs,
    parameter defaults/ranges, stage availability, and optionally artifact flow.
    """
    registry = registry or default_stage_registry()
    spec = _as_spec(spec_or_pipeline)
    pipeline = normalize_pipeline(spec.get("pipeline"), require_structured=True)
    steps = registry.validate_steps(pipeline, require_executable=require_executable)
    available_artifacts = set(initial_artifacts or ())
    planned_steps: list[DryRunStep] = []
    for step in steps:
        stage = registry.get(str(step["stage_id"]))
        input_artifact = stage.input_artifact
        output_artifact = stage.output_artifact
        if validate_artifacts and input_artifact and input_artifact not in available_artifacts:
            raise ValueError(
                f"Pipeline step '{step['id']}' requires missing artifact '{input_artifact}'."
            )
        if output_artifact:
            available_artifacts.add(output_artifact)
        planned_steps.append(
            DryRunStep(
                step_id=str(step["id"]),
                stage_id=str(step["stage_id"]),
                input_artifact=input_artifact,
                output_artifact=output_artifact,
                params=dict(step.get("params") or {}),
            )
        )

    return {
        "status": "dry_run_ok",
        "dataset_id": spec.get("dataset_id", ""),
        "run_id": spec.get("run_id", ""),
        "parameter_hash": pipeline_spec_parameter_hash(spec),
        "require_executable": require_executable,
        "validate_artifacts": validate_artifacts,
        "steps": [step.as_dict() for step in planned_steps],
        "available_artifacts": sorted(available_artifacts),
    }


def execute_pipeline(
    spec_or_pipeline: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    run_root: str | Path,
    registry: StageRegistry | None = None,
    device: str | None = None,
) -> dict[str, Any]:
    """Execute the currently wired CPU-safe pipeline subset.

    This first executor intentionally supports only small, deterministic Python
    stages. Unsupported catalog stages fail clearly so planned UI workflows do
    not appear silently executable.
    """
    spec = _as_spec(spec_or_pipeline)
    device_spec = resolve_device_from_spec(spec, override=device)
    plan = dry_run_pipeline(spec, registry=registry, require_executable=True, validate_artifacts=False)
    created_at = datetime.now(timezone.utc).isoformat()
    pipeline_run = PipelineRun(
        schema_version=1,
        run_id=str(spec.get("run_id") or f"run_{plan['parameter_hash'][:12]}"),
        dataset_id=str(spec.get("dataset_id") or "unknown_dataset"),
        pipeline_spec_id=str(spec.get("pipeline_spec_id") or spec.get("run_id") or "inline_pipeline_spec"),
        status="running",
        created_at=created_at,
        parameter_hash=str(plan["parameter_hash"]),
        artifacts=[],
        environment={
            "runner": "neurobench.pipelines.executor",
            "device": device_spec.resolved,
            "device_requested": device_spec.requested,
            "device_backend": device_spec.backend,
            "device_available": device_spec.available,
            "device_reason": device_spec.reason,
        },
        extras={"input_checksums": []},
    )
    store = ArtifactStore(run_root, pipeline_run)
    logger = RunLogger(run_root, pipeline_run)
    artifacts: dict[str, Path] = {}
    try:
        for step in plan["steps"]:
            stage_id = str(step["stage_id"])
            logger.stage_started(stage_id, step_id=step["step_id"])
            runner = _STAGE_RUNNERS.get(stage_id)
            if runner is None:
                raise NotImplementedError(f"Pipeline stage '{stage_id}' is not wired for local execution yet.")
            output_key, output_path = runner(step, artifacts, store)
            if output_key:
                artifacts[output_key] = output_path
            logger.stage_completed(stage_id, step_id=step["step_id"], output_artifact=output_key)
        pipeline_run.status = "completed"
        pipeline_run.completed_at = datetime.now(timezone.utc).isoformat()
    except Exception as exc:
        pipeline_run.status = "failed"
        pipeline_run.completed_at = datetime.now(timezone.utc).isoformat()
        logger.error(str(exc), event_type="pipeline_failed")
        store.write_manifest()
        raise
    store.write_manifest()
    return {"status": pipeline_run.status, "run_root": str(Path(run_root)), "plan": plan, "pipeline_run": pipeline_run.to_dict()}


def _as_spec(spec_or_pipeline: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if isinstance(spec_or_pipeline, Mapping):
        if "pipeline" not in spec_or_pipeline:
            raise ValueError("Pipeline spec is missing required 'pipeline' field.")
        return dict(spec_or_pipeline)
    if isinstance(spec_or_pipeline, Sequence) and not isinstance(spec_or_pipeline, (str, bytes, bytearray)):
        return {"pipeline": list(spec_or_pipeline)}
    raise TypeError("dry_run_pipeline expects a pipeline spec mapping or pipeline step sequence.")


def _load_numpy():
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        raise RuntimeError("NumPy is required to execute local pipeline stages.") from exc
    return np


def _load_npy(path: Path):
    np = _load_numpy()
    if path.suffix != ".npy":
        raise ValueError(f"Local executor currently supports .npy video artifacts, got: {path}")
    return np.load(path)


def _run_source_video_import(step: Mapping[str, Any], artifacts: Mapping[str, Path], store: ArtifactStore) -> tuple[str, Path]:
    source = Path(str(step["params"]["source"])).expanduser()
    if not source.is_absolute():
        source = source.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Source video does not exist: {source}")
    summary: dict[str, Any] = {}
    if source.suffix == ".npy":
        video = _load_npy(source)
        summary.update({"shape": [int(value) for value in video.shape], "dtype": str(video.dtype)})
    _record_input_checksum(store, checksum_file(source, path_id="raw_video"))
    store.register_file(
        source,
        artifact_id="raw_video.v1",
        kind="raw_video",
        producer_stage=str(step["stage_id"]),
        summary=summary,
    )
    return "raw_video", source


def _run_temporal_highpass_gaussian(
    step: Mapping[str, Any],
    artifacts: Mapping[str, Path],
    store: ArtifactStore,
) -> tuple[str, Path]:
    np = _load_numpy()
    source = _require_artifact(artifacts, "raw_video", step)
    video = _load_npy(source).astype(np.float32, copy=False)
    sigma = float(step["params"].get("sigma_frames", 6.0))
    try:
        from scipy.ndimage import gaussian_filter1d

        baseline = gaussian_filter1d(video, sigma=sigma, axis=0, mode="nearest") if sigma > 0 else video * 0
    except ModuleNotFoundError:
        baseline = np.mean(video, axis=0, keepdims=True)
    highpass = (video - baseline).astype(np.float32, copy=False)
    out = store.artifact_path("preprocessing", "highpass_video.npy")
    np.save(out, highpass)
    store.register_file(
        out,
        artifact_id="highpass_video.v1",
        kind="highpass_video",
        producer_stage=str(step["stage_id"]),
        summary={"shape": [int(value) for value in highpass.shape], "sigma_frames": sigma},
    )
    return "highpass_video", out


def _run_robust_positive_local_z(
    step: Mapping[str, Any],
    artifacts: Mapping[str, Path],
    store: ArtifactStore,
) -> tuple[str, Path]:
    np = _load_numpy()
    source = artifacts.get("highpass_video") or artifacts.get("raw_video")
    if source is None:
        raise ValueError(f"Pipeline step '{step['step_id']}' requires missing artifact 'highpass_video'.")
    video = _load_npy(source).astype(np.float32, copy=False)
    epsilon = float(step["params"].get("epsilon", 1.0))
    frame_median = np.median(video, axis=(1, 2), keepdims=True)
    mad = np.median(np.abs(video - frame_median), axis=(1, 2), keepdims=True)
    z_stack = np.maximum((video - frame_median) / (1.4826 * mad + epsilon), 0.0).astype(np.float32, copy=False)
    out = store.artifact_path("preprocessing", "z_stack.npy")
    np.save(out, z_stack)
    store.register_file(
        out,
        artifact_id="z_stack.v1",
        kind="z_stack",
        producer_stage=str(step["stage_id"]),
        summary={"shape": [int(value) for value in z_stack.shape], "max_z": float(np.max(z_stack))},
    )
    return "z_stack", out


def _run_spatial_gaussian(
    step: Mapping[str, Any],
    artifacts: Mapping[str, Path],
    store: ArtifactStore,
) -> tuple[str, Path]:
    np = _load_numpy()
    source = _require_artifact(artifacts, "highpass_video", step)
    video = _load_npy(source).astype(np.float32, copy=False)
    sigma = float(step["params"].get("sigma_px", 0.8))
    if sigma > 0:
        try:
            from scipy.ndimage import gaussian_filter
        except ModuleNotFoundError as exc:
            raise RuntimeError("SciPy is required for spatial_gaussian execution.") from exc
        smoothed = gaussian_filter(video, sigma=(0.0, sigma, sigma), mode="nearest").astype(np.float32, copy=False)
    else:
        smoothed = video.astype(np.float32, copy=True)
    out = store.artifact_path("preprocessing", "smoothed_video.npy")
    np.save(out, smoothed)
    store.register_file(
        out,
        artifact_id="smoothed_video.v1",
        kind="smoothed_video",
        producer_stage=str(step["stage_id"]),
        summary={"shape": [int(value) for value in smoothed.shape], "sigma_px": sigma},
    )
    return "smoothed_video", out


def _run_rigid_shift_estimate(
    step: Mapping[str, Any],
    artifacts: Mapping[str, Path],
    store: ArtifactStore,
) -> tuple[str, Path]:
    np = _load_numpy()
    from neurobench.algorithms.motion import estimate_rigid_shifts

    source = _require_artifact(artifacts, "raw_video", step)
    video = _load_npy(source).astype(np.float32, copy=False)
    params = step["params"]
    max_shift_px = int(params.get("max_shift_px", 4))
    reference = str(params.get("reference", "first"))
    result = estimate_rigid_shifts(video, max_shift_px=max_shift_px, reference=reference, device=_resolved_device(store))

    shift_trace_out = store.artifact_path("motion", "rigid_shift_trace.json")
    shift_trace_out.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "stage_id": str(step["stage_id"]),
                "summary": result["summary"],
                "shifts": result["shifts"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    store.register_file(
        shift_trace_out,
        artifact_id="rigid_shift_trace.v1",
        kind="rigid_shift_trace",
        producer_stage=str(step["stage_id"]),
        summary=dict(result["summary"]),
    )

    out = store.artifact_path("motion", "registered_video.npy")
    np.save(out, result["registered_video"].astype(np.float32, copy=False))
    store.register_file(
        out,
        artifact_id="registered_video.v1",
        kind="registered_video",
        producer_stage=str(step["stage_id"]),
        summary=dict(result["summary"]),
    )
    return "registered_video", out


def _run_gamma_cfar(
    step: Mapping[str, Any],
    artifacts: Mapping[str, Path],
    store: ArtifactStore,
) -> tuple[str, Path]:
    np = _load_numpy()
    from neurobench.algorithms.cfar import robust_local_cfar

    source = _require_artifact(artifacts, "smoothed_video", step)
    video = _load_npy(source).astype(np.float32, copy=False)
    params = step["params"]
    pfa = float(params.get("pfa", 0.001))
    guard_px = int(params.get("guard_px", 2))
    training_radius_px = int(params.get("training_radius_px", max(guard_px + 1, 11)))
    epsilon = float(params.get("epsilon", 1e-6))
    result = robust_local_cfar(
        video,
        pfa=pfa,
        guard_px=guard_px,
        training_radius_px=training_radius_px,
        epsilon=epsilon,
        device=_resolved_device(store),
    )
    mask = result["mask"].astype(np.uint8, copy=False)
    out = store.artifact_path("candidates", "candidate_mask.npy")
    np.save(out, mask)
    summary: dict[str, Any] = {
        "shape": [int(value) for value in mask.shape],
        "pfa": pfa,
        "guard_px": guard_px,
        "training_radius_px": training_radius_px,
        "threshold_z": float(result["threshold_z"]),
        "active_fraction": float(result["active_fraction"]),
    }
    if "update_alpha" in params:
        summary["update_alpha"] = float(params["update_alpha"])
    store.register_file(
        out,
        artifact_id="candidate_mask.v1",
        kind="candidate_mask",
        producer_stage=str(step["stage_id"]),
        summary=summary,
    )
    return "candidate_mask", out


def _run_component_filter(step: Mapping[str, Any], artifacts: Mapping[str, Path], store: ArtifactStore) -> tuple[str, Path]:
    np = _load_numpy()
    source = _require_artifact(artifacts, "z_stack", step)
    z_stack = _load_npy(source).astype(np.float32, copy=False)
    params = step["params"]
    seed_z = float(params.get("seed_z", 2.0))
    min_area = int(params.get("min_area_px", 8))
    max_area = int(params.get("max_area_px", 260))
    projection = np.max(z_stack, axis=0)
    mask = projection >= seed_z
    try:
        from scipy import ndimage
    except ModuleNotFoundError as exc:
        raise RuntimeError("SciPy is required for component_filter execution.") from exc
    labels, count = ndimage.label(mask)
    objects = ndimage.find_objects(labels)
    candidates: list[dict[str, Any]] = []
    for label_index, slices in enumerate(objects, start=1):
        if slices is None:
            continue
        component = labels[slices] == label_index
        area = int(np.count_nonzero(component))
        if area < min_area or area > max_area:
            continue
        ys, xs = np.nonzero(component)
        y0, x0 = slices[0].start, slices[1].start
        abs_xs = xs + x0
        abs_ys = ys + y0
        peak = float(np.max(projection[slices][component]))
        candidates.append(
            {
                "id": f"roi_{len(candidates) + 1:03d}",
                "x": float(np.mean(abs_xs)),
                "y": float(np.mean(abs_ys)),
                "area_px": area,
                "peak_z": peak,
                "bbox": [int(np.min(abs_xs)), int(np.min(abs_ys)), int(np.max(abs_xs)), int(np.max(abs_ys))],
            }
        )
    out = store.artifact_path("candidates", "roi_candidates.json")
    out.write_text(json.dumps({"schema_version": 1, "candidates": candidates}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    store.register_file(
        out,
        artifact_id="roi_candidates.v1",
        kind="roi_candidates",
        producer_stage=str(step["stage_id"]),
        summary={"count": len(candidates), "seed_z": seed_z, "min_area_px": min_area, "max_area_px": max_area},
    )
    return "roi_candidates", out


def _run_heuristic_priority_v1(
    step: Mapping[str, Any],
    artifacts: Mapping[str, Path],
    store: ArtifactStore,
) -> tuple[str, Path]:
    from neurobench.discovery.ranking import rank_candidates

    source = _require_artifact(artifacts, "roi_candidates", step)
    payload = json.loads(source.read_text(encoding="utf-8"))
    candidates = list(payload.get("candidates", []) or [])
    weights = {
        "local_correlation_weight": step["params"].get("local_correlation_weight", 0.2),
        "event_support_weight": step["params"].get("event_support_weight", 0.2),
        "artifact_weight": step["params"].get("artifact_weight", -0.15),
    }
    video_shape = None
    if "raw_video" in artifacts:
        try:
            video_shape = _load_npy(artifacts["raw_video"]).shape
        except Exception:
            video_shape = None
    ranked = rank_candidates(candidates, video_shape=video_shape, weights=weights)
    out = store.artifact_path("candidates", "ranked_candidates.json")
    out.write_text(json.dumps(ranked, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    top_score = ranked["ranked_candidates"][0]["priority_score"] if ranked["ranked_candidates"] else 0.0
    store.register_file(
        out,
        artifact_id="ranked_candidates.v1",
        kind="ranked_candidates",
        producer_stage=str(step["stage_id"]),
        summary={"count": len(ranked["ranked_candidates"]), "top_priority_score": float(top_score), "weights": weights},
    )
    return "ranked_candidates", out


def _require_artifact(artifacts: Mapping[str, Path], key: str, step: Mapping[str, Any]) -> Path:
    if key not in artifacts:
        raise ValueError(f"Pipeline step '{step['step_id']}' requires missing artifact '{key}'.")
    return artifacts[key]


def _resolved_device(store: ArtifactStore) -> str:
    return str(store.pipeline_run.environment.get("device") or "cpu")


def _record_input_checksum(store: ArtifactStore, record: Mapping[str, Any]) -> None:
    records = list(store.pipeline_run.extras.get("input_checksums") or [])
    path_id = record.get("path_id")
    if path_id is not None:
        records = [item for item in records if item.get("path_id") != path_id]
    records.append(dict(record))
    store.pipeline_run.extras["input_checksums"] = records


_STAGE_RUNNERS = {
    "source_video_import": _run_source_video_import,
    "temporal_highpass_gaussian": _run_temporal_highpass_gaussian,
    "robust_positive_local_z": _run_robust_positive_local_z,
    "spatial_gaussian": _run_spatial_gaussian,
    "rigid_shift_estimate": _run_rigid_shift_estimate,
    "gamma_cfar": _run_gamma_cfar,
    "adaptive_gamma_cfar": _run_gamma_cfar,
    "component_filter": _run_component_filter,
    "heuristic_priority_v1": _run_heuristic_priority_v1,
}
