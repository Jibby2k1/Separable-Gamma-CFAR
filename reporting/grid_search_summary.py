"""Shared grid-search summary/report dispatch helpers."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


def family_tag(filter_type: str) -> str:
    """Return the stable output label for a preprocessor family."""
    return {"gamma": "Gamma", "kalman_mcc": "KalmanMCC"}.get(filter_type, filter_type)


def group_results_by_family(all_results: Sequence[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    """Bucket result rows by params.varied_param.filter_type."""
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for result in all_results:
        filter_type = result["params"]["varied_param"]["filter_type"]
        grouped[filter_type].append(result)
    return dict(grouped)


def write_ranked_model_summaries(
    *,
    results: Sequence[Mapping[str, Any]],
    output_dir: Path,
    category_prefix: str,
    analysis_module: Any,
    generators_module: Any,
    plotters_module: Any,
    report_callback: Callable[[list[dict[str, Any]], str, Path], None],
    top_k: int,
    fppi_limit: float,
) -> dict[str, list[dict[str, Any]]]:
    """Write top/balanced CSVs, detailed reports, FROC, and Youden plots."""
    output_dir.mkdir(exist_ok=True)
    top_models = analysis_module.find_top_k_models(results, k=top_k)
    balanced = analysis_module.find_balanced_operating_points(
        results,
        k=top_k,
        fppi_normalization_max=fppi_limit,
    )

    generators_module.save_top_models_summary(top_models, output_dir)
    generators_module.save_balanced_summary(balanced, output_dir)
    report_callback(top_models, f"{category_prefix}_Top_100_TPR", output_dir)
    report_callback(balanced, f"{category_prefix}_Top_Balanced", output_dir)
    plotters_module.plot_range_truncated_froc(results, top_models, fppi_limit, output_dir)
    if hasattr(plotters_module, "plot_youden_vs_fppi"):
        plotters_module.plot_youden_vs_fppi(balanced, fppi_limit, output_dir)

    return {"top_models": top_models, "balanced": balanced}
