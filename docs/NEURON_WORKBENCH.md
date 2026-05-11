# Neuron Annotation Workbench

The neuron annotation workbench is a local browser tool for reviewing neuron
ROI candidates and candidate firing events from calcium-imaging videos. It is
designed as a high-convenience annotation surface: large video review, trace
inspection, ROI/event labels, notes, keyboard shortcuts, and autosave.

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
- `PUT /annotations.json`: autosave endpoint

Writes are atomic: the server writes a temporary JSON file and then replaces
`annotations.json`.

## Annotation Files

`annotations.json` stores:

- ROI labels: accept, reject, unsure, hidden/deleted
- ROI notes
- Event labels: accept, reject, unsure
- Event notes
- Discovery suggestion labels: promoted, missed neuron, artifact, unsure
- Artifact classes such as vessel/static structure, impulse noise, border
  artifact, saturation/bright blob, or uncertain artifact
- Promoted missed-neuron footprints copied from discovery suggestions
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

The workbench exports two TSVs:

- ROI annotations: one row per ROI with label, notes, footprint metadata, and
  event count
- Event annotations: one row per candidate event with ROI ID, frame, label,
  amplitude, and z score
- Discovery annotations: one row per missed-neuron suggestion with promotion,
  artifact, notes, score, and provenance fields

Use these exports as the bridge into downstream inverse-dynamics analysis.

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
- combined discovery score

Use the evidence-map overlay to inspect regions where the video has strong
signal but no accepted ROI. Suggestions can be promoted, marked as missed
neurons, marked as artifacts, or left unsure. Promoted suggestions are saved in
`annotations.json`; they become part of the review record and can be used to
tune the next candidate-generation pass.

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
