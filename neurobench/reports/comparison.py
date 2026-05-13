"""Run-comparison reports built from MetricsReport payloads."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from neurobench.metrics.run_comparison import candidate_consensus_metrics, metric_winner_table
from neurobench.models.metrics import MetricsReport
from neurobench.reports.render import _format_value, _label


DEFAULT_COMPARISON_METRICS = (
    ("object_level", "object_recall", "higher"),
    ("object_level", "object_precision", "higher"),
    ("event_level", "event_recall", "higher"),
    ("event_level", "event_precision", "higher"),
    ("pixel_level", "truncated_auc", "higher"),
    ("runtime", "duration_seconds", "lower"),
)


def build_run_comparison_report(
    reports: Sequence[MetricsReport | Mapping[str, Any]],
    *,
    metric_specs: Sequence[tuple[str, str, str]] = DEFAULT_COMPARISON_METRICS,
) -> dict[str, Any]:
    """Build a structured comparison from multiple MetricsReport objects."""

    payloads = [_as_payload(report) for report in reports]
    if not payloads:
        raise ValueError("At least one metrics report is required for comparison.")
    dataset_ids = sorted({str(payload.get("dataset_id", "")) for payload in payloads})
    rows = []
    for payload in payloads:
        run_id = _primary_run_id(payload)
        rows.append(
            {
                "metrics_report_id": payload["metrics_report_id"],
                "dataset_id": payload["dataset_id"],
                "run_id": run_id,
                "values": {
                    f"{section}.{metric}": _metric_value(payload, section, metric)
                    for section, metric, _direction in metric_specs
                },
                "warning_count": len(payload.get("warnings") or []),
            }
        )

    winners = metric_winner_table(payloads, metric_specs)["best_by_metric"]
    consensus = candidate_consensus_metrics(payloads)
    return {
        "schema_version": 1,
        "dataset_ids": dataset_ids,
        "run_count": len(payloads),
        "metric_specs": [
            {"section": section, "metric": metric, "direction": direction}
            for section, metric, direction in metric_specs
        ],
        "runs": rows,
        "best_by_metric": winners,
        "candidate_consensus": consensus,
        "warnings": [
            {
                "metrics_report_id": payload["metrics_report_id"],
                "run_id": _primary_run_id(payload),
                "warnings": list(payload.get("warnings") or []),
            }
            for payload in payloads
            if payload.get("warnings")
        ],
    }


def render_run_comparison_markdown(comparison: Mapping[str, Any]) -> str:
    """Render a structured run comparison to Markdown."""

    metric_specs = list(comparison.get("metric_specs") or [])
    lines = [
        "# Neurobench Run Comparison",
        "",
        f"- Dataset IDs: {', '.join(f'`{item}`' for item in comparison.get('dataset_ids', [])) or 'none'}",
        f"- Runs compared: {comparison.get('run_count', 0)}",
        "",
        "## Metric Table",
        "",
    ]
    headers = ["Run"] + [f"{_label(spec['section'])}.{_label(spec['metric'])}" for spec in metric_specs] + ["Warnings"]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in comparison.get("runs", []):
        values = [f"`{row['run_id']}`"]
        for spec in metric_specs:
            key = f"{spec['section']}.{spec['metric']}"
            values.append(_format_value(row.get("values", {}).get(key)))
        values.append(str(row.get("warning_count", 0)))
        lines.append("| " + " | ".join(values) + " |")

    lines.extend(["", "## Best By Metric", ""])
    for key, winner in sorted(dict(comparison.get("best_by_metric") or {}).items()):
        if winner is None:
            lines.append(f"- {_label(key)}: no numeric values")
        else:
            lines.append(f"- {_label(key)}: `{winner['run_id']}` ({_format_value(winner['value'])})")

    consensus = dict(comparison.get("candidate_consensus") or {})
    lines.extend(
        [
            "",
            "## Candidate Consensus",
            "",
            f"- Consensus accepted candidates: {len(consensus.get('consensus_accepted_candidate_ids', []))}",
            f"- Unique accepted candidates: {len(consensus.get('unique_accepted_candidate_ids', []))}",
        ]
    )
    for item in consensus.get("unique_by_run", []):
        lines.append(f"- `{item['run_id']}` unique accepted: {_format_value(item['candidate_ids'])}")

    lines.extend(["", "## Warnings and Limitations", ""])
    warnings = list(comparison.get("warnings") or [])
    if not warnings:
        lines.append("No warnings reported.")
    else:
        for item in warnings:
            lines.append(f"- `{item['run_id']}`: {_format_value(item.get('warnings') or [])}")
    return "\n".join(lines).rstrip() + "\n"


def write_run_comparison_markdown(comparison: Mapping[str, Any], path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_run_comparison_markdown(comparison), encoding="utf-8")
    return out


def _as_payload(report: MetricsReport | Mapping[str, Any]) -> dict[str, Any]:
    return report.to_dict() if isinstance(report, MetricsReport) else MetricsReport.from_dict(report).to_dict()


def _primary_run_id(payload: Mapping[str, Any]) -> str:
    run_ids = list(payload.get("run_ids") or [])
    return str(run_ids[0]) if run_ids else str(payload.get("metrics_report_id", "run"))


def _metric_value(payload: Mapping[str, Any], section: str, metric: str) -> float | int | None:
    value = ((payload.get("metrics") or {}).get(section) or {}).get(metric)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
