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
        self.assertIn('id="architecturePresetGallery"', html)
        self.assertIn('id="componentLibrary"', html)
        self.assertIn('value="adaptive_cfar"', html)
        self.assertIn('value="artifact_suppression"', html)
        self.assertIn('value="high_recall_discovery"', html)
        self.assertIn("Advanced Manifest Preview", html)
        self.assertIn('value="strongNeuron"', html)
        self.assertIn('value="needsEventReview"', html)
        self.assertIn('value="annotationBatch"', html)
        self.assertIn('id="guidedPanel"', html)
        self.assertIn('id="reportPage"', html)
        self.assertIn('href="#report"', html)
        self.assertIn('id="activeRunSelect"', html)
        self.assertIn('id="runGeneratePanel"', html)
        self.assertIn('id="generationBackend"', html)
        self.assertIn('id="previewRunViewBtn"', html)
        self.assertIn('id="unlockGenerationBtn"', html)
        self.assertIn('href="#process"', html)
        self.assertIn("Process Lab", html)
        self.assertIn("Generate View", html)

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
        self.assertIn("nextAnnotationBatch", js)
        self.assertIn("Recommended Next Annotation Batch", js)
        self.assertIn("tuning_ready", js)
        self.assertIn("guidedTasks", js)
        self.assertIn("renderGuidedPanel", js)
        self.assertIn("renderReviewReport", js)
        self.assertIn("ARCHITECTURE_PRESETS", js)
        self.assertIn("renderComponentLibrary", js)
        self.assertIn("renderArchitecturePresets", js)
        self.assertIn("availabilityBadge", js)
        self.assertIn("expected_qc_outputs", js)
        self.assertIn("qcRunSelect", js)
        self.assertIn("qcFrameSlider", js)
        self.assertIn("renderQcStageTimeline", js)
        self.assertIn("updateQcFrameView", js)
        self.assertIn("hash === 'process'", js)
        self.assertIn("renderParameterExperiments", js)
        self.assertIn("artifactReasonsForRoi", js)
        self.assertIn("rebaseReviewDataAssets", js)
        self.assertIn("activeRunId", js)
        self.assertIn("materializeRunAnnotations", js)
        self.assertIn("loadReviewForRun", js)
        self.assertIn("generationCommandForRun", js)
        self.assertIn("qcStageGrid", js)
        self.assertIn("intermediateArtifactsForRun", js)
        self.assertIn("apiUrl", js)
        self.assertIn("startGenerationJob", js)
        self.assertIn("generationHeaders", js)
        self.assertIn("ownerTokenKey", js)
        self.assertIn("generate-preview", js)
        self.assertIn("pollGenerationJob", js)
        self.assertIn("backendReadiness", js)

    def test_intermediate_export_tool_exposes_manifest_fields(self):
        from pathlib import Path

        script = Path("tools/export_intermediate_frames.py").read_text(encoding="utf-8")
        self.assertIn('"frame_pattern"', script)
        self.assertIn('"media_type": "frame_sequence"', script)
        self.assertIn('"intermediates"', script)


if __name__ == "__main__":
    unittest.main()
