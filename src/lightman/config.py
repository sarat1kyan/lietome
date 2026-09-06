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


class AUConfig(BaseModel):
    """Action Unit detector (OpenGraphAU via ONNX Runtime)."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    model: str = Field(
        default="opengraphau/resnet50_s2",
        pattern="^opengraphau/(resnet50_s2|resnet18_s2)$",
        description="resnet50_s2: better; resnet18_s2: ~4x faster",
    )
    stride: int = Field(
        default=1, ge=1, description="Run the AU model on every Nth analyzed frame (1 = all)"
    )
    prefer_gpu: bool = True
    min_face_px: float = Field(
        default=48.0, ge=8, description="Skip AU inference when the face box is narrower"
    )


class AudioConfig(BaseModel):
    """Audio pipeline: Silero VAD + prosodic features (librosa pyin)."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    vad_threshold: float = Field(default=0.5, ge=0, le=1)
    min_speech_ms: int = Field(default=250, ge=0)
    min_silence_ms: int = Field(default=300, ge=0)
    f0_min_hz: float = Field(default=60.0, gt=0)
    f0_max_hz: float = Field(default=400.0, gt=0)
    long_pause_ms: int = Field(
        default=1500, ge=0, description="Within-speech gap reported as a pause event"
    )
    voiced_prob_min: float = Field(
        default=0.5,
        ge=0,
        le=1,
        description="Frames below this pyin voicing probability are excluded from voice statistics",
    )
    min_event_ms: int = Field(
        default=250, ge=0, description="Minimum duration of a voice deviation event"
    )
    signals: list[str] = Field(default_factory=lambda: ["voice.f0_hz", "voice.energy_db"])


class AdaptiveBaselineConfig(BaseModel):
    """Bounded tracking of each signal after the calibration window (ADR-014)."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    half_life_s: float = Field(default=60.0, gt=0)
    max_center_shift: float = Field(default=3.0, ge=0, description="In anchor scales")
    max_scale_ratio: float = Field(default=4.0, ge=1.0)
    update_z_max: float = Field(
        default=2.5, gt=0, description="Frames beyond this |z| do not update"
    )


class BaselineConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: str = Field(default="leading_window", pattern="^(leading_window)$")
    window_s: float = Field(default=40.0, gt=0, description="Calibration window length")
    min_quality: float = Field(default=0.5, ge=0, le=1, description="Frame quality gate")
    min_samples: int = Field(default=60, ge=5, description="Below this, baseline is low quality")
    good_samples: int = Field(default=600, ge=5, description="At/above this, sample-size term = 1")
    adaptive: AdaptiveBaselineConfig = AdaptiveBaselineConfig()


class EventsConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    z_enter: float = Field(default=3.0, gt=0, description="|robust z| to open an event")
    z_exit: float = Field(default=2.0, gt=0, description="|robust z| to close (hysteresis)")
    z_enter_by_prefix: dict[str, float] = Field(
        default_factory=lambda: {"au.": 4.0, "blendshape.": 4.0},
        description="Higher entry thresholds for noisy classifier outputs; exit shifts alike",
    )
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
            "au.AU1",
            "au.AU2",
            "au.AU4",
            "au.AU5",
            "au.AU6",
            "au.AU7",
            "au.AU9",
            "au.AU10",
            "au.AU12",
            "au.AU14",
            "au.AU15",
            "au.AU17",
            "au.AU20",
            "au.AU23",
            "au.AU24",
            "au.AU25",
            "au.AU26",
        ]
    )
    blink_ear_threshold: float = Field(default=0.21, gt=0, description="EAR closed threshold")

    def thresholds_for(self, signal: str) -> tuple[float, float]:
        """(enter, exit) for a signal, honoring prefix overrides."""
        for prefix, enter in self.z_enter_by_prefix.items():
            if signal.startswith(prefix):
                return enter, self.z_exit + (enter - self.z_enter)
        return self.z_enter, self.z_exit

    blink_min_ms: int = Field(default=50, ge=0)
    blink_max_ms: int = Field(default=500, ge=0)


class StorageConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    store_landmarks: bool = Field(default=False, description="Persist 478x3 landmarks per frame")
    write_report: bool = True
    event_thumbnails: bool = Field(default=True, description="Small JPEG crops at event peaks")
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
    au: AUConfig = AUConfig()
    audio: AudioConfig = AudioConfig()
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
