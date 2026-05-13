"""Renderers for structured Neurobench reports."""
from __future__ import annotations

from collections.abc import Mapping
from html import escape
from pathlib import Path
from typing import Any

from neurobench.models.metrics import MetricsReport


METRIC_SECTION_TITLES = {
    "pixel_level": "Pixel-Level Metrics",
    "object_level": "Object-Level Metrics",
    "event_level": "Event-Level Metrics",
    "annotation": "Annotation Metrics",
    "runtime": "Runtime Metrics",
}


def render_metrics_report_markdown(report: MetricsReport | Mapping[str, Any]) -> str:
    """Render a structured metrics report to deterministic Markdown."""

    payload = _metrics_report_payload(report)
    lines = [
        f"# Neurobench Metrics Report: {payload['dataset_id']}",
        "",
        "## Report Metadata",
        "",
        f"- Metrics report ID: `{payload['metrics_report_id']}`",
        f"- Dataset ID: `{payload['dataset_id']}`",
        f"- Run IDs: {', '.join(f'`{run_id}`' for run_id in payload.get('run_ids', [])) or 'none'}",
        f"- Created at: `{payload['created_at']}`",
        "",
        "## Metrics",
        "",
    ]

    metrics = dict(payload.get("metrics") or {})
    for section, title in METRIC_SECTION_TITLES.items():
        lines.extend(_render_mapping_section(title, metrics.get(section) or {}))

    extra_metric_sections = {
        key: value for key, value in metrics.items() if key not in METRIC_SECTION_TITLES
    }
    for section, value in sorted(extra_metric_sections.items()):
        lines.extend(_render_mapping_section(_titleize(section), value if isinstance(value, Mapping) else {"value": value}))

    lines.extend(_render_figures(payload.get("figures") or []))
    lines.extend(_render_warnings(payload.get("warnings") or []))
    lines.extend(_render_mapping_section("Reproducibility Appendix", payload.get("provenance") or {}))
    if payload.get("extras"):
        lines.extend(_render_mapping_section("Additional Metadata", payload["extras"]))
    return "\n".join(lines).rstrip() + "\n"


def render_metrics_report_html(report: MetricsReport | Mapping[str, Any]) -> str:
    """Render a structured metrics report to deterministic standalone HTML."""

    payload = _metrics_report_payload(report)
    dataset_id = _html_text(payload["dataset_id"])
    lines = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        f"<title>Neurobench Metrics Report: {dataset_id}</title>",
        "<style>",
        "body { font-family: system-ui, sans-serif; line-height: 1.5; margin: 2rem; color: #1f2933; }",
        "main { max-width: 920px; }",
        "h1, h2, h3 { line-height: 1.2; }",
        "section { margin-block: 1.75rem; }",
        "table { border-collapse: collapse; width: 100%; }",
        "th, td { border: 1px solid #d9e2ec; padding: 0.5rem 0.65rem; text-align: left; vertical-align: top; }",
        "th { background: #f0f4f8; }",
        "code { background: #f0f4f8; border-radius: 0.25rem; padding: 0.05rem 0.2rem; }",
        ".empty { color: #627d98; }",
        "</style>",
        "</head>",
        "<body>",
        "<main>",
        f"<h1>Neurobench Metrics Report: {dataset_id}</h1>",
        '<section aria-labelledby="report-metadata">',
        '<h2 id="report-metadata">Report Metadata</h2>',
        "<ul>",
        f"<li>Metrics report ID: {_html_code(payload['metrics_report_id'])}</li>",
        f"<li>Dataset ID: {_html_code(payload['dataset_id'])}</li>",
        f"<li>Run IDs: {_render_html_run_ids(payload.get('run_ids', []))}</li>",
        f"<li>Created at: {_html_code(payload['created_at'])}</li>",
        "</ul>",
        "</section>",
        '<section aria-labelledby="metrics">',
        '<h2 id="metrics">Metrics</h2>',
    ]

    metrics = dict(payload.get("metrics") or {})
    for section, title in METRIC_SECTION_TITLES.items():
        lines.extend(_render_html_mapping_section(title, metrics.get(section) or {}))

    extra_metric_sections = {
        key: value for key, value in metrics.items() if key not in METRIC_SECTION_TITLES
    }
    for section, value in sorted(extra_metric_sections.items()):
        lines.extend(_render_html_mapping_section(_titleize(section), value if isinstance(value, Mapping) else {"value": value}))

    lines.extend([
        "</section>",
        *_render_html_figures(payload.get("figures") or []),
        *_render_html_warnings(payload.get("warnings") or []),
        *_render_html_mapping_section("Reproducibility Appendix", payload.get("provenance") or {}, heading_level=2),
    ])
    if payload.get("extras"):
        lines.extend(_render_html_mapping_section("Additional Metadata", payload["extras"], heading_level=2))
    lines.extend(["</main>", "</body>", "</html>"])
    return "\n".join(lines).rstrip() + "\n"


def write_metrics_report_markdown(report: MetricsReport | Mapping[str, Any], path: str | Path) -> Path:
    """Write a Markdown metrics report and return the output path."""

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_metrics_report_markdown(report), encoding="utf-8")
    return out


def write_metrics_report_html(report: MetricsReport | Mapping[str, Any], path: str | Path) -> Path:
    """Write an HTML metrics report and return the output path."""

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_metrics_report_html(report), encoding="utf-8")
    return out


def _metrics_report_payload(report: MetricsReport | Mapping[str, Any]) -> dict[str, Any]:
    return report.to_dict() if isinstance(report, MetricsReport) else MetricsReport.from_dict(report).to_dict()


def _render_mapping_section(title: str, values: Mapping[str, Any]) -> list[str]:
    lines = [f"### {title}", ""]
    if not values:
        lines.extend(["No values reported.", ""])
        return lines
    for key, value in sorted(values.items()):
        lines.append(f"- {_label(key)}: {_format_value(value)}")
    lines.append("")
    return lines


def _render_html_mapping_section(title: str, values: Mapping[str, Any], *, heading_level: int = 3) -> list[str]:
    title_text = _html_text(title)
    section_id = _html_attr(_html_id(title))
    lines = [
        f'<section aria-labelledby="{section_id}">',
        f'<h{heading_level} id="{section_id}">{title_text}</h{heading_level}>',
    ]
    if not values:
        lines.extend(['<p class="empty">No values reported.</p>', "</section>"])
        return lines
    lines.extend(["<table>", "<thead><tr><th>Metric</th><th>Value</th></tr></thead>", "<tbody>"])
    for key, value in sorted(values.items()):
        lines.append(f"<tr><th>{_html_text(_label(key))}</th><td>{_format_html_value(value)}</td></tr>")
    lines.extend(["</tbody>", "</table>", "</section>"])
    return lines


def _render_figures(figures: list[Mapping[str, Any]]) -> list[str]:
    lines = ["## Figures", ""]
    if not figures:
        lines.extend(["No figures reported.", ""])
        return lines
    for figure in figures:
        caption = figure.get("caption") or figure.get("kind") or "figure"
        lines.append(f"- `{figure.get('path', '')}`: {caption}")
    lines.append("")
    return lines


def _render_html_figures(figures: list[Mapping[str, Any]]) -> list[str]:
    lines = ['<section aria-labelledby="figures">', '<h2 id="figures">Figures</h2>']
    if not figures:
        lines.extend(['<p class="empty">No figures reported.</p>', "</section>"])
        return lines
    lines.append("<ul>")
    for figure in figures:
        caption = figure.get("caption") or figure.get("kind") or "figure"
        lines.append(f"<li>{_html_code(figure.get('path', ''))}: {_html_text(caption)}</li>")
    lines.extend(["</ul>", "</section>"])
    return lines


def _render_warnings(warnings: list[Any]) -> list[str]:
    lines = ["## Warnings and Limitations", ""]
    if not warnings:
        lines.extend(["No warnings reported.", ""])
        return lines
    for warning in warnings:
        lines.append(f"- {warning}")
    lines.append("")
    return lines


def _render_html_warnings(warnings: list[Any]) -> list[str]:
    lines = ['<section aria-labelledby="warnings-and-limitations">', '<h2 id="warnings-and-limitations">Warnings and Limitations</h2>']
    if not warnings:
        lines.extend(['<p class="empty">No warnings reported.</p>', "</section>"])
        return lines
    lines.append("<ul>")
    for warning in warnings:
        lines.append(f"<li>{_html_text(warning)}</li>")
    lines.extend(["</ul>", "</section>"])
    return lines


def _format_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4g}"
    if isinstance(value, Mapping):
        if not value:
            return "`{}`"
        return "; ".join(f"{_label(key)}={_format_value(val)}" for key, val in sorted(value.items()))
    if isinstance(value, list):
        if not value:
            return "none"
        return ", ".join(_format_value(item) for item in value)
    if isinstance(value, str):
        return f"`{value}`" if _looks_like_path_or_id(value) else value
    return str(value)


def _format_html_value(value: Any) -> str:
    if isinstance(value, float):
        return _html_text(f"{value:.4g}")
    if isinstance(value, Mapping):
        if not value:
            return _html_code("{}")
        return "; ".join(f"{_html_text(_label(key))}={_format_html_value(val)}" for key, val in sorted(value.items()))
    if isinstance(value, list):
        if not value:
            return "none"
        return ", ".join(_format_html_value(item) for item in value)
    if isinstance(value, str):
        return _html_code(value) if _looks_like_path_or_id(value) else _html_text(value)
    return _html_text(value)


def _label(value: Any) -> str:
    return str(value).replace("_", " ")


def _titleize(value: str) -> str:
    return _label(value).title()


def _looks_like_path_or_id(value: str) -> bool:
    return "/" in value or "\\" in value or value.endswith(".json") or value.endswith(".md") or value.startswith("run_")


def _render_html_run_ids(run_ids: list[str]) -> str:
    if not run_ids:
        return "none"
    return ", ".join(_html_code(run_id) for run_id in run_ids)


def _html_text(value: Any) -> str:
    return escape(str(value), quote=False)


def _html_attr(value: Any) -> str:
    return escape(str(value), quote=True)


def _html_code(value: Any) -> str:
    return f"<code>{_html_text(value)}</code>"


def _html_id(value: str) -> str:
    identifier = "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")
    return "-".join(part for part in identifier.split("-") if part) or "section"
