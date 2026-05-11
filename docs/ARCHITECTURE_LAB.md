# Architecture Lab

Architecture Lab is the comparison page inside the neuron workbench. It is
available at:

```text
http://127.0.0.1:8765/#architecture
```

The page consumes standardized architecture-run metadata. A run can represent
the current Fiji/Groovy pipeline, a Python CFAR pipeline, or future imports such
as Suite2p, CaImAn, PMD, OASIS, or denoising models.

Suite2p outputs can be converted with `tools/import_suite2p_run.py`,
PMD-denoised videos can be attached with `tools/import_pmd_run.py`, and OASIS
trace outputs can be attached with `tools/import_oasis_run.py`; see
`docs/SOTA_INTEGRATIONS.md`.

Architecture Lab has two related modes:

- Compare mode reads completed architecture-run manifests and reports candidate
  counts, accepted/control-ready counts, review burden, evidence maps, and
  artifact paths.
- Build mode captures a planned run configuration that can be exported as a
  manifest for command-line execution or later attachment.

Build mode is intentionally not a browser execution engine. In v1, the
workbench can configure, save, and export planned pipeline metadata, but it does
not run Fiji/Groovy, Python, Suite2p, CaImAn, PMD, OASIS, denoising models, or
other compute pipelines in-browser.

## Create A Run Manifest

Convert the current `review_data.json` into a run manifest:

```bash
python3 tools/build_architecture_run.py \
  --review-data Outputs/NeuronReview/calcium_video_2/app/review_data.json \
  --out Outputs/ArchitectureRuns/calcium_video_2/architecture_runs.json
```

Then build the dashboard with:

```bash
python3 tools/build_neuron_workbench_v2.py \
  --architecture-runs Outputs/ArchitectureRuns/calcium_video_2/architecture_runs.json
```

If no run manifest is supplied, the builder creates an in-memory baseline run
from the current review data. The selected or generated architecture-run
manifest is also written into the app directory as `architecture_runs.json`.

## Planned Pipeline Manifests

Planned pipeline manifests describe intended work before a run exists. They
should include enough information to reproduce or launch the run outside the
browser:

- dataset ID and source manifest path
- planned pipeline family, implementation, and version when known
- parameters and preset names that affect ROI/event generation
- expected output locations for `review_data.json`, evidence maps, traces, and
  architecture-run manifests
- status such as `planned`, `exported`, `running`, `completed`, or `failed`
- provenance notes, including who configured the plan and when it was exported

Completed run manifests remain the comparison source of truth. A planned
manifest should not be counted as a completed Architecture Lab run until the
external pipeline has produced artifacts and an architecture-run manifest is
attached.

## Parameter Sweeps

Build mode can also describe small parameter sweeps without running them in the
browser. A sweep is stored as manifest-level `sweep.parameters`, and each
expanded planned run receives a `sweep` assignment with the exact stage,
parameter, and value used. The dashboard and `tools/build_pipeline_run.py` use
the same plan/export-only contract.

Recommended first sweeps are narrow and interpretable:

- event threshold, such as `2.0, 2.4, 2.8`
- component seed/grow thresholds
- minimum and maximum ROI area
- Kalman positive-innovation event threshold

Use the exported planned manifest as a run sheet for Fiji/Python execution, then
merge completed runs back into Architecture Lab for comparison.

## Stage Explanations And 100 Hz Readiness

Build mode reads the shared `neurobench.pipeline_catalog` metadata. Each stage
should include a plain-language description, why it is useful, parameter
explanations, and real-time metadata. The dashboard surfaces this directly in
the stack so parameter choices are not just raw names and numbers.

For upcoming 100 Hz samples, use the real-time badges as planning warnings:

- `streaming` means the stage is intended to work frame-by-frame.
- `adaptive` means the stage maintains or updates local statistics online.
- `offline` or `batch` means the stage is evidence/comparison-only for closed
  loop work unless a streaming runner is added.
- The 100 Hz summary assumes a 10 ms/frame budget when the dataset manifest
  reports `frame_rate_hz: 100.0`.

Benchmark candidate streaming stages with:

```bash
python3 tools/benchmark_pipeline_stage.py \
  --stage adaptive_ewma_z \
  --frame-rate-hz 100 \
  --out Outputs/Benchmarks/adaptive_ewma_z_100hz.json
```

## Merge Multiple Runs

When each method writes its own manifest, merge them before building the
dashboard:

```bash
python3 tools/merge_architecture_runs.py \
  --out Outputs/ArchitectureRuns/calcium_video_2/architecture_runs.json \
  Outputs/ArchitectureRuns/calcium_video_2/current_run.json \
  Outputs/ArchitectureRuns/calcium_video_2/suite2p_architecture_runs.json
```

Duplicate `run_id` values fail by default. Add `--replace` only when the later
manifest should intentionally overwrite an earlier run.

## Current Fields

Architecture Lab v1 shows:

- run ID and label
- dataset ID
- ROI, event, suggestion, and frame counts
- review-data and ROI-summary artifact paths
- evidence-map labels
- paired run comparison for candidate counts, accepted/rejected counts,
  control-ready counts, and review burden when two or more runs are available

The page is intentionally lightweight for now. Side-by-side frame overlays can
be added once multiple real runs exist.

The companion Metrics/Audit page is available at `#metrics` and summarizes the
current annotation burden and review progress.

## Review/Test Planning

For Build mode and pipeline manifests, documentation and manual testing should
verify:

- exported planned manifests never imply that browser-side execution happened
- completed manifests remain visually distinct from planned/exported work
- the baseline run still appears when no explicit manifest is supplied
- Run A / Run B comparison ignores planned-only entries unless they have
  completed run artifacts
- paths exported from Build mode are relative or manifest-driven where possible
  instead of hard-coded to one workstation
