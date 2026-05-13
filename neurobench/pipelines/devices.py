"""Execution device resolution for CPU-first Neurobench pipelines."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


SUPPORTED_DEVICE_REQUESTS = frozenset({"auto", "cpu", "cuda", "gpu"})


@dataclass(frozen=True)
class DeviceSpec:
    """Resolved execution device metadata."""

    requested: str
    resolved: str
    backend: str
    available: bool
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "requested": self.requested,
            "resolved": self.resolved,
            "backend": self.backend,
            "available": self.available,
            "reason": self.reason,
        }


def resolve_device(requested: str | None = None) -> DeviceSpec:
    """Resolve a requested execution device.

    ``auto`` uses CUDA when a supported backend is available and otherwise
    falls back to CPU. Explicit ``cuda``/``gpu`` requests fail clearly when no
    CUDA backend is available.
    """
    request = _normalize_device(requested or "cpu")
    if request == "cpu":
        return DeviceSpec(requested=request, resolved="cpu", backend="numpy", available=True, reason="CPU requested.")

    cuda_backend = _cuda_backend()
    if request == "auto":
        if cuda_backend:
            return DeviceSpec(
                requested=request,
                resolved="cuda",
                backend=cuda_backend,
                available=True,
                reason=f"CUDA available through {cuda_backend}.",
            )
        return DeviceSpec(
            requested=request,
            resolved="cpu",
            backend="numpy",
            available=True,
            reason="No CUDA backend detected; using CPU fallback.",
        )

    if cuda_backend:
        return DeviceSpec(
            requested=request,
            resolved="cuda",
            backend=cuda_backend,
            available=True,
            reason=f"CUDA available through {cuda_backend}.",
        )
    raise RuntimeError("CUDA device requested, but no supported CUDA backend is available.")


def resolve_device_from_spec(spec: Mapping[str, Any], *, override: str | None = None) -> DeviceSpec:
    """Resolve a device from a pipeline spec's ``execution.device`` field."""
    if override is not None:
        return resolve_device(override)
    execution = spec.get("execution") if isinstance(spec, Mapping) else None
    if isinstance(execution, Mapping) and execution.get("device") is not None:
        return resolve_device(str(execution.get("device")))
    return resolve_device("cpu")


def _normalize_device(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized not in SUPPORTED_DEVICE_REQUESTS:
        raise ValueError(f"Unsupported execution device '{value}'. Expected one of: auto, cpu, cuda.")
    return "cuda" if normalized == "gpu" else normalized


def _cuda_backend() -> str:
    """Return the first available CUDA backend name, or an empty string."""
    try:
        import torch  # type: ignore

        if bool(torch.cuda.is_available()):
            return "torch_cuda"
    except Exception:
        pass
    try:
        import cupy  # type: ignore

        if int(cupy.cuda.runtime.getDeviceCount()) > 0:
            return "cupy_cuda"
    except Exception:
        pass
    return ""
