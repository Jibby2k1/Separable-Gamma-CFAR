"""Small registry for external Neurobench plugin stages and importers."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any


PluginEntrypoint = Callable[..., Any] | str
_MISSING = object()
_PARAMETER_KINDS = frozenset({"any", "number", "integer", "string", "boolean"})


@dataclass(frozen=True)
class PluginParameter:
    """Validation rule for one plugin parameter."""

    kind: str = "any"
    required: bool = False
    default: Any = _MISSING
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[Any, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        if self.kind not in _PARAMETER_KINDS:
            raise ValueError(f"Unsupported plugin parameter kind '{self.kind}'.")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("Plugin parameter minimum cannot be greater than maximum.")
        if self.default is not _MISSING:
            self.validate("default", "default", self.default)

    def validate(self, owner_id: str, name: str, value: Any) -> Any:
        if value is _MISSING:
            if self.required:
                raise ValueError(f"Plugin '{owner_id}' is missing required parameter '{name}'.")
            if self.default is not _MISSING:
                return self.default
            return _MISSING

        if self.kind == "number":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"Plugin '{owner_id}' parameter '{name}' must be numeric.")
            numeric = float(value)
            if self.minimum is not None and numeric < self.minimum:
                raise ValueError(f"Plugin '{owner_id}' parameter '{name}'={value} is below minimum {self.minimum}.")
            if self.maximum is not None and numeric > self.maximum:
                raise ValueError(f"Plugin '{owner_id}' parameter '{name}'={value} is above maximum {self.maximum}.")
        elif self.kind == "integer":
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"Plugin '{owner_id}' parameter '{name}' must be an integer.")
            if self.minimum is not None and value < self.minimum:
                raise ValueError(f"Plugin '{owner_id}' parameter '{name}'={value} is below minimum {self.minimum}.")
            if self.maximum is not None and value > self.maximum:
                raise ValueError(f"Plugin '{owner_id}' parameter '{name}'={value} is above maximum {self.maximum}.")
        elif self.kind == "string":
            if not isinstance(value, str):
                raise ValueError(f"Plugin '{owner_id}' parameter '{name}' must be a string.")
        elif self.kind == "boolean":
            if not isinstance(value, bool):
                raise ValueError(f"Plugin '{owner_id}' parameter '{name}' must be a boolean.")

        if self.choices and value not in self.choices:
            choices = ", ".join(repr(choice) for choice in self.choices)
            raise ValueError(f"Plugin '{owner_id}' parameter '{name}' must be one of: {choices}.")
        return value

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind,
            "required": self.required,
            "description": self.description,
        }
        if self.default is not _MISSING:
            payload["default"] = self.default
        if self.minimum is not None:
            payload["minimum"] = self.minimum
        if self.maximum is not None:
            payload["maximum"] = self.maximum
        if self.choices:
            payload["choices"] = list(self.choices)
        return payload


@dataclass(frozen=True)
class PluginStageDefinition:
    """Metadata for a plugin-provided pipeline stage."""

    stage_id: str
    plugin_id: str
    entrypoint: PluginEntrypoint | None = None
    label: str = ""
    description: str = ""
    input_artifact: str = ""
    output_artifact: str = ""
    parameters: Mapping[str, PluginParameter] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_identifier(self.stage_id, "stage_id")
        _validate_identifier(self.plugin_id, "plugin_id")
        for name, parameter in self.parameters.items():
            _validate_identifier(name, "parameter name")
            if not isinstance(parameter, PluginParameter):
                raise TypeError(f"Plugin stage '{self.stage_id}' parameter '{name}' must be a PluginParameter.")

    def validate_params(self, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return _validate_params(self.stage_id, self.parameters, params)

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "plugin_id": self.plugin_id,
            "label": self.label or self.stage_id,
            "description": self.description,
            "input_artifact": self.input_artifact,
            "output_artifact": self.output_artifact,
            "parameters": {name: parameter.as_dict() for name, parameter in self.parameters.items()},
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class PluginImporterDefinition:
    """Metadata for a plugin-provided external output importer."""

    importer_id: str
    plugin_id: str
    entrypoint: PluginEntrypoint | None = None
    label: str = ""
    description: str = ""
    source_format: str = ""
    output_artifact: str = ""
    parameters: Mapping[str, PluginParameter] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_identifier(self.importer_id, "importer_id")
        _validate_identifier(self.plugin_id, "plugin_id")
        for name, parameter in self.parameters.items():
            _validate_identifier(name, "parameter name")
            if not isinstance(parameter, PluginParameter):
                raise TypeError(f"Plugin importer '{self.importer_id}' parameter '{name}' must be a PluginParameter.")

    def validate_params(self, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return _validate_params(self.importer_id, self.parameters, params)

    def as_dict(self) -> dict[str, Any]:
        return {
            "importer_id": self.importer_id,
            "plugin_id": self.plugin_id,
            "label": self.label or self.importer_id,
            "description": self.description,
            "source_format": self.source_format,
            "output_artifact": self.output_artifact,
            "parameters": {name: parameter.as_dict() for name, parameter in self.parameters.items()},
            "metadata": dict(self.metadata),
        }


class PluginRegistry:
    """In-memory registry for plugin stages and importers."""

    def __init__(self) -> None:
        self._stages: dict[str, PluginStageDefinition] = {}
        self._importers: dict[str, PluginImporterDefinition] = {}

    def register_stage(self, stage: PluginStageDefinition) -> PluginStageDefinition:
        if not isinstance(stage, PluginStageDefinition):
            raise TypeError("register_stage expects a PluginStageDefinition.")
        if stage.stage_id in self._stages:
            raise ValueError(f"Plugin stage '{stage.stage_id}' is already registered.")
        self._stages[stage.stage_id] = stage
        return stage

    def register_importer(self, importer: PluginImporterDefinition) -> PluginImporterDefinition:
        if not isinstance(importer, PluginImporterDefinition):
            raise TypeError("register_importer expects a PluginImporterDefinition.")
        if importer.importer_id in self._importers:
            raise ValueError(f"Plugin importer '{importer.importer_id}' is already registered.")
        self._importers[importer.importer_id] = importer
        return importer

    def get_stage(self, stage_id: str) -> PluginStageDefinition:
        try:
            return self._stages[stage_id]
        except KeyError as exc:
            raise ValueError(f"Unknown plugin stage '{stage_id}'.") from exc

    def get_importer(self, importer_id: str) -> PluginImporterDefinition:
        try:
            return self._importers[importer_id]
        except KeyError as exc:
            raise ValueError(f"Unknown plugin importer '{importer_id}'.") from exc

    def list_stages(self, *, plugin_id: str | None = None) -> list[PluginStageDefinition]:
        stages = sorted(self._stages.values(), key=lambda stage: stage.stage_id)
        if plugin_id is None:
            return stages
        return [stage for stage in stages if stage.plugin_id == plugin_id]

    def list_importers(self, *, plugin_id: str | None = None) -> list[PluginImporterDefinition]:
        importers = sorted(self._importers.values(), key=lambda importer: importer.importer_id)
        if plugin_id is None:
            return importers
        return [importer for importer in importers if importer.plugin_id == plugin_id]

    def validate_stage(self, stage_id: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self.get_stage(stage_id).validate_params(params)

    def validate_importer(self, importer_id: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self.get_importer(importer_id).validate_params(params)

    def as_dict(self) -> dict[str, Any]:
        return {
            "stages": [stage.as_dict() for stage in self.list_stages()],
            "importers": [importer.as_dict() for importer in self.list_importers()],
        }


def default_plugin_registry() -> PluginRegistry:
    """Return an empty plugin registry ready for local registration."""

    return PluginRegistry()


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Plugin {field_name} must be a non-empty string.")


def _validate_params(
    owner_id: str,
    specs: Mapping[str, PluginParameter],
    params: Mapping[str, Any] | None,
) -> dict[str, Any]:
    provided = dict(params or {})
    unknown = sorted(set(provided) - set(specs))
    if unknown:
        raise ValueError(f"Plugin '{owner_id}' received unknown parameter(s): {', '.join(unknown)}.")

    validated: dict[str, Any] = {}
    for name, spec in specs.items():
        value = spec.validate(owner_id, name, provided.get(name, _MISSING))
        if value is not _MISSING:
            validated[name] = value
    return validated
