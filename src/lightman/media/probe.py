"""Container/stream probing with PyAV. No subprocesses, no shell."""

from __future__ import annotations

import hashlib
from fractions import Fraction
from pathlib import Path

import av

from lightman.core.errors import MediaError, SecurityLimitError
from lightman.core.timebase import pts_to_us
from lightman.media.limits import MediaLimits, check_file_limits, check_frame_geometry
from lightman.schema.media import AudioStreamInfo, MediaInfo, VideoStreamInfo

_HASH_CHUNK = 4 * 1024 * 1024


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_HASH_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def _fraction_str(tb: Fraction | None) -> str:
    return "0/1" if tb is None else f"{tb.numerator}/{tb.denominator}"


def _stream_rotation_deg(stream: av.video.stream.VideoStream) -> int:
    """Rotation from container metadata (legacy 'rotate' tag). Frame-level side data is
    consulted again at decode time via ``VideoFrame.rotation``."""
    raw = stream.metadata.get("rotate")
    if raw is None:
        return 0
    try:
        return int(float(raw)) % 360
    except ValueError:
        return 0


def probe_media(path: Path, limits: MediaLimits | None = None) -> MediaInfo:
    """Read container + stream metadata without decoding frames.

    Raises :class:`SecurityLimitError` if declared geometry/duration/streams exceed limits,
    and :class:`MediaError` if the container cannot be opened.
    """
    limits = limits or MediaLimits()
    size = check_file_limits(path, limits)
    try:
        container = av.open(str(path), mode="r", metadata_errors="ignore")
    except Exception as exc:  # PyAV raises FFmpegError subclasses or OSError for garbage input
        raise MediaError(f"cannot open media container: {exc}") from exc

    with container:
        video_streams = list(container.streams.video)
        audio_streams = list(container.streams.audio)
        if len(video_streams) > limits.max_video_streams:
            raise SecurityLimitError(f"too many video streams: {len(video_streams)}")
        if len(audio_streams) > limits.max_audio_streams:
            raise SecurityLimitError(f"too many audio streams: {len(audio_streams)}")

        duration_us: int | None = None
        if container.duration is not None:
            duration_us = int(container.duration)  # PyAV reports container duration in us
            if duration_us > limits.max_duration_us:
                raise SecurityLimitError(
                    f"declared duration {duration_us / 1e6:.0f}s exceeds limit "
                    f"{limits.max_duration_us / 1e6:.0f}s"
                )

        vinfos: list[VideoStreamInfo] = []
        for vs in video_streams:
            cc = vs.codec_context
            check_frame_geometry(cc.width, cc.height, limits)
            tb = vs.time_base
            vdur = pts_to_us(vs.duration, tb) if (vs.duration is not None and tb) else None
            vinfos.append(
                VideoStreamInfo(
                    index=vs.index,
                    codec=cc.name,
                    width=cc.width,
                    height=cc.height,
                    rotation_deg=_stream_rotation_deg(vs),
                    pix_fmt=cc.pix_fmt,
                    average_fps=float(vs.average_rate) if vs.average_rate else None,
                    guessed_fps=float(vs.guessed_rate) if vs.guessed_rate else None,
                    frame_count=vs.frames or None,
                    duration_us=vdur,
                    time_base=_fraction_str(tb),
                )
            )

        ainfos: list[AudioStreamInfo] = []
        for aus in audio_streams:
            acc = aus.codec_context
            tb = aus.time_base
            adur = pts_to_us(aus.duration, tb) if (aus.duration is not None and tb) else None
            ainfos.append(
                AudioStreamInfo(
                    index=aus.index,
                    codec=acc.name,
                    sample_rate=int(acc.sample_rate or 0),
                    channels=int(acc.channels or 0),
                    duration_us=adur,
                    time_base=_fraction_str(tb),
                )
            )

        fmt = container.format.name if container.format else "unknown"

    return MediaInfo(
        path_name=path.name,
        size_bytes=size,
        sha256=sha256_file(path),
        container_format=fmt,
        duration_us=duration_us,
        video_streams=vinfos,
        audio_streams=ainfos,
    )
