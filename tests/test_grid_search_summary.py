from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class _AnalysisStub:
    def __init__(self, calls):
        self.calls = calls

    def find_top_k_models(self, results, k):
        self.calls.append(("top", len(results), k))
        return [dict(results[0], rank_kind="top")]

    def find_balanced_operating_points(self, results, k, fppi_normalization_max):
        self.calls.append(("balanced", len(results), k, fppi_normalization_max))
        return [dict(results[-1], rank_kind="balanced")]


class _GeneratorsStub:
    def __init__(self, calls):
        self.calls = calls

    def save_top_models_summary(self, models, output_dir):
        self.calls.append(("save_top", models[0]["rank_kind"], Path(output_dir).name))

    def save_balanced_summary(self, models, output_dir):
        self.calls.append(("save_balanced", models[0]["rank_kind"], Path(output_dir).name))


class _PlottersStub:
    def __init__(self, calls):
        self.calls = calls

    def plot_range_truncated_froc(self, results, top_models, truncation_limit, output_dir):
        self.calls.append(("froc", len(results), top_models[0]["rank_kind"], truncation_limit, Path(output_dir).name))

    def plot_youden_vs_fppi(self, balanced, truncation_limit, output_dir):
        self.calls.append(("youden", balanced[0]["rank_kind"], truncation_limit, Path(output_dir).name))


class GridSearchSummaryTests(unittest.TestCase):
    def test_group_results_by_family_and_tags_are_stable(self):
        from reporting.grid_search_summary import family_tag, group_results_by_family

        results = [
            {"params": {"varied_param": {"filter_type": "gamma"}}},
            {"params": {"varied_param": {"filter_type": "kalman_mcc"}}},
            {"params": {"varied_param": {"filter_type": "gamma"}}},
        ]

        grouped = group_results_by_family(results)

        self.assertEqual(set(grouped), {"gamma", "kalman_mcc"})
        self.assertEqual(len(grouped["gamma"]), 2)
        self.assertEqual(family_tag("gamma"), "Gamma")
        self.assertEqual(family_tag("kalman_mcc"), "KalmanMCC")
        self.assertEqual(family_tag("custom"), "custom")

    def test_ranked_model_summary_helper_preserves_output_names(self):
        from reporting.grid_search_summary import write_ranked_model_summaries

        calls = []
        results = [
            {"params": {"varied_param": {"filter_type": "gamma"}}, "score": 1},
            {"params": {"varied_param": {"filter_type": "gamma"}}, "score": 2},
        ]

        def report_callback(models, category, output_dir):
            calls.append(("report", models[0]["rank_kind"], category, Path(output_dir).name))

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "Gamma"
            summaries = write_ranked_model_summaries(
                results=results,
                output_dir=out,
                category_prefix="Gamma",
                analysis_module=_AnalysisStub(calls),
                generators_module=_GeneratorsStub(calls),
                plotters_module=_PlottersStub(calls),
                report_callback=report_callback,
                top_k=4,
                fppi_limit=30.0,
            )

            self.assertTrue(out.exists())

        self.assertEqual(summaries["top_models"][0]["rank_kind"], "top")
        self.assertEqual(summaries["balanced"][0]["rank_kind"], "balanced")
        self.assertIn(("report", "top", "Gamma_Top_100_TPR", "Gamma"), calls)
        self.assertIn(("report", "balanced", "Gamma_Top_Balanced", "Gamma"), calls)
        self.assertIn(("save_top", "top", "Gamma"), calls)
        self.assertIn(("save_balanced", "balanced", "Gamma"), calls)
        self.assertIn(("froc", 2, "top", 30.0, "Gamma"), calls)
        self.assertIn(("youden", "balanced", 30.0, "Gamma"), calls)
        self.assertIn(("balanced", 2, 4, 30.0), calls)


if __name__ == "__main__":
    unittest.main()
