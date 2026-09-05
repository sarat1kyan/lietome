"""Resource limits applied to untrusted media before and during decoding.

Media files are hostile input. A tiny container can declare an absurd resolution, an
hours-long duration, or millions of frames. These limits are enforced *before* pixel
memory is allocated and re-checked as frames stream in.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from lightman.core.errors import SecurityLimitError

MIB = 1024 * 1024


class MediaLimits(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_file_bytes: int = Field(default=4 * 1024 * MIB, description="Reject larger files")
    max_duration_us: int = Field(default=4 * 3600 * 1_000_000, description="4 h")
    max_pixels_per_frame: int = Field(default=3840 * 2160, description="4K UHD")
    max_frames: int = Field(default=2_000_000, description="Hard cap on decoded frames")
    max_video_streams: int = 8
    max_audio_streams: int = 8


def check_file_limits(path: Path, limits: MediaLimits) -> int:
    """Validate the path is a regular, readable file within size limits. Returns size."""
    if not path.exists():
        raise SecurityLimitError(f"media file does not exist: {path.name}")
    if path.is_symlink():
        # Resolve explicitly so we never follow a link to somewhere unexpected silently.
        path = path.resolve(strict=True)
    if not path.is_file():
        raise SecurityLimitError(f"media path is not a regular file: {path.name}")
    size = path.stat().st_size
    if size == 0:
        raise SecurityLimitError(f"media file is empty: {path.name}")
    if size > limits.max_file_bytes:
        raise SecurityLimitError(
            f"media file is {size / MIB:.1f} MiB, above limit {limits.max_file_bytes / MIB:.0f} MiB"
        )
    return size


def check_frame_geometry(width: int, height: int, limits: MediaLimits) -> None:
    if width <= 0 or height <= 0:
        raise SecurityLimitError(f"invalid frame geometry {width}x{height}")
    if width * height > limits.max_pixels_per_frame:
        raise SecurityLimitError(
            f"frame geometry {width}x{height} exceeds max pixels {limits.max_pixels_per_frame}"
        )
