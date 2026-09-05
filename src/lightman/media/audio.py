"""Audio decoding to mono float32 at a fixed rate, with container-time alignment.

Audio and video are aligned on the container clock: every sample block carries the container
time (us) of its first sample, and the caller subtracts the session origin (container time of
the first analyzed video frame) so both modalities share one ``t_us`` axis (ADR-004).
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
from lightman.media.limits import MediaLimits

log = get_logger(__name__)

TARGET_RATE = 16_000


@dataclass(slots=True)
class AudioBlock:
    container_t_us: int
    """Container time of the first sample in this block."""
    samples: npt.NDArray[np.float32]
    """Mono float32 in [-1, 1]."""
    rate: int


def iter_audio_blocks(
    path: Path,
    *,
    stream_index: int = 0,
    rate: int = TARGET_RATE,
    limits: MediaLimits | None = None,
) -> Iterator[AudioBlock]:
    """Decode and resample the audio stream to mono ``rate`` Hz, yielding blocks in order."""
    limits = limits or MediaLimits()
    try:
        container = av.open(str(path), mode="r", metadata_errors="ignore")
    except Exception as exc:
        raise MediaError(f"cannot open media container: {exc}") from exc
    with container:
        audios = container.streams.audio
        if not audios:
            raise UnsupportedMediaError("media has no audio stream")
        if stream_index >= len(audios):
            raise UnsupportedMediaError(f"audio stream {stream_index} not present")
        stream = audios[stream_index]
        tb: Fraction = stream.time_base or Fraction(1, rate)
        resampler = av.AudioResampler(format="fltp", layout="mono", rate=rate)
        total = 0
        max_samples = int(limits.max_duration_us / 1_000_000 * rate) + rate
        next_t_us: int | None = None
        try:
            for frame in container.decode(stream):
                if frame.pts is not None:
                    next_t_us = pts_to_us(frame.pts, frame.time_base or tb)
                for out in resampler.resample(frame):
                    yield from _emit(out, rate, next_t_us)
                    total += out.samples
                    if next_t_us is not None:
                        next_t_us += int(out.samples * 1_000_000 / rate)
                    if total > max_samples:
                        raise SecurityLimitError("audio duration exceeded configured limit")
            for out in resampler.resample(None):
                yield from _emit(out, rate, next_t_us)
                total += out.samples
                if next_t_us is not None:
                    next_t_us += int(out.samples * 1_000_000 / rate)
        except (SecurityLimitError, MediaError, UnsupportedMediaError):
            raise
        except Exception as exc:
            raise MediaError(f"audio decode failed: {exc}") from exc
    log.info("audio_decoded", samples=total, seconds=round(total / rate, 2), rate=rate)


def _emit(frame: av.AudioFrame, rate: int, t_us: int | None) -> Iterator[AudioBlock]:
    arr = frame.to_ndarray()
    mono = np.asarray(arr[0] if arr.ndim == 2 else arr, dtype=np.float32)
    if mono.size == 0:
        return
    yield AudioBlock(container_t_us=t_us if t_us is not None else 0, samples=mono, rate=rate)


def load_audio_mono(
    path: Path, *, rate: int = TARGET_RATE, limits: MediaLimits | None = None
) -> tuple[npt.NDArray[np.float32], int]:
    """Return (samples, container_t_us_of_first_sample). Convenience for prerecorded files."""
    blocks = list(iter_audio_blocks(path, rate=rate, limits=limits))
    if not blocks:
        return np.zeros(0, dtype=np.float32), 0
    return np.concatenate([b.samples for b in blocks]), blocks[0].container_t_us
