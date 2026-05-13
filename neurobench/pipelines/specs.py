"""Stable pipeline-spec hashing helpers."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


_BEHAVIORAL_SPEC_FIELDS = ("pipeline", "parameters", "execution", "sweep")


def canonicalize_for_hash(value: Any) -> Any:
    """Convert a parameter payload into a deterministic JSON-compatible form."""
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return canonicalize_for_hash(value.to_dict())
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, Mapping):
        return {
            str(key): canonicalize_for_hash(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (set, frozenset)):
        items = [canonicalize_for_hash(item) for item in value]
        return sorted(items, key=canonical_json)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [canonicalize_for_hash(item) for item in value]
    if hasattr(value, "tolist") and callable(value.tolist):
        return canonicalize_for_hash(value.tolist())
    if hasattr(value, "item") and callable(value.item):
        return canonicalize_for_hash(value.item())
    return value


def canonical_json(value: Any) -> str:
    """Serialize a payload with stable key order and whitespace."""
    return json.dumps(
        canonicalize_for_hash(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def parameter_hash(parameters: Any) -> str:
    """Return a full SHA-256 digest for a canonicalized parameter payload."""
    encoded = canonical_json(parameters).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def pipeline_spec_parameter_hash(spec: Mapping[str, Any] | Any) -> str:
    """Hash only fields expected to change pipeline behavior.

    Labels, run ids, output paths, artifacts, and summaries are intentionally
    excluded so the same configured computation keeps the same parameter hash
    across repeated runs and alternate output locations.
    """
    payload = spec.to_dict() if hasattr(spec, "to_dict") and callable(spec.to_dict) else spec
    if not isinstance(payload, Mapping):
        raise TypeError("pipeline spec hash input must be a mapping or provide to_dict()")
    behavioral_payload = {field: payload.get(field) for field in _BEHAVIORAL_SPEC_FIELDS if field in payload}
    return parameter_hash(behavioral_payload)
