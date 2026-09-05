"""Shared interval utilities for event detectors."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


@dataclass(slots=True)
class Segment:
    start_idx: int
    end_idx: int  # inclusive
    peak_idx: int
    peak_abs: float


def hysteresis_segments(
    score: npt.NDArray[np.floating],
    ok: npt.NDArray[np.bool_],
    *,
    enter: float,
    exit_: float,
) -> list[Segment]:
    """Find runs where ``score`` rises above ``enter`` and stays above ``exit_``.

    ``score`` must be non-negative (use abs(z)). Frames with ``ok == False`` or NaN close an
    open run and can never open one.
    """
    segs: list[Segment] = []
    open_start: int | None = None
    peak_idx = -1
    peak_abs = -1.0
    n = score.shape[0]
    for i in range(n):
        s = float(score[i])
        valid = bool(ok[i]) and np.isfinite(s)
        if open_start is None:
            if valid and s >= enter:
                open_start, peak_idx, peak_abs = i, i, s
        elif not valid or s < exit_:
            segs.append(Segment(open_start, i - 1, peak_idx, peak_abs))
            open_start = None
        elif s > peak_abs:
            peak_idx, peak_abs = i, s
    if open_start is not None:
        segs.append(Segment(open_start, n - 1, peak_idx, peak_abs))
    return segs


def merge_close_segments(
    segs: list[Segment], t_us: npt.NDArray[np.integer], gap_us: int
) -> list[Segment]:
    if not segs:
        return []
    merged = [segs[0]]
    for s in segs[1:]:
        prev = merged[-1]
        if int(t_us[s.start_idx]) - int(t_us[prev.end_idx]) <= gap_us:
            if s.peak_abs > prev.peak_abs:
                prev.peak_idx, prev.peak_abs = s.peak_idx, s.peak_abs
            prev.end_idx = s.end_idx
        else:
            merged.append(s)
    return merged


def segment_end_us(t_us: npt.NDArray[np.integer], end_idx: int, frame_period_us: int) -> int:
    """End time = start of the last frame + one frame period (interval is half-open in frames)."""
    return int(t_us[end_idx]) + frame_period_us


def median_frame_period_us(t_us: npt.NDArray[np.integer]) -> int:
    if t_us.size < 2:
        return 33_333
    d = np.diff(t_us.astype(np.int64))
    d = d[d > 0]
    return int(np.median(d)) if d.size else 33_333
