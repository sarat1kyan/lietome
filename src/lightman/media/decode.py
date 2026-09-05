"""Streaming video decode yielding RGB frames with exact media timestamps.

Why PyAV instead of ``cv2.VideoCapture``: OpenCV exposes frame *indices* and an estimated
FPS, which silently mis-times variable-frame-rate recordings (phones, screen captures,
conference apps). PyAV exposes the container PTS for every frame, so each measurement is
stamped with the time it actually occurred.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
import numpy.typing as npt

from lightman.core.errors import MediaError, SecurityLimitError, UnsupportedMediaError
from lightman.core.logging import get_logger
from lightman.core.timebase import pts_to_us
from lightman.media.limits import MediaLimits, check_frame_geometry

log = get_logger(__name__)


@dataclass(slots=True)
class DecodedFrame:
    index: int
    """Sequential index among *yielded* frames (after any sampling)."""
    source_index: int
    """Index in the decoded stream before sampling."""
    t_us: int
    """Media time in microseconds, relative to the first decoded frame."""
    rgb: npt.NDArray[np.uint8]
    """HxWx3 uint8, display-oriented (rotation applied)."""
    rotation_deg: int
    timestamp_estimated: bool
    """True if PTS was missing and time was reconstructed from frame rate."""


def _rotate(rgb: npt.NDArray[np.uint8], rotation_deg: int) -> npt.NDArray[np.uint8]:
    """Apply display rotation. PyAV/FFmpeg report the *rotation to display* in degrees;
    a positive value means the stored image must be rotated counter-clockwise to view."""
    r = rotation_deg % 360
    if r == 0:
        return rgb
    k = {90: 1, 180: 2, 270: 3}.get(r)
    if k is None:  # non right-angle rotation: leave as-is, caller has the metadata
        return rgb
    return np.ascontiguousarray(np.rot90(rgb, k=k))


def iter_video_frames(
    path: Path,
    *,
    stream_index: int = 0,
    target_fps: float | None = None,
    limits: MediaLimits | None = None,
    max_frames: int | None = None,
) -> Iterator[DecodedFrame]:
    """Yield display-oriented RGB frames with microsecond timestamps.

    ``target_fps`` subsamples by *time* (not by index) so VFR sources are handled correctly.
    ``max_frames`` stops early (useful for tests and quick previews).
    """
    limits = limits or MediaLimits()
    try:
        container = av.open(str(path), mode="r", metadata_errors="ignore")
    except Exception as exc:
        raise MediaError(f"cannot open media container: {exc}") from exc

    with container:
        videos = container.streams.video
        if not videos:
            raise UnsupportedMediaError("media has no video stream")
        if stream_index >= len(videos):
            raise UnsupportedMediaError(f"video stream {stream_index} not present")
        stream = videos[stream_index]
        stream.thread_type = "AUTO"
        stream.codec_context.thread_type = "AUTO"
        tb: Fraction = stream.time_base or Fraction(1, 1_000_000)
        rate = stream.average_rate or stream.guessed_rate
        nominal_period_us = int(1_000_000 / rate) if rate else None

        min_gap_us = int(1_000_000 / target_fps) if target_fps else 0
        next_keep_us = 0
        first_us: int | None = None
        yielded = 0
        decoded = 0
        estimated_warned = False
        hard_cap = min(limits.max_frames, max_frames) if max_frames else limits.max_frames

        try:
            for frame in container.decode(stream):
                if decoded >= hard_cap:
                    if max_frames is None:
                        raise SecurityLimitError(f"decoded frame count exceeded {hard_cap}")
                    break
                check_frame_geometry(frame.width, frame.height, limits)
                estimated = False
                if frame.pts is not None:
                    t_abs = pts_to_us(frame.pts, frame.time_base or tb)
                elif nominal_period_us is not None:
                    t_abs = decoded * nominal_period_us
                    estimated = True
                    if not estimated_warned:
                        log.warning("frame_pts_missing_using_nominal_rate", stream=stream_index)
                        estimated_warned = True
                else:
                    raise MediaError("frame has no PTS and stream has no frame rate")
                if first_us is None:
                    first_us = t_abs
                t_us = t_abs - first_us
                decoded += 1
                if t_us > limits.max_duration_us:
                    raise SecurityLimitError("actual duration exceeded configured limit")
                if min_gap_us and t_us < next_keep_us:
                    continue
                if min_gap_us:
                    # Advance in fixed steps so long gaps do not cause bursts afterwards.
                    while next_keep_us <= t_us:
                        next_keep_us += min_gap_us
                rgb = np.asarray(frame.to_ndarray(format="rgb24"), dtype=np.uint8)
                rotation = int(getattr(frame, "rotation", 0) or 0)
                yield DecodedFrame(
                    index=yielded,
                    source_index=decoded - 1,
                    t_us=t_us,
                    rgb=_rotate(rgb, rotation),
                    rotation_deg=rotation,
                    timestamp_estimated=estimated,
                )
                yielded += 1
        except (SecurityLimitError, MediaError):
            raise
        except Exception as exc:
            raise MediaError(f"decode failed after {decoded} frames: {exc}") from exc
        log.info("video_decoded", frames_decoded=decoded, frames_yielded=yielded)
