"""Report rendering helpers."""

from neurobench.reports.builder import build_metrics_report_from_pipeline_run, build_metrics_report_from_pipeline_runs
from neurobench.reports.comparison import (
    build_run_comparison_report,
    render_run_comparison_markdown,
    write_run_comparison_markdown,
)
from neurobench.reports.render import render_metrics_report_markdown, write_metrics_report_markdown

__all__ = [
    "build_metrics_report_from_pipeline_run",
    "build_metrics_report_from_pipeline_runs",
    "build_run_comparison_report",
    "render_metrics_report_markdown",
    "render_run_comparison_markdown",
    "write_metrics_report_markdown",
    "write_run_comparison_markdown",
]
