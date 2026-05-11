# Resting Calcium Video Algorithm Brief

This note summarizes the current local workbench for the cropped resting video,
`calcium_rest_cropped.tif`. The goal is to explain what the current algorithm
does, what the dashboard is showing, and what has or has not been tuned.

## Current Status

The current target is the cropped resting hindbrain video, not the earlier
video that appeared to be non-normal brain function. The workbench is meant to
generate candidate neurons and candidate firing events for human review. It is
not yet a validated detector with measured accuracy.

For `calcium_rest_cropped.tif`, the current run produced:

- video size: `421 x 259` pixels
- frame count: `628`
- frame rate used in the manifest: `5 Hz`
- spatial scale used in the manifest: `0.5 um/pixel`
- stable candidate ROIs: `59`
- missed-neuron discovery suggestions: `62`
- median ROI area: `47 px`
- median equivalent ROI diameter: `7.7 px`, about `3.85 um`

The expected hindbrain neuron diameter discussed for this sample is roughly
`5-10 um`, or `10-20 px` at `0.5 um/pixel`. The current median candidate is
therefore somewhat smaller than the expected full-cell diameter, while the
larger candidates overlap the expected range. This is consistent with the
current detector finding active compact footprints rather than necessarily
recovering full cell bodies.

## What The Algorithm Does

The current workflow handles the nonuniform background by using local and
adaptive measurements rather than one global intensity threshold.

1. **Temporal high-pass filtering**

   The raw video is converted to 32-bit and a slow temporal baseline is
   estimated with Gaussian smoothing over `4`, `6`, and `8` frame scales. The
   high-pass stack is:

   ```text
   high_pass = raw_32bit - temporal_gaussian_baseline
   ```

   At `5 Hz`, these scales correspond to roughly `0.8`, `1.2`, and `1.6`
   seconds. This penalizes changes that are too slow while preserving faster
   fluorescence transients.

2. **Local robust background scoring**

   For each frame, the algorithm removes frame-wide common-mode shifts and then
   computes a local positive z-score using local median/MAD-style background
   statistics. This matters because the background is not uniform and contains
   local clusters. A global threshold would over-detect bright background areas
   and under-detect dimmer regions.

3. **Candidate event components**

   The event proposal stage uses permissive local-z thresholds, then filters
   connected components by shape and size. The current presets are:

   - permissive: seed `1.4`, grow `0.7`, minimum area `3 px`
   - balanced: seed `1.7`, grow `0.9`, minimum area `3 px`
   - strict: seed `2.0`, grow `1.1`, minimum area `4 px`

   Components that are too large, too sparse, or too elongated are rejected as
   likely artifacts or background structure.

4. **Stable ROI formation**

   The review app builds candidate neuron footprints from the aggregate robust-z
   evidence, currently using the `sigma06` robust-z stack. For the resting crop,
   the data-derived projection thresholds were:

   - peak threshold: `4.91`
   - grow floor: `4.65`
   - ROI area range: `8-260 px`
   - maximum ROIs: `90`

   These thresholds are derived from the current video's evidence distribution;
   they are not label-optimized hyperparameters.

5. **Trace extraction and local background correction**

   For each ROI, the app extracts:

   - the raw fluorescence trace inside the ROI
   - a local background ring around the ROI
   - a background-corrected trace using neuropil weight `0.7`
   - a dF/F-like trace for visualization and event scoring

6. **Robust Kalman-style event trace**

   The dashboard estimates a slow baseline for each ROI trace with a robust
   Kalman-style update. The baseline follows normal slow drift, but it follows
   large positive deviations more slowly so transient events are not immediately
   absorbed into the baseline.

   Current trace parameters:

   - event threshold: `z >= 2.4`
   - baseline Kalman gain: `0.060`
   - spike gain: `0.008`
   - negative correction gain: `0.110`

   Candidate events are positive innovations above the estimated baseline. In
   other words, an event is called when the corrected trace rises locally above
   what the slow baseline model expects.

## What The Dashboard Shows

The dashboard is a local annotation and inspection tool. It makes candidate
detections easy to inspect, reject, accept, or mark as uncertain.

In the selected-ROI trace plot:

- **blue waveform**: background-corrected dF/F-like ROI trace
- **gray waveform**: estimated slow Kalman baseline
- **orange waveform**: event z-score derived from positive innovations
- **yellow dots/markers**: candidate event frames where the event z-score is a
  local maximum above the event threshold

The yellow dots are not direct action-potential spikes. Calcium imaging measures
indirect calcium influx, and at `5 Hz` the video cannot reliably distinguish a
single spike from a burst. The markers should be interpreted as candidate
fluorescence transient initiations.

The discovery/evidence maps are meant to catch missed neurons. They highlight
uncovered regions with strong robust-z, temporal activity, local contrast, or
local temporal correlation that are not already explained by the current ROI
set. These are review targets, not ground truth.

## Hyperparameter Status

No label-driven hyperparameter optimization has been done yet. The current
settings are a mix of:

- conservative default values chosen to make the dashboard usable
- data-derived percentile thresholds from the resting video
- hand-tunable dashboard controls for exploratory review

The current result should therefore be treated as a baseline proposal set. The
next step is to review examples, label false positives/likely neurons/missed
neurons, and then use those labels to tune the detector more systematically.

## Important Caveats

- The background is nonuniform and locally clustered, so adaptive local
  background estimates are necessary.
- The current ROI footprints may represent active compact regions rather than
  complete cell bodies.
- Low temporal resolution limits event interpretation; the system detects
  fluorescence transients, not individual spikes.
- The dashboard is local by default. It can be served on the local machine, but
  sharing it online would require an explicit hosting step.

## Suggested Walkthrough For Lab Discussion

For a concise screen-share or slide sequence:

1. Show the resting cropped video with ROI overlay disabled.
2. Enable ROI overlays and explain that these are candidate ROIs, not final
   labels.
3. Select one strong candidate ROI and walk through the blue, gray, orange, and
   yellow trace elements.
4. Show one uncertain or artifact-like region and explain why local background
   and human review are still needed.
5. Open an evidence/discovery map and show how missed-neuron suggestions are
   generated.
6. Close by stating that the current numbers are baseline proposals and that
   the next high-value step is annotation-driven parameter tuning.
