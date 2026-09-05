"""Provenance: which code, model and environment produced a result."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Provenance(BaseModel):
    """Identifies the extractor that produced a signal or event.

    Every stored observation/event carries (or references by ``extractor_id``) one of these
    so that results can be traced back when a model or algorithm is upgraded.
    """

    model_config = ConfigDict(frozen=True)

    extractor_id: str = Field(description="Stable id, e.g. 'face.mediapipe_landmarker'")
    extractor_version: str = Field(description="Version of the Lightman adapter code")
    model_id: str | None = Field(default=None, description="Model registry id, if any")
    model_sha256: str | None = Field(default=None, description="SHA-256 of the model asset")
    runtime: str = Field(description="Execution backend, e.g. 'mediapipe-cpu', 'onnxruntime-cuda'")
    lightman_version: str


class EnvironmentSnapshot(BaseModel):
    """Machine and software environment of an analysis run (for reproducibility)."""

    model_config = ConfigDict(frozen=True)

    os: str
    os_version: str
    machine: str = Field(description="CPU architecture, e.g. arm64 / x86_64")
    cpu: str
    cpu_count: int
    memory_gb: float
    python: str
    accelerators: list[str] = Field(
        default_factory=list, description="Detected accelerators, e.g. ['apple-metal', 'cuda:0']"
    )
    packages: dict[str, str] = Field(
        default_factory=dict, description="Versions of key runtime packages"
    )
