"""Artifact store and deterministic run-layout helpers."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any

from neurobench.models.artifacts import ArtifactRecord
from neurobench.models.pipeline import PipelineRun


RUN_LAYOUT_DIRS = ("logs", "artifacts", "workbench", "exports")


def sha256_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Compute a SHA-256 digest for a file."""
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Artifact file does not exist: {file_path}")
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_run_layout(run_root: str | Path, pipeline_run: PipelineRun | None = None) -> dict[str, Path]:
    """Create the standard run root layout and optionally write pipeline_run.json."""
    root = Path(run_root)
    root.mkdir(parents=True, exist_ok=True)
    paths = {"root": root, "pipeline_run": root / "pipeline_run.json"}
    for name in RUN_LAYOUT_DIRS:
        path = root / name
        path.mkdir(parents=True, exist_ok=True)
        paths[name] = path
    if pipeline_run is not None:
        pipeline_run.write_json(paths["pipeline_run"])
    return paths


def _rel_or_abs(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


class ArtifactStore:
    """Register produced artifacts into a pipeline-run manifest."""

    def __init__(self, run_root: str | Path, pipeline_run: PipelineRun):
        self.run_root = Path(run_root)
        self.pipeline_run = pipeline_run
        self.paths = create_run_layout(self.run_root, pipeline_run)

    def artifact_path(self, *parts: str) -> Path:
        """Return a path under run_root/artifacts, creating parent directories."""
        path = self.paths["artifacts"].joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def register_file(
        self,
        path: str | Path,
        *,
        artifact_id: str,
        kind: str,
        producer_stage: str,
        schema: str | None = None,
        summary: dict[str, Any] | None = None,
        created_at: str | None = None,
    ) -> ArtifactRecord:
        """Register an existing file as an ArtifactRecord and update pipeline_run.json."""
        file_path = Path(path)
        if not file_path.is_file():
            raise FileNotFoundError(f"Artifact file does not exist: {file_path}")
        record = ArtifactRecord(
            schema_version=1,
            artifact_id=artifact_id,
            kind=kind,
            path=_rel_or_abs(file_path, self.run_root),
            schema=schema,
            producer_stage=producer_stage,
            created_at=created_at or datetime.now(timezone.utc).isoformat(),
            sha256=sha256_file(file_path),
            summary=dict(summary or {}),
        )
        record.validate()
        self.pipeline_run.artifacts = [
            item for item in self.pipeline_run.artifacts if getattr(item, "artifact_id", None) != artifact_id
        ]
        self.pipeline_run.artifacts.append(record)
        self.write_manifest()
        return record

    def write_manifest(self) -> Path:
        """Write the current pipeline_run.json manifest."""
        path = self.paths["pipeline_run"]
        self.pipeline_run.write_json(path)
        return path
