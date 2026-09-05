"""Robust per-signal baselines (median / scaled MAD) and robust z-scores.

Why median/MAD rather than mean/SD: a calibration window is short and frequently contains
the very excursions we later want to detect (a blink, a head turn). The median and MAD are
resistant to those contaminations (50 % breakdown point), whereas one large excursion can
inflate the SD enough to hide everything that follows. The 1.4826 factor makes the scaled
MAD a consistent estimator of sigma under normality so "robust z" reads like a z-score.

Known limitation (documented in scientific-limitations.md): a leading window assumes the
subject's *early* behavior is representative. It is a calibration convenience, not a
psychological claim. Later phases add question-aware and adaptive baselines.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict, Field

from lightman.config import BaselineConfig
from lightman.features.table import signal_unit

MAD_TO_SIGMA = 1.4826

# Absolute lower bounds on the robust scale, per unit. Prevents division by ~0 for signals
# that are nearly constant in the window (which would turn measurement noise into "events").
SCALE_FLOOR_BY_UNIT: dict[str, float] = {
    "deg": 0.5,
    "ratio": 0.005,
    "coefficient": 0.01,
    "probability": 0.02,
    "model_units": 0.05,
    "unitless": 1e-3,
}


class SignalBaseline(BaseModel):
    model_config = ConfigDict(frozen=True)

    feature: str
    unit: str
    center: float = Field(description="Median over the baseline window")
    scale: float = Field(description="max(1.4826 * MAD, unit floor)")
    n: int = Field(description="Number of quality-gated samples used")
    floor_applied: bool


class BaselineSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: str
    window_start_us: int
    window_end_us: int
    frames_in_window: int
    frames_used: int
    quality: float = Field(ge=0, le=1, description="Baseline reliability in [0, 1]")
    notes: list[str] = Field(default_factory=list)
    signals: dict[str, SignalBaseline]


def robust_center_scale(x: npt.NDArray[np.floating], unit: str) -> tuple[float, float, int, bool]:
    finite = x[np.isfinite(x)]
    n = int(finite.size)
    if n == 0:
        return math.nan, math.nan, 0, False
    center = float(np.median(finite))
    mad = float(np.median(np.abs(finite - center)))
    scale = MAD_TO_SIGMA * mad
    floor = SCALE_FLOOR_BY_UNIT.get(unit, 1e-3)
    floored = scale < floor
    return center, max(scale, floor), n, floored


def robust_z(x: npt.NDArray[np.floating], center: float, scale: float) -> npt.NDArray[np.float64]:
    if not math.isfinite(center) or not math.isfinite(scale) or scale <= 0:
        return np.full(x.shape, np.nan, dtype=np.float64)
    return (np.asarray(x, dtype=np.float64) - center) / scale


def compute_leading_window_baseline(
    t_us: npt.NDArray[np.integer],
    quality: npt.NDArray[np.floating],
    signals: Mapping[str, npt.NDArray[np.floating]],
    cfg: BaselineConfig,
) -> BaselineSnapshot:
    window_end = round(cfg.window_s * 1_000_000)
    in_window = t_us <= window_end
    usable = in_window & (quality >= cfg.min_quality)
    n_window = int(in_window.sum())
    n_used = int(usable.sum())
    notes: list[str] = []

    per_signal: dict[str, SignalBaseline] = {}
    for name, values in signals.items():
        unit = signal_unit(name)
        center, scale, n, floored = robust_center_scale(values[usable], unit)
        per_signal[name] = SignalBaseline(
            feature=name, unit=unit, center=center, scale=scale, n=n, floor_applied=floored
        )

    # Reliability: sample-size term (saturating) x mean frame quality within the window.
    size_term = min(1.0, n_used / cfg.good_samples) if cfg.good_samples > 0 else 0.0
    q_term = float(np.mean(quality[usable])) if n_used else 0.0
    reliability = size_term * q_term
    if n_used < cfg.min_samples:
        notes.append(
            f"only {n_used} quality-gated frames in the {cfg.window_s:.0f}s baseline window "
            f"(minimum {cfg.min_samples}); deviations are unreliable"
        )
    if t_us.size and int(t_us[-1]) < window_end:
        notes.append("recording is shorter than the baseline window; whole recording used")
    floored_names = [s.feature for s in per_signal.values() if s.floor_applied]
    if floored_names:
        notes.append(
            f"{len(floored_names)} signal(s) had near-constant baselines; scale floor applied"
        )

    actual_end = int(t_us[in_window].max()) if n_window else 0
    return BaselineSnapshot(
        mode=cfg.mode,
        window_start_us=0,
        window_end_us=actual_end,
        frames_in_window=n_window,
        frames_used=n_used,
        quality=max(0.0, min(1.0, reliability)),
        notes=notes,
        signals=per_signal,
    )
