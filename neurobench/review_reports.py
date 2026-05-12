"""Shareable review-session report helpers."""
from __future__ import annotations

from typing import Any, Mapping

from neurobench.annotation_metrics import compute_annotation_summary
from neurobench.review_batches import build_annotation_batch


def build_review_report(review_data: Mapping[str, Any], annotations: Mapping[str, Any] | None) -> dict[str, Any]:
    summary = compute_annotation_summary(review_data, annotations or {})
    batch = summary.get("next_annotation_batch") or build_annotation_batch(review_data, annotations)
    dataset_id = review_data.get("dataset", {}).get("dataset_id") or review_data.get("video", {}).get("name") or "dataset"
    progress = summary["review_progress"]
    recommendations = []
    if not progress["tuning_ready"]:
        recommendations.append(
            f"Review at least {progress['tuning_ready_targets']['reviewed_rois']} ROIs and "
            f"{progress['tuning_ready_targets']['reviewed_events']} events before treating parameter comparisons as tuning data."
        )
    if summary["suggestion_states"]["unlabeled"]:
        recommendations.append("Audit discovery suggestions to estimate missed-neuron burden.")
    if summary["roi_states"]["accepted"] and summary["control_ready"]["yes"] == 0:
        recommendations.append("Mark trace quality and control readiness for accepted ROIs before inverse-dynamics export.")
    if not recommendations:
        recommendations.append("Generate a review sweep pack and compare candidate stability across parameter presets.")
    return {
        "dataset_id": dataset_id,
        "summary": summary,
        "top_next_rois": batch.get("rois", [])[:10],
        "top_next_events": batch.get("events", [])[:10],
        "top_next_suggestions": batch.get("suggestions", [])[:10],
        "recommendations": recommendations,
    }


def render_review_report_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    progress = summary["review_progress"]
    lines = [
        f"# Neuron Workbench Review Report: {report['dataset_id']}",
        "",
        "## Review Status",
        "",
        f"- Candidate ROIs: {summary['roi_count']}",
        f"- Candidate events: {summary['event_count']}",
        f"- Discovery suggestions: {summary['suggestion_count']}",
        f"- Reviewed ROIs: {progress['reviewed_rois']} ({progress['roi_review_fraction']:.0%})",
        f"- Reviewed events: {progress['reviewed_events']} ({progress['event_review_fraction']:.0%})",
        f"- Tuning-ready: {'yes' if progress['tuning_ready'] else 'no'}",
        "",
        "## Accepted Outputs",
        "",
        f"- Accepted ROIs: {summary['roi_states']['accepted']}",
        f"- Accepted events: {summary['event_states']['accepted']}",
        f"- Control-ready yes/maybe: {summary['control_ready']['yes']} / {summary['control_ready']['maybe']}",
        "",
        "## Recommended Next Review",
        "",
    ]
    for roi in report.get("top_next_rois", [])[:5]:
        lines.append(f"- ROI {roi['roi_id']}: score {roi['score']}, {', '.join(roi.get('reasons', []))}")
    lines.extend(["", "## Recommendations", ""])
    for item in report.get("recommendations", []):
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"
