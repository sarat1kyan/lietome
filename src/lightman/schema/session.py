"""Session-level manifest written alongside analysis outputs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from lightman.schema.media import MediaInfo
from lightman.schema.provenance import EnvironmentSnapshot, Provenance


class OutputArtifact(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    kind: str = Field(description="'json' | 'parquet' | 'html' | 'png'")
    size_bytes: int
    sha256: str


class QualitySummary(BaseModel):
    """Aggregate signal-quality figures for the whole session."""

    model_config = ConfigDict(frozen=True)

    frames_total: int
    frames_decoded: int
    frames_with_face: int
    face_coverage: float = Field(ge=0.0, le=1.0, description="frames_with_face / frames_decoded")
    mean_face_quality: float | None = Field(default=None, ge=0.0, le=1.0)
    baseline_quality: float = Field(ge=0.0, le=1.0)
    baseline_window_us: tuple[int, int] | None = None
    notes: list[str] = Field(default_factory=list, description="Human-readable quality caveats")


class AnalysisManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = 1
    session_id: str
    subject_ids: list[str]
    created_utc: str
    lightman_version: str
    media: MediaInfo
    config: dict[str, Any] = Field(description="Effective configuration snapshot")
    environment: EnvironmentSnapshot
    provenance: list[Provenance]
    quality: QualitySummary
    outputs: list[OutputArtifact]
    timing_ms: dict[str, float] = Field(default_factory=dict, description="Stage wall times")
    disclaimer: str
