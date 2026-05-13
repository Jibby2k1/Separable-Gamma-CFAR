"""Executable stage registry built from the shared pipeline catalog."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from neurobench.pipeline_catalog import catalog_as_dict, get_stage


EXECUTABLE_AVAILABILITIES = frozenset({"implemented"})


@dataclass(frozen=True)
class StageDefinition:
    """Runtime-facing stage metadata normalized from the Architecture Lab catalog."""

    stage_id: str
    label: str
    availability: str
    input_artifact: str
    output_artifact: str
    default_params: Mapping[str, Any]
    required_params: tuple[str, ...]
    description: str = ""

    @property
    def executable(self) -> bool:
        return self.availability in EXECUTABLE_AVAILABILITIES

    def validate_params(self, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Merge defaults and validate stage parameters using the canonical catalog."""
        return get_stage(self.stage_id).merged_params(params)

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "label": self.label,
            "availability": self.availability,
            "executable": self.executable,
            "input_artifact": self.input_artifact,
            "output_artifact": self.output_artifact,
            "default_params": dict(self.default_params),
            "required_params": list(self.required_params),
            "description": self.description,
        }


class StageRegistry:
    """Lookup and validation surface for pipeline execution stages."""

    def __init__(self, stages: Mapping[str, StageDefinition]):
        self._stages = dict(stages)

    @classmethod
    def from_catalog(cls) -> "StageRegistry":
        stages = {
            stage_id: StageDefinition(
                stage_id=stage_id,
                label=str(entry["label"]),
                availability=str(entry["availability"]),
                input_artifact=str(entry.get("input") or ""),
                output_artifact=str(entry.get("output") or ""),
                default_params=dict(entry.get("default_params") or {}),
                required_params=tuple(entry.get("required_params") or ()),
                description=str(entry.get("description") or ""),
            )
            for stage_id, entry in catalog_as_dict().items()
        }
        return cls(stages)

    def get(self, stage_id: str) -> StageDefinition:
        try:
            return self._stages[stage_id]
        except KeyError as exc:
            raise ValueError(f"Unknown pipeline stage_id '{stage_id}'.") from exc

    def list(self, *, executable_only: bool = False) -> list[StageDefinition]:
        stages = sorted(self._stages.values(), key=lambda stage: get_stage(stage.stage_id).order)
        if executable_only:
            return [stage for stage in stages if stage.executable]
        return stages

    def executable_stage_ids(self) -> tuple[str, ...]:
        return tuple(stage.stage_id for stage in self.list(executable_only=True))

    def validate_steps(
        self,
        steps: Sequence[Mapping[str, Any]],
        *,
        require_executable: bool = True,
    ) -> list[dict[str, Any]]:
        validated: list[dict[str, Any]] = []
        for step in steps:
            stage_id = str(step["stage_id"])
            stage = self.get(stage_id)
            if require_executable and not stage.executable:
                raise ValueError(
                    f"Pipeline stage '{stage_id}' is not executable by the local runner "
                    f"(availability={stage.availability})."
                )
            validated_step = dict(step)
            validated_step["params"] = stage.validate_params(step.get("params"))
            validated.append(validated_step)
        return validated


def default_stage_registry() -> StageRegistry:
    return StageRegistry.from_catalog()
