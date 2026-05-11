"""Dataset and architecture-run manifest helpers."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).expanduser().open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: str | Path, data: Mapping[str, Any]) -> None:
    out = Path(path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resolve_path(value: str | Path | None, *, base_dir: Path | None = None) -> Path | None:
    if value is None:
        return None
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    base = base_dir or project_root()
    candidate = base / path
    if candidate.exists():
        return candidate.resolve()
    return (project_root() / path).resolve()


def load_dataset_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path).expanduser().resolve()
    manifest = load_json(manifest_path)
    manifest["_manifest_path"] = str(manifest_path)
    manifest["_manifest_dir"] = str(manifest_path.parent)
    return manifest


def manifest_path(manifest: Mapping[str, Any], key: str) -> Path | None:
    paths = manifest.get("paths", {})
    if key not in paths:
        return None
    base_dir = Path(manifest.get("_manifest_dir", project_root()))
    return resolve_path(paths[key], base_dir=base_dir)


def default_calcium_video_2_manifest() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "dataset_id": "calcium_video_2",
        "name": "calcium video 2.tif",
        "modality": "light_sheet_calcium",
        "indicator": "GCaMP6f",
        "frame_rate_hz": 5.0,
        "pixel_size_microns": 0.5,
        "paths": {
            "raw_video": "Inputs/050126/050126/calcium video 2.tif",
            "app_dir": "Outputs/NeuronReview/calcium_video_2/app",
            "review_data": "Outputs/NeuronReview/calcium_video_2/app/review_data.json",
            "annotations": "Outputs/NeuronReview/calcium_video_2/app/annotations.json",
        },
    }
