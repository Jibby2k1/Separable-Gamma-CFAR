from __future__ import annotations

import unittest


class WorkbenchStructureTests(unittest.TestCase):
    def test_template_contains_accessible_roi_context_and_pipeline_builder(self):
        from tools import build_neuron_workbench_v2 as builder

        html = builder.HTML_TEMPLATE
        self.assertIn("reviewEvidenceGrid", html)
        self.assertIn('aria-labelledby="selectedRoiContextHeading"', html)
        self.assertIn('id="selectedRoiContextHeading"', html)
        self.assertIn('id="architectureBuildPanel"', html)
        self.assertIn('id="pipelineStagePalette"', html)
        self.assertIn('id="pipelineJsonPreview"', html)
        self.assertIn("Advanced Manifest Preview", html)
        self.assertIn('value="strongNeuron"', html)
        self.assertIn('value="needsEventReview"', html)

    def test_asset_js_uses_keyboardable_filmstrip_and_planned_run_builder(self):
        from pathlib import Path

        js = Path("neurobench/workbench/assets/workbench.js").read_text(encoding="utf-8")
        self.assertIn("document.createElement('button')", js)
        self.assertIn("aria-current", js)
        self.assertIn("execution: {status: 'planned'}", js)
        self.assertIn("architecture_runs.json", js)
        self.assertIn("stageIssueBadge", js)
        self.assertIn("plannedManifest", js)
        self.assertIn("sweepFactors", js)
        self.assertIn("triage_queue_counts", js)
        self.assertIn("buildStageCatalog(data.pipelineCatalog)", js)
        self.assertIn("pipelineRealtimeSummary", js)
        self.assertIn("parameterHelp", js)


if __name__ == "__main__":
    unittest.main()
