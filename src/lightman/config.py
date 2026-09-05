"""Typed configuration (TOML on disk, pydantic in memory).

Sections mirror pipeline stages. Secrets never live here; Lightman currently needs none.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from lightman.core.errors import ConfigError
from lightman.media.limits import MediaLimits


class VideoConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    target_fps: float | None = Field(
        default=None, gt=0, description="Time-based subsampling rate; None = every frame"
    )
    max_faces: int = Field(default=1, ge=1, le=8, description="V0.1 analyzes the first face only")
    min_face_detection_confidence: float = Field(default=0.5, ge=0, le=1)
    min_face_presence_confidence: float = Field(default=0.5, ge=0, le=1)
    min_tracking_confidence: float = Field(default=0.5, ge=0, le=1)


class BaselineConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: str = Field(default="leading_window", pattern="^(leading_window)$")
    window_s: float = Field(default=30.0, gt=0, description="Calibration window length")
    min_quality: float = Field(default=0.5, ge=0, le=1, description="Frame quality gate")
    min_samples: int = Field(default=60, ge=5, description="Below this, baseline is low quality")
    good_samples: int = Field(default=600, ge=5, description="At/above this, sample-size term = 1")


class EventsConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    z_enter: float = Field(default=3.0, gt=0, description="|robust z| to open an event")
    z_exit: float = Field(default=2.0, gt=0, description="|robust z| to close (hysteresis)")
    min_duration_ms: int = Field(default=120, ge=0)
    merge_gap_ms: int = Field(default=200, ge=0)
    min_frame_quality: float = Field(default=0.4, ge=0, le=1)
    warmup_ms: int = Field(
        default=300,
        ge=0,
        description="Ignore events starting before this: face trackers need a few frames to settle",
    )
    signals: list[str] = Field(
        default_factory=lambda: [
            "head.yaw_deg",
            "head.pitch_deg",
            "head.roll_deg",
            "eye.aspect_ratio_mean",
            "blendshape.browDownLeft",
            "blendshape.browDownRight",
            "blendshape.browInnerUp",
            "blendshape.mouthPressLeft",
            "blendshape.mouthPressRight",
            "blendshape.jawOpen",
            "blendshape.eyeSquintLeft",
            "blendshape.eyeSquintRight",
        ]
    )
    blink_ear_threshold: float = Field(default=0.21, gt=0, description="EAR closed threshold")
    blink_min_ms: int = Field(default=50, ge=0)
    blink_max_ms: int = Field(default=500, ge=0)


class StorageConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    store_landmarks: bool = Field(default=False, description="Persist 478x3 landmarks per frame")
    write_report: bool = True
    event_thumbnails: bool = Field(default=True, description="Small PNG crops at event peaks")
    thumbnail_max_px: int = Field(default=256, ge=32, le=1024)


class PrivacyConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    anonymous_subject_ids: bool = True
    retain_media_copy: bool = Field(default=False, description="Never copy input media by default")
    persist_source_path: bool = Field(default=False, description="Only the file name is stored")


class ModelsConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    cache_dir: Path | None = None
    allow_download: bool = True


class LightmanConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    video: VideoConfig = VideoConfig()
    limits: MediaLimits = MediaLimits()
    baseline: BaselineConfig = BaselineConfig()
    events: EventsConfig = EventsConfig()
    storage: StorageConfig = StorageConfig()
    privacy: PrivacyConfig = PrivacyConfig()
    models: ModelsConfig = ModelsConfig()
    log_level: str = "INFO"

    @classmethod
    def load(cls, path: Path | None) -> LightmanConfig:
        if path is None:
            return cls()
        try:
            data: dict[str, Any] = tomllib.loads(path.read_text("utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ConfigError(f"cannot read config {path.name}: {exc}") from exc
        try:
            return cls.model_validate(data)
        except ValueError as exc:
            raise ConfigError(f"invalid config {path.name}: {exc}") from exc

    def snapshot(self) -> dict[str, Any]:
        """JSON-safe copy for the manifest."""
        return self.model_dump(mode="json")
