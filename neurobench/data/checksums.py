"""Input checksum helpers for reproducible dataset and pipeline runs."""
from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


DEFAULT_INPUT_PATH_KEYS = frozenset(
    {
        "raw_video",
        "video",
        "behavior",
        "stimulus",
        "metadata",
        "labels",
        "ground_truth",
        "mask",
        "roi_mask",
        "annotation_source",
    }
)

OUTPUT_LIKE_PATH_KEYS = frozenset(
    {
        "app_dir",
        "review_data",
        "annotations",
        "output",
        "output_root",
        "report",
        "exports",
    }
)


def sha256_path(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Compute a SHA-256 digest for a file path."""
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Input file does not exist: {file_path}")
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checksum_file(path: str | Path, *, path_id: str | None = None, base_dir: str | Path | None = None) -> dict[str, Any]:
    """Return a reproducibility record for one input file."""
    file_path = Path(path).expanduser()
    if not file_path.is_file():
        raise FileNotFoundError(f"Input file does not exist: {file_path}")
    resolved = file_path.resolve()
    if base_dir is not None:
        try:
            display_path = resolved.relative_to(Path(base_dir).expanduser().resolve()).as_posix()
        except ValueError:
            display_path = str(resolved)
    else:
        display_path = str(file_path)
    record: dict[str, Any] = {
        "path": display_path,
        "sha256": sha256_path(resolved),
        "size_bytes": resolved.stat().st_size,
    }
    if path_id is not None:
        record["path_id"] = path_id
    return record


def input_path_keys(paths: Mapping[str, Any], *, path_keys: Iterable[str] | None = None) -> list[str]:
    """Select manifest path keys that should be treated as immutable inputs."""
    if path_keys is not None:
        return [str(key) for key in path_keys]
    selected: list[str] = []
    for key in paths:
        normalized = str(key)
        lower = normalized.lower()
        if lower in OUTPUT_LIKE_PATH_KEYS:
            continue
        if lower in DEFAULT_INPUT_PATH_KEYS or lower.startswith("input_") or lower.endswith("_input"):
            selected.append(normalized)
    return selected


def resolve_manifest_path(value: str | Path, *, base_dir: str | Path | None = None) -> Path:
    """Resolve a manifest path relative to the manifest directory when needed."""
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (Path(base_dir).expanduser() / path if base_dir is not None else path).resolve()


def dataset_input_checksums(
    manifest: Mapping[str, Any] | Any,
    *,
    manifest_path: str | Path | None = None,
    path_keys: Iterable[str] | None = None,
    require_exists: bool = True,
) -> list[dict[str, Any]]:
    """Compute checksum records for input-like paths in a dataset manifest.

    Missing optional inputs are skipped when ``require_exists`` is false. This
    keeps validation usable for portable example manifests whose raw data is not
    checked into the repository.
    """
    payload = manifest.to_dict() if hasattr(manifest, "to_dict") and callable(manifest.to_dict) else manifest
    if not isinstance(payload, Mapping):
        raise TypeError("dataset manifest checksum input must be a mapping or provide to_dict()")
    paths = payload.get("paths") or {}
    if not isinstance(paths, Mapping):
        raise TypeError("dataset manifest paths must be a mapping")
    base_dir = Path(payload.get("_manifest_dir") or Path(manifest_path).expanduser().parent) if manifest_path else payload.get("_manifest_dir")
    records: list[dict[str, Any]] = []
    for key in input_path_keys(paths, path_keys=path_keys):
        value = paths.get(key)
        if value is None:
            continue
        path = resolve_manifest_path(value, base_dir=base_dir)
        if not path.exists() and not require_exists:
            continue
        records.append(checksum_file(path, path_id=key, base_dir=base_dir))
    return records
