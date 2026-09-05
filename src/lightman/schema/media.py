"""Container/stream metadata as reported by the demuxer (PyAV)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class VideoStreamInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    index: int
    codec: str
    width: int = Field(description="Coded width before rotation")
    height: int = Field(description="Coded height before rotation")
    rotation_deg: int = Field(default=0, description="Display rotation from container metadata")
    pix_fmt: str | None = None
    average_fps: float | None = Field(default=None, description="Container average rate")
    guessed_fps: float | None = Field(
        default=None, description="Demuxer guess (may differ for VFR)"
    )
    frame_count: int | None = Field(default=None, description="Container-declared count, if any")
    duration_us: int | None = None
    time_base: str = Field(description="Stream time base as 'num/den'")

    @property
    def display_size(self) -> tuple[int, int]:
        """(width, height) after applying display rotation."""
        if self.rotation_deg % 180 == 90:
            return self.height, self.width
        return self.width, self.height


class AudioStreamInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    index: int
    codec: str
    sample_rate: int
    channels: int
    duration_us: int | None = None
    time_base: str


class MediaInfo(BaseModel):
    """Everything Lightman knows about a media file *before* decoding pixels."""

    model_config = ConfigDict(frozen=True)

    path_name: str = Field(description="File name only; full paths are not persisted")
    size_bytes: int
    sha256: str
    container_format: str
    duration_us: int | None
    video_streams: list[VideoStreamInfo]
    audio_streams: list[AudioStreamInfo]

    @property
    def has_video(self) -> bool:
        return bool(self.video_streams)

    @property
    def has_audio(self) -> bool:
        return bool(self.audio_streams)
