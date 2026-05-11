# Neuron Annotation Workbench

The neuron annotation workbench is a local browser tool for reviewing neuron
ROI candidates and candidate firing events from calcium-imaging videos. It is
designed as a high-convenience annotation surface: large video review, trace
inspection, ROI/event labels, notes, keyboard shortcuts, and autosave.

For the current cropped resting-video result and an algorithm-first explanation
of the waveforms, thresholds, and yellow event markers, see
[RESTING_VIDEO_ALGORITHM_BRIEF.md](RESTING_VIDEO_ALGORITHM_BRIEF.md).

## What It Reviews

The current workbench consumes `review_data.json`, generated from:

1. The raw TIFF video.
2. A robust positive z-score stack.
3. Stable ROI candidates built from aggregate spatial/temporal evidence.
4. ROI traces with local background correction.
5. Trace-level robust Kalman baseline estimates and positive innovation event
   calls.

The default calcium-video output is written under:

```bash
Outputs/NeuronReview/calcium_video_2/app/
```

Generated outputs and scientific input data are not intended to be committed to
git.

## Generate The Review Data

Run the Fiji/Groovy generator after the upstream high-pass and candidate
pipeline outputs exist:

```bash
fiji --headless --run '/home/jibby2k1/CNEL/State Analysis (Fish)/Separable-Gamma-CFAR/tools/generate_neuron_review_app.groovy'
```

This writes:

- `review_data.json`: video metadata, ROI footprints, traces, and event data
- `roi_summary.tsv`: compact ROI summary table
- `discovery_suggestions.tsv`: candidate missed-neuron suggestions from
  uncovered evidence maps
- `evidence/*.png`: projection and discovery maps for coverage auditing
- `frames/frame_###.png`: browser-friendly video frames
- `parameters.txt`: generation parameters

## Build The Workbench UI

The v2 workbench builder is stdlib-only Python. It reads the generated
`review_data.json` and writes `index.html`, `workbench.css`, and
`workbench.js`:

```bash
python3 tools/build_neuron_workbench_v2.py
```

The builder also accepts explicit paths or a dataset manifest:

```bash
python3 tools/build_neuron_workbench_v2.py \
  --dataset-manifest examples/dataset_manifest.example.json
```

Useful explicit arguments:

- `--app-dir`: output directory containing `index.html` and autosaved
  `annotations.json`
- `--review-data`: source `review_data.json`
- `--dataset-manifest`: dataset metadata and standard paths
- `--architecture-runs`: optional standardized run comparison manifest

The builder writes `architecture_runs.json` into the app directory, so the
local server can expose the attached architecture metadata alongside
`annotations.json`.

Static dashboard code now lives in `neurobench/workbench/assets/`. The builder
copies those tracked assets into the app directory, which makes UI changes much
easier to review than editing large embedded Python strings.

The v1 builder configures and exports a static/local browser workbench. It does
not execute image-processing pipelines in the browser. Pipeline runs still
happen through Fiji/Groovy, Python, or imported external-tool outputs; the
browser consumes the resulting JSON, manifests, frames, evidence maps, and
autosaved annotations.

## Process A New Dataset

Use a dataset manifest when cycling through multiple TIFF videos. For example,
to process `calcium_rest_cropped.tif` with the current Fiji/Groovy pipeline:

```bash
python3 tools/create_dataset_manifest.py \
  --out Outputs/Manifests/calcium_rest_cropped.dataset.json \
  --dataset-id calcium_rest_cropped \
  --raw-video "Inputs/050126/050126/calcium_rest_cropped.tif" \
  --app-dir Outputs/NeuronReview/calcium_rest_cropped/app \
  --frame-rate-hz 5.0 \
  --pixel-size-microns 0.5
```

```bash
python3 tools/run_neuron_review_pipeline.py \
  --dataset-manifest Outputs/Manifests/calcium_rest_cropped.dataset.json \
  --fiji /home/jibby2k1/.local/bin/fiji
```

The runner executes high-pass filtering, event-preserving denoising, candidate
generation, temporal scoring, review-data generation, the v2 workbench build,
and the multi-dataset index build. Use `--dry-run` to print the exact commands
without running Fiji.

## Run With Autosave

Use the local server for persistent annotation saving:

```bash
python3 tools/serve_neuron_workbench.py --port 8765
```

Then open:

```text
http://127.0.0.1:8765/
```

The server supports:

- `GET /`: workbench app
- `GET /annotations.json`: current annotation state
- `GET /architecture_runs.json`: attached architecture-run metadata
- `PUT /annotations.json`: autosave endpoint

Writes are atomic: the server writes a temporary JSON file and then replaces
`annotations.json`.

For a multi-dataset workbench index, serve the review root instead:

```bash
python3 tools/serve_neuron_workbench.py \
  --root-dir Outputs/NeuronReview \
  --port 8765
```

Then `/` shows all processed dataset dashboards, and autosave writes only to
safe per-dataset files under `*/app/annotations.json` or
`*/app/architecture_runs.json`.

## Review Layout

The Review page is organized for repeated ROI triage:

- the primary video panel remains the spatial reference for frame playback,
  ROI overlays, and discovery overlays
- the trace panel stays adjacent to the selected ROI workflow so candidate
  events can be checked against frame context
- the ROI/event controls, labels, queues, filters, and notes are grouped into
  review sections instead of one long control stack
- secondary review sections are collapsible so a reviewer can keep high-use
  labeling controls visible while hiding lower-frequency panels such as
  discovery, advanced scoring, or audit details
- collapse state is a workflow preference, not an annotation label

The reorganization should not change the saved scientific meaning of
`annotations.json`; it only makes the same review operations easier to scan and
use during long labeling sessions.

## Annotation Files

`annotations.json` stores:

- ROI labels: accept, reject, unsure, hidden/deleted
- ROI notes
- v3 ROI fields: neuron state, trace quality, control readiness, artifact
  class, identity group, and needs-action flag
- Event labels: accept, reject, unsure
- Event notes
- v3 event fields: event state, event type, and timing quality
- Discovery suggestion labels: promoted, missed neuron, artifact, unsure
- Artifact classes such as vessel/static structure, impulse noise, border
  artifact, saturation/bright blob, or uncertain artifact
- Promoted missed-neuron footprints copied from discovery suggestions
- Intent-first virtual ROI merges in `virtualRois`, with source ROI IDs and
  identity-group metadata
- Review-session action counts for lightweight workflow auditing
- Review settings such as thresholds, display settings, and queue mode

The browser also keeps a localStorage backup. If the app is opened directly as
a file instead of through the server, export TSVs before closing the browser.

## Keyboard Shortcuts

- `Space`: play/pause
- Left/right arrows: previous/next frame
- `j` / `k`: next/previous ROI in the active queue
- `n` / `p`: next/previous event in the selected ROI
- `a`: accept selected ROI
- `r`: reject selected ROI
- `u`: mark selected ROI unsure
- `e`: accept selected event
- `x`: reject selected event
- `f`: fullscreen video panel

## Export

The workbench exports three TSVs:

- ROI annotations: one row per ROI with label, notes, footprint metadata, and
  event count
- Event annotations: one row per candidate event with ROI ID, frame, label,
  amplitude, and z score
- Discovery annotations: one row per missed-neuron suggestion with promotion,
  artifact, notes, score, and provenance fields
- Full JSON: migrated v3 annotation state, including review settings

Use these exports as the bridge into downstream inverse-dynamics analysis.

For an inverse-dynamics-ready trace/event table:

```bash
python3 tools/export_inverse_dynamics.py \
  --review-data Outputs/NeuronReview/calcium_video_2/app/review_data.json \
  --annotations Outputs/NeuronReview/calcium_video_2/app/annotations.json \
  --out-dir Outputs/NeuronReview/calcium_video_2/inverse_dynamics
```

For file-based exports outside the browser, use:

```bash
python3 tools/export_annotations.py \
  --review-data Outputs/NeuronReview/calcium_video_2/app/review_data.json \
  --annotations Outputs/NeuronReview/calcium_video_2/app/annotations.json \
  --out-dir Outputs/NeuronReview/calcium_video_2/exports
```

For review-burden and annotation-count summaries:

```bash
python3 tools/compute_annotation_metrics.py \
  --review-data Outputs/NeuronReview/calcium_video_2/app/review_data.json \
  --annotations Outputs/NeuronReview/calcium_video_2/app/annotations.json \
  --out Outputs/NeuronReview/calcium_video_2/annotation_metrics.json
```

## Discovery Mode

Discovery mode is meant to address missed neurons. It adds evidence maps and
candidate suggestions that are not already covered by the current ROI set.

Available evidence maps include:

- raw mean projection
- raw max projection
- raw temporal standard deviation
- robust-z max projection
- peak-count projection
- uncovered robust-z score
- local contrast proxy
- local temporal correlation
- event-support map
- combined discovery score

Use the evidence-map overlay to inspect regions where the video has strong
signal but no accepted ROI. Suggestions can be promoted, marked as missed
neurons, marked as artifacts, or left unsure. Promoted suggestions are saved in
`annotations.json`; they become part of the review record and can be used to
tune the next candidate-generation pass.

New review-data builds also attach transparent scoring fields to ROIs and
suggestions: priority score, local correlation, event support, trace SNR,
background correlation, compactness, and artifact risk. The queue can sort by
these fields, but the scores are only review guidance, not ground truth.

## Architecture Lab

The same generated app now includes an Architecture Lab page at
`#architecture`. It displays standardized architecture-run metadata: run ID,
parameters, ROI/event/suggestion counts, evidence maps, and artifact paths.

The current review output is automatically represented as a baseline run. To
write an explicit run manifest:

```bash
python3 tools/build_architecture_run.py \
  --review-data Outputs/NeuronReview/calcium_video_2/app/review_data.json \
  --out Outputs/ArchitectureRuns/calcium_video_2/architecture_runs.json
```

When two or more runs are attached, Architecture Lab provides Run A / Run B
selectors and a comparison table for candidate totals, accepted/control-ready
counts, and review-burden metrics.

Use `tools/merge_architecture_runs.py` to combine separate method outputs into
one manifest for comparison.

Architecture Lab also includes a Build mode for configuring planned run
manifests. Build mode is a planning/export surface: it captures dataset
references, proposed pipeline options, output locations, and run metadata so the
configuration can be saved or handed to command-line tooling. In v1 it does not
run Fiji, Python, Suite2p, CaImAn, PMD, OASIS, or any other pipeline inside the
browser.

Planned pipeline manifests should be treated as requested or proposed work
until a real run artifact exists. Once a pipeline has actually executed, attach
its produced architecture-run manifest to compare it with the current baseline.

## Metrics/Audit

The generated app also includes a Metrics/Audit page at `#metrics`. It
summarizes live annotation progress from the current browser/server state:

- ROI, event, and discovery suggestion labels
- trace-quality labels
- control-readiness labels
- candidate burden, such as candidates per accepted ROI/event

Use this page during review sessions to see whether labeling is converging or
whether the candidate generator is creating too much review burden.

The Review queue also includes v3-specific filters for needs-action ROIs,
control-ready ROIs, problematic traces, priority score, local correlation,
event support, trace SNR, and artifact risk.

## Dataset QC

The generated app includes a Dataset QC page at `#qc`. It audits lightweight
video and candidate-set properties such as ROI size, trace noise, event density,
discovery burden, artifact cues, and evidence-map thumbnails.

If `pixel_size_microns` is present in the dataset manifest, the QC page also
reports equivalent ROI diameters in microns. Without that manifest field,
physical-size checks are intentionally disabled.

## Selected ROI Context

The Review page includes a selected-ROI context panel beneath the trace:

- a cropped view around the selected ROI
- the ROI footprint overlaid on the crop
- equivalent ROI diameter in pixels and microns when pixel size is known
- peak score, trace noise, and event count
- priority score, local correlation, event support, background correlation,
  trace SNR, and artifact risk
- an event-centered cropped filmstrip from roughly `t-5` to `t+10`

Use this panel to decide whether a yellow event marker corresponds to a compact
local fluorescence change, shared background motion, or impulse/static artifact.

The Selected ROI Context panel is part of the Review layout rather than a modal
or hover-only affordance. It should remain reachable by keyboard navigation,
expose text labels for the selected ROI and metrics, preserve visible focus
state for controls, and provide non-color cues for event/ROI status wherever
possible. The crop and filmstrip are visual evidence; the adjacent metric text
is the accessible summary that should be used in testing and screen-reader
review.

## Intent-First ROI Editing

The Review page supports shift/ctrl/cmd multi-select in the ROI list or overlay.
Selected ROIs can be assigned the same `identity_group`, marked with a shared
`needs_action`, or saved as a virtual merge. Virtual merges are stored only in
`annotations.json`; the source `review_data.json` footprints remain unchanged.

## Troubleshooting

- If autosave is not active, confirm the page URL starts with
  `http://127.0.0.1:8765/`.
- If the video does not appear, regenerate the frame PNGs with
  `generate_neuron_review_app.groovy`.
- If the ROI list is empty, check queue filters such as minimum area, minimum
  events, or hidden/deleted view.
- If discovery suggestions look too broad, treat them as audit regions rather
  than final ROIs; mark artifacts and promote only visually plausible neurons.
- If annotations appear stale, inspect
  `Outputs/NeuronReview/calcium_video_2/app/annotations.json`.
