"""Bounded adaptive baseline: the calibration window anchors each signal; afterwards the
center and scale track the subject's ongoing behavior slowly, only within limits.

Why: 30-40 s of calibration cannot sample a person's conversational range (brow flashes,
jaw amplitude, head turns). Sessions showed steady "deviations" that were simply the wider
distribution of ordinary talking. Why bounded: an unbounded tracker would absorb the very
changes we want to report (drift), so the center may move at most ``max_center_shift`` anchor
scales from the anchor and the scale may grow to at most ``max_scale_ratio`` times the anchor
scale (and never shrink below it). Why only non-event frames: updating during an open
deviation would pull the baseline toward the excursion; frames whose |z| exceeds
``update_z_max`` are skipped.

Same code serves offline (sequential pass over arrays) and live (per-frame update).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from lightman.baseline.robust import BaselineSnapshot, SignalBaseline


@dataclass(slots=True)
class AdaptiveConfig:
    enabled: bool = True
    half_life_s: float = 60.0
    max_center_shift: float = 3.0  # in anchor scales
    max_scale_ratio: float = 4.0
    update_z_max: float = 2.5  # center updates only within this |z|; residuals clipped here


@dataclass(slots=True)
class _Track:
    anchor_center: float
    anchor_scale: float
    center: float
    scale: float
    m2: float  # running estimate of squared deviation for the scale


class AdaptiveSignal:
    """Per-signal, per-state tracker."""

    def __init__(self, anchor: SignalBaseline, cfg: AdaptiveConfig) -> None:
        self.cfg = cfg
        self.ok = math.isfinite(anchor.center) and math.isfinite(anchor.scale) and anchor.scale > 0
        c = anchor.center if self.ok else 0.0
        s = anchor.scale if self.ok else 1.0
        self.t = _Track(c, s, c, s, s * s)

    @property
    def center(self) -> float:
        return self.t.center

    @property
    def scale(self) -> float:
        return self.t.scale

    def update(self, value: float, dt_s: float) -> None:
        """Center moves only for frames within ``update_z_max`` (so excursions do not pull it);
        the scale learns from every frame with the residual clipped at ``update_z_max`` scales
        (bounded influence), otherwise a distribution wider than the anchor could never be
        learned because its frames would all be "too far" to count."""
        if not self.ok or not math.isfinite(value) or dt_s <= 0:
            return
        alpha = 1.0 - 0.5 ** (dt_s / self.cfg.half_life_s)
        resid = value - self.t.center
        z = resid / self.t.scale
        if abs(z) <= self.cfg.update_z_max:
            c = self.t.center + alpha * resid
            lo = self.t.anchor_center - self.cfg.max_center_shift * self.t.anchor_scale
            hi = self.t.anchor_center + self.cfg.max_center_shift * self.t.anchor_scale
            self.t.center = min(hi, max(lo, c))
        clip = self.cfg.update_z_max * self.t.scale
        r = max(-clip, min(clip, value - self.t.center))
        self.t.m2 = self.t.m2 + alpha * (r * r - self.t.m2)
        s = math.sqrt(max(self.t.m2, 1e-12))
        cap = self.t.anchor_scale * self.cfg.max_scale_ratio
        self.t.scale = min(cap, max(self.t.anchor_scale, s))


class AdaptiveBaseline:
    """Tracks every signal of one or more state baselines."""

    def __init__(self, baselines: Mapping[str, BaselineSnapshot], cfg: AdaptiveConfig) -> None:
        self.cfg = cfg
        self._tracks: dict[str, dict[str, AdaptiveSignal]] = {
            state: {name: AdaptiveSignal(sb, cfg) for name, sb in snap.signals.items()}
            for state, snap in baselines.items()
        }
        self._last_t_us: dict[str, int] = {}

    def states(self) -> list[str]:
        return list(self._tracks)

    def center_scale(self, state: str, name: str) -> tuple[float, float] | None:
        tr = self._tracks.get(state, {}).get(name)
        if tr is None or not tr.ok:
            return None
        return tr.center, tr.scale

    def update(self, state: str, t_us: int, values: Mapping[str, float]) -> None:
        if not self.cfg.enabled or state not in self._tracks:
            return
        last = self._last_t_us.get(state)
        self._last_t_us[state] = t_us
        if last is None:
            return
        dt_s = (t_us - last) / 1e6
        for name, tr in self._tracks[state].items():
            v = values.get(name)
            if v is not None:
                tr.update(float(v), dt_s)


def adaptive_center_scale_arrays(
    t_us: npt.NDArray[np.integer],
    values: npt.NDArray[np.floating],
    frame_state: npt.NDArray[np.str_] | None,
    baselines: Mapping[str, BaselineSnapshot],
    name: str,
    cfg: AdaptiveConfig,
    *,
    start_us: int,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Offline counterpart: per-frame center/scale after a sequential adaptive pass that
    starts updating at ``start_us`` (end of the calibration window)."""
    ab = AdaptiveBaseline(baselines, cfg)
    n = t_us.shape[0]
    center = np.full(n, np.nan)
    scale = np.full(n, np.nan)
    for i in range(n):
        state = str(frame_state[i]) if frame_state is not None else "all"
        if state not in baselines:
            state = "all"
        cs = ab.center_scale(state, name)
        if cs is not None:
            center[i], scale[i] = cs
        if int(t_us[i]) > start_us:
            ab.update(state, int(t_us[i]), {name: float(values[i])})
    return center, scale
