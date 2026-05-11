"""Shared pipeline stage catalog and validation helpers."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from numbers import Real
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class ParameterRange:
    """Inclusive numeric parameter bounds."""

    minimum: float | None = None
    maximum: float | None = None

    def validate(self, stage_id: str, param_name: str, value: Any) -> None:
        if not isinstance(value, Real) or isinstance(value, bool):
            raise ValueError(f"Pipeline stage '{stage_id}' parameter '{param_name}' must be numeric.")
        if self.minimum is not None and value < self.minimum:
            raise ValueError(
                f"Pipeline stage '{stage_id}' parameter '{param_name}'={value} is below minimum {self.minimum}."
            )
        if self.maximum is not None and value > self.maximum:
            raise ValueError(
                f"Pipeline stage '{stage_id}' parameter '{param_name}'={value} is above maximum {self.maximum}."
            )

    def as_dict(self) -> dict[str, float]:
        data: dict[str, float] = {}
        if self.minimum is not None:
            data["minimum"] = self.minimum
        if self.maximum is not None:
            data["maximum"] = self.maximum
        return data


@dataclass(frozen=True)
class PipelineStage:
    """Catalog entry for a pipeline stage."""

    stage_id: str
    label: str
    order: int
    required_params: tuple[str, ...] = ()
    default_params: Mapping[str, Any] | None = None
    param_ranges: Mapping[str, ParameterRange] | None = None
    description: str = ""

    def merged_params(self, params: Mapping[str, Any] | None) -> dict[str, Any]:
        merged = deepcopy(dict(self.default_params or {}))
        merged.update(dict(params or {}))
        return merged

    def as_dict(self) -> dict[str, Any]:
        metadata = _stage_metadata(self.stage_id)
        return {
            "stage_id": self.stage_id,
            "label": self.label,
            "order": self.order,
            "type": metadata["type"],
            "input": metadata["input"],
            "output": metadata["output"],
            "required_params": list(self.required_params),
            "default_params": deepcopy(dict(self.default_params or {})),
            "param_ranges": {key: value.as_dict() for key, value in dict(self.param_ranges or {}).items()},
            "description": self.description,
            "why_use_it": metadata["why_use_it"],
            "parameter_docs": _parameter_docs(self.stage_id, self),
            "real_time_profile": metadata["real_time_profile"],
        }


_DEFAULT_REALTIME = {
    "mode": "unknown",
    "latency_budget_ms": None,
    "requires_gpu": False,
    "stateful": False,
    "adaptive": False,
    "closed_loop_candidate": False,
}


_STAGE_METADATA: dict[str, dict[str, Any]] = {
    "source_video_import": {
        "type": "import",
        "input": "",
        "output": "raw_video",
        "why_use_it": "Makes the source movie explicit so downstream artifacts and timing can be traced.",
        "real_time_profile": {"mode": "streaming", "latency_budget_ms": 1.0, "closed_loop_candidate": True},
    },
    "review_data_import": {
        "type": "import",
        "input": "review_data",
        "output": "roi_candidates",
        "why_use_it": "Reuses an existing reviewed/candidate dataset as an Architecture Lab baseline.",
        "real_time_profile": {"mode": "offline", "latency_budget_ms": None},
    },
    "temporal_highpass_gaussian": {
        "type": "temporal_smoothing",
        "input": "raw_video",
        "output": "highpass_video",
        "why_use_it": "Penalizes slow baseline drift while preserving fast calcium transients.",
        "real_time_profile": {"mode": "streaming", "latency_budget_ms": 2.0, "stateful": True, "adaptive": True, "closed_loop_candidate": True},
    },
    "event_preserving_noise_suppression": {
        "type": "denoising",
        "input": "highpass_video",
        "output": "denoised_video",
        "why_use_it": "Reduces impulse-like noise before candidate extraction without intentionally blurring events away.",
        "real_time_profile": {"mode": "streaming", "latency_budget_ms": 2.0, "stateful": True, "adaptive": True, "closed_loop_candidate": True},
    },
    "spatial_gaussian": {
        "type": "spatial_smoothing",
        "input": "highpass_video",
        "output": "smoothed_video",
        "why_use_it": "Suppresses pixel-scale noise before CFAR or local-z scoring.",
        "real_time_profile": {"mode": "streaming", "latency_budget_ms": 1.0, "closed_loop_candidate": True},
    },
    "rigid_shift_estimate": {
        "type": "motion_correction",
        "input": "raw_video",
        "output": "registered_video",
        "why_use_it": "Flags or corrects frame drift that can masquerade as neural activity.",
        "real_time_profile": {"mode": "streaming", "latency_budget_ms": 3.0, "stateful": True, "closed_loop_candidate": True},
    },
    "suite2p_import": {
        "type": "import",
        "input": "suite2p_output",
        "output": "roi_candidates",
        "why_use_it": "Benchmarks the current workflow against a widely used ROI extraction package.",
        "real_time_profile": {"mode": "offline", "latency_budget_ms": None, "requires_gpu": False},
    },
    "pmd_import": {
        "type": "import",
        "input": "pmd_output",
        "output": "denoised_video",
        "why_use_it": "Compares against a low-rank denoising baseline without treating it as ground truth.",
        "real_time_profile": {"mode": "offline", "latency_budget_ms": None},
    },
    "oasis_import": {
        "type": "import",
        "input": "trace_array",
        "output": "deconvolved_events",
        "why_use_it": "Compares reviewed calcium events with an established deconvolution output.",
        "real_time_profile": {"mode": "streaming", "latency_budget_ms": 1.0, "stateful": True, "closed_loop_candidate": True},
    },
    "pmd_denoised_video_import": {
        "type": "import",
        "input": "raw_video",
        "output": "highpass_video",
        "why_use_it": "Uses a denoised movie as candidate evidence while preserving raw-video provenance.",
        "real_time_profile": {"mode": "offline", "latency_budget_ms": None},
    },
    "robust_positive_local_z": {
        "type": "filtering",
        "input": "highpass_video",
        "output": "z_stack",
        "why_use_it": "Highlights positive local excursions using robust local scale estimates.",
        "real_time_profile": {"mode": "streaming", "latency_budget_ms": 2.0, "stateful": True, "adaptive": True, "closed_loop_candidate": True},
    },
    "adaptive_ewma_z": {
        "type": "filtering",
        "input": "raw_video",
        "output": "z_stack",
        "why_use_it": "Maintains streaming per-pixel baseline and variance estimates for 100 Hz candidate screening.",
        "real_time_profile": {"mode": "streaming", "latency_budget_ms": 2.0, "stateful": True, "adaptive": True, "closed_loop_candidate": True},
    },
    "gamma_cfar": {
        "type": "filtering",
        "input": "smoothed_video",
        "output": "candidate_mask",
        "why_use_it": "Adapts thresholds to local background so bright and dim regions are treated more fairly.",
        "real_time_profile": {"mode": "streaming", "latency_budget_ms": 2.0, "adaptive": True, "closed_loop_candidate": True},
    },
    "adaptive_gamma_cfar": {
        "type": "filtering",
        "input": "smoothed_video",
        "output": "candidate_mask",
        "why_use_it": "Uses a local training region and streaming update rate to keep CFAR thresholds responsive at high frame rates.",
        "real_time_profile": {"mode": "streaming", "latency_budget_ms": 2.0, "stateful": True, "adaptive": True, "closed_loop_candidate": True},
    },
    "candidate_event_pipeline": {
        "type": "filtering",
        "input": "z_stack",
        "output": "candidate_events",
        "why_use_it": "Produces permissive event and discovery candidates for human triage.",
        "real_time_profile": {"mode": "offline", "latency_budget_ms": None},
    },
    "component_filter": {
        "type": "trace_extraction",
        "input": "z_stack",
        "output": "roi_candidates",
        "why_use_it": "Turns pixel evidence into object-level neuron candidates with size constraints.",
        "real_time_profile": {"mode": "streaming", "latency_budget_ms": 2.0, "closed_loop_candidate": True},
    },
    "local_background_ring": {
        "type": "background_correction",
        "input": "roi_candidates",
        "output": "roi_traces",
        "why_use_it": "Subtracts nearby background/neuropil signal before event scoring.",
        "real_time_profile": {"mode": "streaming", "latency_budget_ms": 1.0, "closed_loop_candidate": True},
    },
    "trace_event_scoring": {
        "type": "event_model",
        "input": "roi_traces",
        "output": "candidate_events",
        "why_use_it": "Provides a simple thresholded trace event baseline.",
        "real_time_profile": {"mode": "streaming", "latency_budget_ms": 1.0, "closed_loop_candidate": True},
    },
    "robust_kalman_positive_innovation": {
        "type": "event_model",
        "input": "roi_traces",
        "output": "candidate_events",
        "why_use_it": "Tracks a robust baseline and calls positive innovations as candidate transients.",
        "real_time_profile": {"mode": "streaming", "latency_budget_ms": 1.0, "stateful": True, "adaptive": True, "closed_loop_candidate": True},
    },
    "oasis_deconvolution_import": {
        "type": "event_model",
        "input": "roi_traces",
        "output": "deconvolved_events",
        "why_use_it": "Attaches deconvolved activity estimates for comparison against reviewed event labels.",
        "real_time_profile": {"mode": "streaming", "latency_budget_ms": 1.0, "stateful": True, "closed_loop_candidate": True},
    },
    "heuristic_priority_v1": {
        "type": "candidate_ranking",
        "input": "roi_candidates",
        "output": "ranked_candidates",
        "why_use_it": "Orders candidates for review using transparent feature weights rather than hidden labels.",
        "real_time_profile": {"mode": "streaming", "latency_budget_ms": 1.0, "adaptive": False, "closed_loop_candidate": True},
    },
    "generate_neuron_review_app": {
        "type": "export",
        "input": "ranked_candidates",
        "output": "review_app",
        "why_use_it": "Builds the human review dashboard and exported summary artifacts.",
        "real_time_profile": {"mode": "offline", "latency_budget_ms": None},
    },
}


_PARAMETER_DOCS: dict[str, dict[str, str]] = {
    "source": "Path to the raw movie or frame stack. Keep this relative when possible for reproducibility.",
    "review_data": "Path to an existing review_data.json artifact to import as a baseline run.",
    "sigma_frames": "Temporal high-pass scale in frames. At 100 Hz, convert from seconds rather than copying 5 Hz values directly.",
    "spatial_sigma_px": "Spatial smoothing radius in pixels. Larger values suppress speckle but can merge nearby neurons.",
    "temporal_window_frames": "Temporal window used for event-preserving noise checks. Short windows are safer for sparse fast events.",
    "sigma_px": "Gaussian blur radius in pixels before spatial detection. Use the smallest value that reduces pixel noise.",
    "max_shift_px": "Maximum rigid x/y drift to search per frame. High values are slower and can overfit weak texture.",
    "suite2p_dir": "Folder containing Suite2p outputs such as stat.npy, F.npy, and spks.npy.",
    "pmd_dir": "Folder containing PMD outputs for denoising/import comparison.",
    "traces": "Trace array path used by deconvolution importers.",
    "denoised_video": "Path to a denoised video artifact; keep raw-video provenance attached.",
    "local_radius_px": "Local neighborhood radius for robust z scoring. Should cover background around a soma without swallowing nearby cells.",
    "epsilon": "Small stabilizer added to the denominator to avoid noise blow-ups in low-variance regions.",
    "pfa": "Target false-alarm probability for CFAR-style adaptive thresholds. Lower values are more conservative.",
    "guard_px": "Pixels around the test point excluded from background estimation so the candidate does not train on itself.",
    "training_radius_px": "Outer local background radius used by adaptive CFAR training statistics.",
    "update_alpha": "Streaming update rate for adaptive background statistics. Lower values are slower but more stable.",
    "alpha": "EWMA update rate for online baseline and variance estimates.",
    "threshold_z": "Streaming z-score threshold for candidate activity masks.",
    "event_threshold_z": "Z-score threshold for candidate event calls. Lower values improve recall but increase review burden.",
    "min_area_px": "Smallest accepted component area in pixels. Use microscope resolution and expected soma size to set this.",
    "max_area_px": "Largest accepted component area in pixels. Helps flag merged clusters and broad artifacts.",
    "seed_z": "Higher threshold used to seed connected components from strong evidence peaks.",
    "grow_z": "Lower threshold used to grow components around seeds without swallowing background.",
    "outer_radius_px": "Outer radius of the local background/neuropil ring around an ROI.",
    "neuropil_weight": "Fraction of local background ring signal subtracted from the ROI trace.",
    "kalman_gain": "How quickly the baseline follows slow trace changes. Too high can absorb real calcium events.",
    "spike_gain": "How much positive innovation updates the event model. Use conservatively for sparse events.",
    "array_key": "Key inside an .npz file containing imported deconvolved activity.",
    "local_correlation_weight": "Priority contribution from local spatial/temporal consistency.",
    "event_support_weight": "Priority contribution from event evidence support.",
    "artifact_weight": "Negative priority contribution from artifact-like cues.",
    "include_discovery": "Whether the generated dashboard should include missed-neuron discovery suggestions.",
}


def _stage_metadata(stage_id: str) -> dict[str, Any]:
    metadata = deepcopy(_STAGE_METADATA.get(stage_id, {}))
    realtime = deepcopy(_DEFAULT_REALTIME)
    realtime.update(metadata.get("real_time_profile", {}))
    metadata["real_time_profile"] = realtime
    metadata.setdefault("type", "stage")
    metadata.setdefault("input", "")
    metadata.setdefault("output", "")
    metadata.setdefault("why_use_it", "Use this stage when its output is needed by the following pipeline step.")
    return metadata


def _parameter_docs(stage_id: str, stage: PipelineStage) -> dict[str, dict[str, Any]]:
    docs: dict[str, dict[str, Any]] = {}
    names = set(stage.required_params)
    names.update(dict(stage.default_params or {}))
    names.update(dict(stage.param_ranges or {}))
    for name in sorted(names):
        item: dict[str, Any] = {
            "meaning": _PARAMETER_DOCS.get(name, f"Parameter '{name}' for {stage.label}."),
            "default": deepcopy(dict(stage.default_params or {}).get(name)),
            "required": name in stage.required_params,
            "why": "Tune this parameter with sweeps when candidate recall, artifact burden, or 100 Hz latency changes.",
        }
        param_range = dict(stage.param_ranges or {}).get(name)
        if param_range is not None:
            item["range"] = param_range.as_dict()
        docs[name] = item
    return docs


STAGE_CATALOG: dict[str, PipelineStage] = {
    "source_video_import": PipelineStage(
        stage_id="source_video_import",
        label="Source video import",
        order=10,
        required_params=("source",),
        description="Resolve the source imaging video or frame stack used by later stages.",
    ),
    "review_data_import": PipelineStage(
        stage_id="review_data_import",
        label="Review data import",
        order=10,
        required_params=("review_data",),
        description="Import an existing Neurobench review_data.json artifact.",
    ),
    "temporal_highpass_gaussian": PipelineStage(
        stage_id="temporal_highpass_gaussian",
        label="Temporal high-pass Gaussian",
        order=20,
        default_params={"sigma_frames": 6.0},
        param_ranges={"sigma_frames": ParameterRange(minimum=0.1, maximum=120.0)},
        description="Remove slow temporal baseline drift with a Gaussian high-pass filter.",
    ),
    "event_preserving_noise_suppression": PipelineStage(
        stage_id="event_preserving_noise_suppression",
        label="Event-preserving noise suppression",
        order=30,
        default_params={"spatial_sigma_px": 1.0, "temporal_window_frames": 3},
        param_ranges={
            "spatial_sigma_px": ParameterRange(minimum=0.0, maximum=10.0),
            "temporal_window_frames": ParameterRange(minimum=1, maximum=101),
        },
        description="Suppress noise while retaining localized calcium transients.",
    ),
    "spatial_gaussian": PipelineStage(
        stage_id="spatial_gaussian",
        label="Spatial Gaussian smoothing",
        order=30,
        default_params={"sigma_px": 0.8},
        param_ranges={"sigma_px": ParameterRange(minimum=0.0, maximum=10.0)},
        description="Apply spatial Gaussian smoothing before local filtering or CFAR.",
    ),
    "rigid_shift_estimate": PipelineStage(
        stage_id="rigid_shift_estimate",
        label="Rigid drift estimate",
        order=35,
        default_params={"max_shift_px": 4},
        param_ranges={"max_shift_px": ParameterRange(minimum=1, maximum=50)},
        description="Estimate simple rigid x/y frame drift for QC or registration-aware comparison.",
    ),
    "suite2p_import": PipelineStage(
        stage_id="suite2p_import",
        label="Suite2p import",
        order=40,
        required_params=("suite2p_dir",),
        description="Import Suite2p ROI and trace outputs.",
    ),
    "pmd_import": PipelineStage(
        stage_id="pmd_import",
        label="PMD import",
        order=40,
        required_params=("pmd_dir",),
        description="Import penalized matrix decomposition outputs.",
    ),
    "oasis_import": PipelineStage(
        stage_id="oasis_import",
        label="OASIS import",
        order=40,
        required_params=("traces",),
        description="Import OASIS deconvolution outputs.",
    ),
    "pmd_denoised_video_import": PipelineStage(
        stage_id="pmd_denoised_video_import",
        label="PMD denoised video import",
        order=40,
        required_params=("denoised_video",),
        description="Attach a PMD-denoised video artifact for downstream candidate generation.",
    ),
    "robust_positive_local_z": PipelineStage(
        stage_id="robust_positive_local_z",
        label="Robust positive local-z",
        order=50,
        default_params={"local_radius_px": 11, "epsilon": 1.0},
        param_ranges={
            "local_radius_px": ParameterRange(minimum=1, maximum=101),
            "epsilon": ParameterRange(minimum=0.0, maximum=100.0),
        },
        description="Compute robust positive local z-score evidence from a filtered video.",
    ),
    "gamma_cfar": PipelineStage(
        stage_id="gamma_cfar",
        label="Gamma CFAR",
        order=50,
        default_params={"pfa": 0.001, "guard_px": 2},
        param_ranges={
            "pfa": ParameterRange(minimum=0.0, maximum=1.0),
            "guard_px": ParameterRange(minimum=0, maximum=100),
        },
        description="Apply gamma CFAR thresholding to candidate evidence.",
    ),
    "adaptive_ewma_z": PipelineStage(
        stage_id="adaptive_ewma_z",
        label="Adaptive EWMA z-score",
        order=50,
        default_params={"alpha": 0.02, "threshold_z": 3.0, "epsilon": 1.0},
        param_ranges={
            "alpha": ParameterRange(minimum=0.0001, maximum=1.0),
            "threshold_z": ParameterRange(minimum=0.0, maximum=20.0),
            "epsilon": ParameterRange(minimum=0.0, maximum=100.0),
        },
        description="Maintain streaming per-pixel mean/variance estimates and emit positive z-score candidate masks.",
    ),
    "adaptive_gamma_cfar": PipelineStage(
        stage_id="adaptive_gamma_cfar",
        label="Adaptive Gamma CFAR",
        order=50,
        default_params={"pfa": 0.001, "guard_px": 2, "training_radius_px": 11, "update_alpha": 0.02},
        param_ranges={
            "pfa": ParameterRange(minimum=0.0, maximum=1.0),
            "guard_px": ParameterRange(minimum=0, maximum=100),
            "training_radius_px": ParameterRange(minimum=1, maximum=101),
            "update_alpha": ParameterRange(minimum=0.0001, maximum=1.0),
        },
        description="Plan a streaming CFAR detector with local training statistics and adaptive background updates.",
    ),
    "candidate_event_pipeline": PipelineStage(
        stage_id="candidate_event_pipeline",
        label="Candidate event pipeline",
        order=50,
        default_params={"event_threshold_z": 2.4, "min_area_px": 4},
        param_ranges={
            "event_threshold_z": ParameterRange(minimum=0.0, maximum=20.0),
            "min_area_px": ParameterRange(minimum=1, maximum=100000),
        },
        description="Detect candidate calcium events and ROI discovery suggestions.",
    ),
    "component_filter": PipelineStage(
        stage_id="component_filter",
        label="Component extraction",
        order=55,
        default_params={"seed_z": 2.0, "grow_z": 1.1, "min_area_px": 8, "max_area_px": 260},
        param_ranges={
            "seed_z": ParameterRange(minimum=0.0, maximum=20.0),
            "grow_z": ParameterRange(minimum=0.0, maximum=20.0),
            "min_area_px": ParameterRange(minimum=1, maximum=100000),
            "max_area_px": ParameterRange(minimum=1, maximum=100000),
        },
        description="Extract connected component ROI candidates from evidence maps.",
    ),
    "local_background_ring": PipelineStage(
        stage_id="local_background_ring",
        label="Local background ring",
        order=58,
        default_params={"outer_radius_px": 15, "neuropil_weight": 0.7},
        param_ranges={
            "outer_radius_px": ParameterRange(minimum=1, maximum=1000),
            "neuropil_weight": ParameterRange(minimum=0.0, maximum=5.0),
        },
        description="Extract ROI traces with a local background or neuropil ring.",
    ),
    "trace_event_scoring": PipelineStage(
        stage_id="trace_event_scoring",
        label="Trace event scoring",
        order=60,
        required_params=("event_threshold_z",),
        param_ranges={"event_threshold_z": ParameterRange(minimum=0.0, maximum=20.0)},
        description="Score candidate trace events with a z-threshold.",
    ),
    "robust_kalman_positive_innovation": PipelineStage(
        stage_id="robust_kalman_positive_innovation",
        label="Kalman positive innovation events",
        order=60,
        default_params={"event_threshold_z": 2.4, "kalman_gain": 0.06, "spike_gain": 0.008},
        param_ranges={
            "event_threshold_z": ParameterRange(minimum=0.0, maximum=20.0),
            "kalman_gain": ParameterRange(minimum=0.0, maximum=1.0),
            "spike_gain": ParameterRange(minimum=0.0, maximum=1.0),
        },
        description="Call candidate events from positive innovations over a robust baseline.",
    ),
    "oasis_deconvolution_import": PipelineStage(
        stage_id="oasis_deconvolution_import",
        label="OASIS deconvolution import",
        order=60,
        default_params={"array_key": "spikes"},
        description="Attach OASIS deconvolved traces or event evidence.",
    ),
    "heuristic_priority_v1": PipelineStage(
        stage_id="heuristic_priority_v1",
        label="Heuristic priority ranking",
        order=80,
        default_params={
            "local_correlation_weight": 0.2,
            "event_support_weight": 0.2,
            "artifact_weight": -0.15,
        },
        param_ranges={
            "local_correlation_weight": ParameterRange(minimum=-5.0, maximum=5.0),
            "event_support_weight": ParameterRange(minimum=-5.0, maximum=5.0),
            "artifact_weight": ParameterRange(minimum=-5.0, maximum=5.0),
        },
        description="Rank candidates for human review using transparent feature weights.",
    ),
    "generate_neuron_review_app": PipelineStage(
        stage_id="generate_neuron_review_app",
        label="Generate neuron review app",
        order=70,
        default_params={"include_discovery": True},
        description="Build review_data.json, summary tables, frames, and dashboard assets.",
    ),
}


def catalog_as_dict() -> dict[str, dict[str, Any]]:
    """Return a JSON-serializable copy of the stage catalog."""

    return {stage_id: stage.as_dict() for stage_id, stage in STAGE_CATALOG.items()}


def stage_ids() -> tuple[str, ...]:
    return tuple(STAGE_CATALOG)


def get_stage(stage_id: str) -> PipelineStage:
    try:
        return STAGE_CATALOG[stage_id]
    except KeyError as exc:
        raise ValueError(f"Unknown pipeline stage_id '{stage_id}'.") from exc


def is_structured_pipeline(pipeline: Sequence[Mapping[str, Any]] | None) -> bool:
    """Return True when any step uses the structured pipeline contract."""

    return any("id" in step or "stage_id" in step or "stage" in step for step in (pipeline or []))


def normalize_pipeline(
    pipeline: Sequence[Mapping[str, Any]] | None,
    *,
    require_structured: bool = False,
) -> list[dict[str, Any]]:
    """Validate a pipeline and merge catalog defaults into structured steps.

    Legacy architecture-run steps that only use ``name`` are preserved as-is unless
    ``require_structured`` is set. Structured steps must contain unique ``id``
    values, known ``stage_id`` values, required params, and nondecreasing catalog
    order.
    """

    if pipeline is None:
        if require_structured:
            raise ValueError("Pipeline is required.")
        return []
    if not isinstance(pipeline, Sequence) or isinstance(pipeline, (str, bytes, bytearray)):
        raise ValueError("Pipeline must be an array.")

    steps: list[dict[str, Any]] = []
    for index, step in enumerate(pipeline):
        if not isinstance(step, Mapping):
            raise ValueError(f"Pipeline step at index {index} must be an object.")
        steps.append(dict(step))
    structured = is_structured_pipeline(steps)
    if require_structured and not structured:
        raise ValueError("Pipeline must use structured steps with 'id' and 'stage_id'.")
    if not structured:
        return steps

    seen_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    previous_order: int | None = None
    previous_stage_id = ""
    for index, step in enumerate(steps):
        step_id = step.get("id")
        stage_id = step.get("stage_id", step.get("stage"))
        if not isinstance(step_id, str) or not step_id:
            raise ValueError(f"Pipeline step at index {index} is missing required string 'id'.")
        if step_id in seen_ids:
            raise ValueError(f"Duplicate pipeline step id '{step_id}'.")
        seen_ids.add(step_id)
        if not isinstance(stage_id, str) or not stage_id:
            raise ValueError(f"Pipeline step '{step_id}' is missing required string 'stage_id'.")

        stage = get_stage(stage_id)
        if previous_order is not None and stage.order < previous_order:
            raise ValueError(
                f"Pipeline stage '{stage_id}' is out of order after '{previous_stage_id}'."
            )

        raw_params = step.get("params")
        if raw_params is not None and not isinstance(raw_params, Mapping):
            raise ValueError(f"Pipeline step '{step_id}' params must be an object.")
        params = stage.merged_params(raw_params)
        for required_param in stage.required_params:
            if required_param not in params or params[required_param] is None:
                raise ValueError(f"Pipeline stage '{stage_id}' is missing required param '{required_param}'.")
        for param_name, param_range in dict(stage.param_ranges or {}).items():
            if param_name in params and params[param_name] is not None:
                param_range.validate(stage_id, param_name, params[param_name])

        normalized_step = dict(step)
        normalized_step["stage_id"] = stage_id
        normalized_step["params"] = params
        normalized.append(normalized_step)
        previous_order = stage.order
        previous_stage_id = stage_id
    return normalized


def validate_pipeline(
    pipeline: Sequence[Mapping[str, Any]] | None,
    *,
    require_structured: bool = False,
) -> list[dict[str, Any]]:
    """Validate and normalize a pipeline.

    This is an explicit validation entrypoint; it returns the same normalized
    structure as ``normalize_pipeline`` so callers can keep merged defaults.
    """

    return normalize_pipeline(pipeline, require_structured=require_structured)
