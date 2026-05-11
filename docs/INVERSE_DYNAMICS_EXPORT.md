# Inverse-Dynamics Export Notes

The current export layer is a preparation step for tail-motion inverse dynamics.
It does not yet align neural activity to behavior, but it records the annotation
fields needed to select cleaner training inputs.

## Current Export

```bash
python3 tools/export_annotations.py \
  --review-data Outputs/NeuronReview/calcium_video_2/app/review_data.json \
  --annotations Outputs/NeuronReview/calcium_video_2/app/annotations.json \
  --out-dir Outputs/NeuronReview/calcium_video_2/exports
```

This writes:

- `annotations_v3.json`
- `accepted_rois.tsv`
- `accepted_events.tsv`

Despite the filenames, the TSVs currently include all reviewed candidates with
their state fields. Downstream scripts should filter for accepted and
control-ready rows.

## Recommended Selection

For inverse-dynamics model inputs, start with ROIs where:

- `cell_state == accepted`
- `trace_quality == good` or `weak`
- `control_ready == yes` or `maybe`
- `artifact_class` is empty or `none`

At 5 Hz, event timing should be treated as frame-level activity evidence, not
exact spike timing.

## Trace/Event Feature Export

Use the inverse-dynamics export when you want one row per ROI/frame and one row
per reviewed event:

```bash
python3 tools/export_inverse_dynamics.py \
  --review-data Outputs/NeuronReview/calcium_video_2/app/review_data.json \
  --annotations Outputs/NeuronReview/calcium_video_2/app/annotations.json \
  --dataset-manifest examples/dataset_manifest.example.json \
  --out-dir Outputs/NeuronReview/calcium_video_2/inverse_dynamics
```

By default, this exports only ROIs marked:

- `cell_state == accepted`
- `trace_quality == good` or `weak`
- `control_ready == yes` or `maybe`
- no artifact class, or artifact class `none`

For early debugging before labels exist, add `--include-pending` to export all
candidate ROIs.

Outputs:

- `control_ready_traces.tsv`: one row per selected ROI per frame
- `event_features.tsv`: one row per candidate event on selected ROIs
- `inverse_dynamics_export_summary.json`: source paths and selected ROI IDs

Trace and event rows include `time_sec`, computed from `frame_rate_hz` in the
review data or dataset manifest. Frame numbers remain 1-based in the TSVs.

When `--dataset-manifest` is supplied, the summary also carries dataset,
behavior, and synchronization metadata. Add tail-motion paths and sync notes to
the manifest before using the export for behavior-aligned inverse dynamics.
Until behavior files are present, the summary reports `alignment.status` as
`not_aligned`.
