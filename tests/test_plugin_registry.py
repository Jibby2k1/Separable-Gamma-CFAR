from __future__ import annotations

import unittest


class PluginRegistryTests(unittest.TestCase):
    def test_plugin_stage_registers_and_validates_params(self):
        from neurobench.integrations.registry import (
            PluginParameter,
            PluginRegistry,
            PluginStageDefinition,
        )

        registry = PluginRegistry()
        stage = PluginStageDefinition(
            stage_id="example_plugin_detector",
            plugin_id="example_plugin",
            label="Example plugin detector",
            input_artifact="raw_video",
            output_artifact="roi_candidates",
            parameters={
                "threshold_z": PluginParameter(kind="number", required=True, minimum=0.0, maximum=20.0),
                "min_area_px": PluginParameter(kind="integer", default=4, minimum=1),
                "mode": PluginParameter(kind="string", default="balanced", choices=("balanced", "strict")),
            },
        )

        registered = registry.register_stage(stage)
        validated = registry.validate_stage("example_plugin_detector", {"threshold_z": 3.5})

        self.assertIs(registered, stage)
        self.assertEqual(validated, {"threshold_z": 3.5, "min_area_px": 4, "mode": "balanced"})
        self.assertEqual([item.stage_id for item in registry.list_stages()], ["example_plugin_detector"])
        self.assertEqual(registry.as_dict()["stages"][0]["output_artifact"], "roi_candidates")

    def test_plugin_stage_validation_rejects_missing_unknown_and_out_of_range_params(self):
        from neurobench.integrations.registry import (
            PluginParameter,
            PluginRegistry,
            PluginStageDefinition,
        )

        registry = PluginRegistry()
        registry.register_stage(
            PluginStageDefinition(
                stage_id="plugin_stage",
                plugin_id="plugin",
                parameters={"alpha": PluginParameter(kind="number", required=True, minimum=0.0, maximum=1.0)},
            )
        )

        with self.assertRaisesRegex(ValueError, "missing required parameter 'alpha'"):
            registry.validate_stage("plugin_stage", {})
        with self.assertRaisesRegex(ValueError, "unknown parameter"):
            registry.validate_stage("plugin_stage", {"alpha": 0.5, "extra": True})
        with self.assertRaisesRegex(ValueError, "above maximum"):
            registry.validate_stage("plugin_stage", {"alpha": 2.0})

    def test_plugin_registry_rejects_duplicate_stage_id(self):
        from neurobench.integrations.registry import PluginRegistry, PluginStageDefinition

        registry = PluginRegistry()
        registry.register_stage(PluginStageDefinition(stage_id="duplicate_stage", plugin_id="one"))

        with self.assertRaisesRegex(ValueError, "already registered"):
            registry.register_stage(PluginStageDefinition(stage_id="duplicate_stage", plugin_id="two"))

    def test_plugin_importer_registers_lists_and_validates(self):
        from neurobench.integrations.registry import (
            PluginImporterDefinition,
            PluginParameter,
            PluginRegistry,
        )

        registry = PluginRegistry()
        importer = PluginImporterDefinition(
            importer_id="external_trace_import",
            plugin_id="trace_plugin",
            source_format="trace_bundle",
            output_artifact="event_traces",
            parameters={"source": PluginParameter(kind="string", required=True)},
        )

        registry.register_importer(importer)
        validated = registry.validate_importer("external_trace_import", {"source": "traces.npz"})

        self.assertEqual(validated, {"source": "traces.npz"})
        self.assertEqual(registry.list_importers(plugin_id="trace_plugin"), [importer])
        self.assertEqual(registry.as_dict()["importers"][0]["source_format"], "trace_bundle")

    def test_registry_exports_from_integrations_package(self):
        from neurobench.integrations import PluginRegistry, default_plugin_registry

        registry = default_plugin_registry()

        self.assertIsInstance(registry, PluginRegistry)
        self.assertEqual(registry.list_stages(), [])


if __name__ == "__main__":
    unittest.main()
