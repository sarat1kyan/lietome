"""Temporal smoothing for noisy per-frame classifier outputs.

AU occurrence probabilities jitter frame to frame (a calm face gave AU4 in 0.11-0.49 within
one session). A short centered median filter removes single-frame spikes without shifting
onsets by more than half its width. Applied to ``au.*`` columns before baselines and events;
landmarks-derived signals are left alone.
"""

from __future__ import annotations

from collections import deque

import numpy as np
import numpy.typing as npt

AU_SMOOTH_FRAMES = 5  # ~170 ms at 30 fps, ~330 ms at 15 fps


def median_smooth(
    x: npt.NDArray[np.floating], width: int = AU_SMOOTH_FRAMES
) -> npt.NDArray[np.float64]:
    """Centered running median over ``width`` samples; NaNs are ignored inside the window and
    preserved where the center is NaN."""
    arr = np.asarray(x, dtype=np.float64)
    n = arr.size
    if n == 0 or width <= 1:
        return arr.copy()
    half = width // 2
    out = np.full(n, np.nan)
    for i in range(n):
        if not np.isfinite(arr[i]):
            continue
        win = arr[max(0, i - half) : i + half + 1]
        win = win[np.isfinite(win)]
        out[i] = float(np.median(win)) if win.size else np.nan
    return out


class StreamingMedian:
    """Causal running median (lags by ``width // 2`` frames) for live mode."""

    def __init__(self, width: int = AU_SMOOTH_FRAMES) -> None:
        self.width = width
        self._buf: deque[float] = deque(maxlen=width)

    def push(self, v: float) -> float:
        if np.isfinite(v):
            self._buf.append(float(v))
        if not self._buf:
            return float("nan")
        return float(np.median(np.asarray(self._buf)))
