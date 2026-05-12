# Annotation Schema

`annotations.json` now migrates to schema version 3. The migration preserves
existing review labels while adding fields needed for inverse-dynamics and
future model training.

## ROI Fields

Each ROI annotation may include:

- `state`: legacy UI label, one of `accept`, `reject`, `unsure`, or empty
- `cell_state`: canonical state, one of `accepted`, `rejected`, `unsure`, or
  empty
- `trace_quality`: `good`, `weak`, `noisy`, `unusable`, or empty
- `control_ready`: `yes`, `maybe`, `no`, or empty
- `artifact_class`: free artifact/category label
- `identity_group`: optional grouping for duplicate/split/merged identities
- `needs_action`: review/edit flag such as `split_needed` or `redraw_needed`
- `notes`
- `deleted`

## Virtual ROI Fields

Intent-first edits that combine multiple source ROIs are stored in
`virtualRois`. A virtual merge may include:

- `id`: virtual ROI ID such as `VM_4_7`
- `roi_kind`: `virtual_merge`
- `source_roi_ids`: source ROI IDs included in the merge
- `identity_group`: shared neuron identity/group label
- label fields such as `cell_state`, `trace_quality`, `control_ready`,
  `artifact_class`, and `notes`

Virtual ROIs do not rewrite source footprints in `review_data.json`. They are
annotation-layer instructions for downstream export and future rebuilds.

## Event Fields

Each event annotation may include:

- `state`: legacy UI label
- `event_state`: canonical state, one of `accepted`, `rejected`, `unsure`, or
  empty
- `event_type`: clear, weak, slow, artifact, or future labels
- `timing_quality`: `clear_frame`, `ambiguous`, `slow_transient`, or empty
- `notes`

## Migration

The browser and `neurobench.annotations.migrate_annotations_v3()` both map
legacy labels automatically:

```text
accept -> accepted
reject -> rejected
unsure -> unsure
```

Use `tools/export_annotations.py` to write a migrated `annotations_v3.json` plus
ROI and event TSV files.

## Run-Scoped Labels

The workbench preserves legacy top-level `rois`, `events`, `suggestions`,
`promotedRois`, and `virtualRois` as the active working copy. It also mirrors
those maps under `runs[run_id]` so labels from one architecture run are not
mixed into another run with different ROI IDs or event calls. Older
single-run `annotations.json` files are migrated into the baseline run when the
dashboard opens.

## Review Stats

The browser records lightweight review-session metadata in `reviewStats`:

- `sessionStartedAt`
- `lastActionAt`
- `actions`, a count of review operations such as ROI accept/reject, event
  labels, suggestion labels, and v3 field changes

These fields are for workflow auditing only. They are not scientific labels.

## Review UI State

Some Review-page behavior is intentionally outside the scientific annotation
schema:

- Review layout section order
- collapsed/expanded state for Review panels
- selected tab or Architecture Lab mode
- transient selected ROI/event IDs
- zoom, playback, and overlay visibility preferences unless explicitly saved in
  review settings

These values may be useful browser preferences, but they should not be treated
as ROI, event, discovery, or virtual-ROI labels.

The Selected ROI Context panel is also derived state. Its crop, footprint
overlay, filmstrip, and metric readouts are computed from `review_data.json`,
current frame/event selection, and dataset metadata such as
`pixel_size_microns`. Accessibility labels and visible text in that panel should
summarize the selected ROI context, but they do not introduce new annotation
fields by themselves.

## Pipeline Build Metadata

Architecture Lab Build mode exports planned pipeline configuration separately
from `annotations.json`. Planned pipeline manifests are not annotation records
and should not be merged into ROI, event, discovery, or virtual-ROI maps.

Use `annotations.json` for reviewer decisions. Use dataset, architecture-run,
or planned-pipeline manifests for data provenance, pipeline parameters,
expected output paths, and run status. In v1, planned-pipeline metadata means
the browser configured or exported a run plan; it does not mean the pipeline was
executed in-browser.
