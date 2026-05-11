# Metrics/Audit

The workbench Metrics/Audit page is available at:

```text
http://127.0.0.1:8765/#metrics
```

It summarizes the live annotation state from `annotations.json` and browser
memory. It is intended for review management, not final scientific evaluation.

Current summaries include:

- ROI state counts
- event state counts
- discovery suggestion outcomes
- trace-quality labels
- control-readiness labels
- triage category counts and queue IDs
- candidates per accepted ROI
- candidate events per accepted event

The same summary can be generated from files:

```bash
python3 tools/compute_annotation_metrics.py \
  --review-data Outputs/NeuronReview/calcium_video_2/app/review_data.json \
  --annotations Outputs/NeuronReview/calcium_video_2/app/annotations.json \
  --out Outputs/NeuronReview/calcium_video_2/annotation_metrics.json
```

High candidate-per-accepted counts indicate that the detector is still too
permissive or that the review queue needs better ranking. Low control-ready
counts indicate that accepted neurons are not yet clean enough for downstream
inverse-dynamics work.

## Triage Categories

File-generated annotation metrics include `triage_categories` and
`triage_queue_counts`. These fields are helper summaries for review queues, not
new scientific labels. They are derived from existing `annotations.json` and
`review_data.json` fields:

- `strong_neuron`: accepted ROI with good trace quality, yes/maybe control
  readiness, no artifact class, and low artifact score
- `possible_missed_neuron`: discovery suggestion marked missed or promoted
- `artifact_like`: ROI or suggestion with an artifact class/cue/state, or high
  artifact score
- `merged_cluster`: ROI marked for merge, ROI sharing an identity group with
  another ROI, or a virtual merge ROI
- `weak_trace`: ROI with weak, noisy, or unusable trace quality
- `needs_event_review`: unlabeled/unsure event, weak event, ambiguous timing, or
  slow-transient timing
