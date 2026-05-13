"""Latency reporting for realtime frame-processing experiments."""
from __future__ import annotations

from statistics import median
from time import perf_counter
from typing import Any, Mapping

from neurobench.realtime.stream import FrameSource


def run_latency_report(
    source: FrameSource,
    stage: Any,
    *,
    frame_budget_ms: float | None = None,
    max_frames: int | None = None,
    warmup_frames: int = 0,
) -> dict[str, Any]:
    """Run a streaming stage over a frame source and summarize latency.

    The stage must expose ``process_frame(frame, frame_index, timestamp_sec)``.
    Optional ``initialize`` and ``finalize`` methods are called when present.
    """
    if frame_budget_ms is not None and frame_budget_ms <= 0:
        raise ValueError("frame_budget_ms must be positive when provided.")
    if max_frames is not None and max_frames <= 0:
        raise ValueError("max_frames must be positive when provided.")
    if warmup_frames < 0:
        raise ValueError("warmup_frames must be non-negative.")
    if not hasattr(stage, "process_frame"):
        raise TypeError("stage must provide process_frame(frame, frame_index, timestamp_sec).")

    if hasattr(stage, "initialize"):
        stage.initialize(None)

    samples_ms: list[float] = []
    processed = 0
    output_counts: list[int] = []
    for packet in source:
        if max_frames is not None and processed >= max_frames:
            break
        start = perf_counter()
        result = stage.process_frame(packet.frame, packet.frame_index, packet.timestamp_sec)
        elapsed_ms = (perf_counter() - start) * 1000.0
        if processed >= warmup_frames:
            samples_ms.append(float(elapsed_ms))
            if isinstance(result, Mapping) and "candidate_pixel_count" in result:
                output_counts.append(int(result["candidate_pixel_count"]))
        processed += 1

    final_payload = stage.finalize() if hasattr(stage, "finalize") else {}
    latency = latency_summary(samples_ms, frame_budget_ms=frame_budget_ms)
    return {
        "schema_version": 1,
        "source": source.metadata(),
        "stage": stage.__class__.__name__,
        "processed_frames": int(processed),
        "warmup_frames": int(warmup_frames),
        "frame_budget_ms": frame_budget_ms,
        "latency": latency,
        "output": {
            "max_candidate_pixel_count": max(output_counts) if output_counts else 0,
            "mean_candidate_pixel_count": float(sum(output_counts) / len(output_counts)) if output_counts else 0.0,
        },
        "stage_final": dict(final_payload) if isinstance(final_payload, Mapping) else {},
    }


def latency_summary(samples_ms: list[float], *, frame_budget_ms: float | None = None) -> dict[str, Any]:
    """Summarize latency samples with budget pass/fail metadata."""
    if not samples_ms:
        return {
            "frames": 0,
            "p50_ms": None,
            "p95_ms": None,
            "p99_ms": None,
            "max_ms": None,
            "mean_ms": None,
            "over_budget_frames": 0,
            "budget_pass": True,
        }
    over_budget = sum(1 for sample in samples_ms if frame_budget_ms is not None and sample > frame_budget_ms)
    return {
        "frames": len(samples_ms),
        "p50_ms": float(median(samples_ms)),
        "p95_ms": _percentile(samples_ms, 0.95),
        "p99_ms": _percentile(samples_ms, 0.99),
        "max_ms": float(max(samples_ms)),
        "mean_ms": float(sum(samples_ms) / len(samples_ms)),
        "over_budget_frames": int(over_budget),
        "budget_pass": over_budget == 0,
    }


def render_latency_report_markdown(report: Mapping[str, Any]) -> str:
    """Render a compact Markdown latency report."""
    source = dict(report.get("source") or {})
    latency = dict(report.get("latency") or {})
    lines = [
        "# Realtime Latency Report",
        "",
        f"- Stage: `{report.get('stage', '')}`",
        f"- Source: `{source.get('source_id', '')}`",
        f"- Frames processed: {report.get('processed_frames', 0)}",
        f"- Frame rate: {source.get('frame_rate_hz', 'n/a')} Hz",
        f"- Frame budget: {_fmt(report.get('frame_budget_ms'))} ms",
        "",
        "## Latency",
        "",
        f"- P50: {_fmt(latency.get('p50_ms'))} ms",
        f"- P95: {_fmt(latency.get('p95_ms'))} ms",
        f"- P99: {_fmt(latency.get('p99_ms'))} ms",
        f"- Max: {_fmt(latency.get('max_ms'))} ms",
        f"- Over-budget frames: {latency.get('over_budget_frames', 0)}",
        f"- Budget pass: `{latency.get('budget_pass', True)}`",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(float(value) for value in values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * q)))
    return float(ordered[index])


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.4g}"
    except (TypeError, ValueError):
        return "n/a"
