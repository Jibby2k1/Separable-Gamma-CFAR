"""Optional integrations that emit Neurobench architecture-run artifacts."""

from neurobench.integrations.registry import (
    PluginImporterDefinition,
    PluginParameter,
    PluginRegistry,
    PluginStageDefinition,
    default_plugin_registry,
)

__all__ = [
    "PluginImporterDefinition",
    "PluginParameter",
    "PluginRegistry",
    "PluginStageDefinition",
    "default_plugin_registry",
]
