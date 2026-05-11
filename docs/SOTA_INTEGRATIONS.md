# SOTA Integration Notes

The workbench should integrate external methods as architecture runs rather
than replacing the review workflow.

Recommended order:

1. DeepCAD-RT output importer or runner wrapper
2. PMD output importer
3. Suite2p ROI/trace importer
4. OASIS event model for accepted or candidate traces
5. CaImAn importer
6. FIOLA notes for future online analysis

Each integration should write the same architecture-run schema and keep raw
video visible beside denoised or inferred outputs. Denoised videos and
deconvolved traces should be treated as evidence, not ground truth.

## Real-Time Priority For 100 Hz Samples

For 100 Hz data, the practical closed-loop budget is about 10 ms/frame before
camera, synchronization, and control overhead. Treat integrations as:

- **Closed-loop candidates:** adaptive local-z/CFAR, online background
  correction, robust Kalman positive innovation, OASIS-style online trace
  inference, and eventually FIOLA.
- **Near-real-time or benchmark candidates:** simple rigid motion correction,
  compact component extraction, and lightweight priority scoring.
- **Offline evidence/comparison:** DeepCAD-RT, Suite2p, CaImAn batch outputs,
  PMD denoising, dashboard generation, and nonrigid registration until measured
  otherwise.

Every method proposed for closed-loop use should have a benchmark summary with
p50/p95/p99 latency and the dataset frame rate attached to the architecture-run
metadata before it is considered operational.

## Suite2p Import

Suite2p outputs can be attached as an Architecture Lab run without making
Suite2p a required dependency:

```bash
python3 tools/import_suite2p_run.py \
  --suite2p-dir /path/to/suite2p/plane0 \
  --dataset-id calcium_video_2 \
  --out Outputs/ArchitectureRuns/calcium_video_2/suite2p_architecture_runs.json
```

The importer expects `stat.npy` and optionally reads `F.npy` and `spks.npy` for
trace/frame counts. It emits the standard architecture-run manifest, which can
then be passed to:

```bash
python3 tools/build_neuron_workbench_v2.py \
  --architecture-runs Outputs/ArchitectureRuns/calcium_video_2/suite2p_architecture_runs.json
```

To compare Suite2p against the current pipeline, merge both manifests with
`tools/merge_architecture_runs.py` and build the dashboard from the merged file.

## PMD Denoising Import

PMD denoising should be attached as evidence before it is trusted as a source
of labels. The importer records the denoised movie path and optional dimensions
as an Architecture Lab run:

```bash
python3 tools/import_pmd_run.py \
  --denoised-video Outputs/Denoised/calcium_video_2_pmd.tif \
  --source-video "Inputs/050126/050126/calcium video 2.tif" \
  --dataset-id calcium_video_2 \
  --frame-count 313 \
  --width 512 \
  --height 512 \
  --out Outputs/ArchitectureRuns/calcium_video_2/pmd_architecture_runs.json
```

This is metadata-only by design. It does not require a PMD Python environment
and does not read the video file. Use it to compare a PMD-denoised artifact
against the current raw-video pipeline, then merge it with the baseline or
Suite2p run manifest.

## OASIS Trace Import

OASIS deconvolution outputs can be attached as a run when they are saved as
`.npy` or `.npz` arrays:

```bash
python3 tools/import_oasis_run.py \
  --traces Outputs/OASIS/calcium_video_2_spikes.npz \
  --key spikes \
  --dataset-id calcium_video_2 \
  --out Outputs/ArchitectureRuns/calcium_video_2/oasis_architecture_runs.json
```

The importer reads only the array shape and selected key. It does not yet
replace event labels in the review app. The intended use is to compare OASIS
deconvolved traces against reviewed calcium events and decide whether the event
model is useful before wiring it into the annotation interface.
