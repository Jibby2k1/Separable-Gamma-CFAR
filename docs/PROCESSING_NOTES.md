# Processing Notes

This repository now has two complementary workflows:

- the original Python grid-search pipeline for Gamma/Kalman-MCC filtering and
  CFAR evaluation
- the Fiji/Groovy neuron-review workflow for practical inspection, ROI review,
  trace denoising, and event annotation

## Current Fiji/Groovy Workflow

The current calcium-video workflow uses the following scripts in order:

1. `tools/temporal_highpass_gaussian.ijm`
   - subtracts a temporal Gaussian background from the raw TIFF
   - writes signed float high-pass stacks for several temporal scales
2. `tools/event_preserving_noise_suppression.groovy`
   - applies median correction, local positive z scoring, and support filters
   - useful as an exploratory baseline
3. `tools/candidate_event_pipeline.groovy`
   - builds permissive spatial candidates using robust local z scores
   - outputs masks, labels, and component tables
4. `tools/temporal_candidate_scoring.groovy`
   - scores candidate components using raw trace support, high-pass support,
     nearby-frame support, and collapse penalties
5. `tools/generate_neuron_review_app.groovy`
   - turns aggregate evidence into stable ROI candidates
   - writes evidence maps for missed-neuron discovery
   - ranks uncovered candidate suggestions by combined evidence
   - extracts raw and local-background-corrected traces
   - applies trace-level robust Kalman baseline estimation
   - writes browser-ready review data
6. `tools/build_neuron_workbench_v2.py`
   - builds the v2 annotation workbench from `review_data.json`
7. `tools/serve_neuron_workbench.py`
   - serves the workbench locally and autosaves annotations

## Denoising Policy

The recommended default is trace-level denoising rather than pixel-video
denoising. Pixel-level smoothing can blur sparse firing events or turn impulse
noise into plausible-looking structure. The workbench therefore:

- finds stable ROI candidates first
- extracts each ROI trace from the raw video
- subtracts a local background/neuropil ring trace
- computes corrected `dF/F`
- estimates a slow baseline with a robust Kalman-style update
- calls candidate firing events from positive innovations

This keeps the sparse event signal visible while still suppressing slow drift
and baseline fluctuations.

## Data And Git Hygiene

Scientific input files and generated review outputs can be large and should
stay outside git:

- `Inputs/*.tif`, nested TIFFs, extracted input folders, and zip files are
  ignored.
- `Outputs/` is ignored.
- Commit scripts, documentation, and reusable source code only.

If a data file is already tracked, do not remove or restore it as part of a
tooling/documentation commit unless that is the explicit goal of the commit.

## Review-Driven Iteration

The intended loop is:

1. Generate candidate ROIs and events.
2. Review in the workbench.
3. Export ROI and event annotations.
4. Use accepted/rejected labels to tune ROI generation, trace denoising, and
   event thresholds.
5. Repeat until accepted ROIs are stable and event calls are usable for the
   inverse-dynamics workflow.

High-impact future robustness work:

- motion/drift correction before ROI extraction
- stronger local-correlation evidence maps
- uncertainty-ranked review queues
- ROI split/merge and footprint brush editing
- side-by-side comparison of trace denoisers and event models

## Missed-Neuron Discovery

The workbench now separates ROI review from coverage auditing. Coverage auditing
uses evidence maps and “uncovered” suggestions to show signal that is not
explained by the current ROI set.

The generator writes browser-ready evidence maps under:

```bash
Outputs/NeuronReview/calcium_video_2/app/evidence/
```

The current discovery maps are intentionally lightweight:

- raw mean, max, and temporal standard deviation projections
- robust-z max projection
- z-threshold peak-count projection
- uncovered robust-z score after masking near existing ROIs
- local contrast proxy
- combined discovery score

Suggestions are not treated as final truth. They are review targets with
provenance and artifact cues. The user can promote likely missed neurons or mark
regions as artifacts. Those labels should feed the next tuning pass.
