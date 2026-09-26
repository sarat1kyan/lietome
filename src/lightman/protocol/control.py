"""Control-referenced scoring: each answer against this person's own control answers.

The 40 s calibration is quiet sitting, reading and free talk. Answers to questions are none of
those: they are speech under a question, with its own pace and effort. Control questions
(known, low-stakes, same format) are the matched reference, which is how comparison-question
designs in the deception literature are built. For every answer this module pools the frames of
the *other* control answers (leave-one-out for controls, so control answers get a fair score
too) and measures:

* the per-signal shift of the answer from the control pool, in the pool's robust SD;
* the literature cue profile with the control pool as the baseline, pattern rates against the
  control answers, blink rate against the control answers and pitch against the control mean.

With fewer than two control answers there is no pool and nothing is computed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import numpy.typing as npt

from lightman.interpretation.cues import cue_profile

MIN_POOL_FRAMES = 30
SCALE_FLOOR_FRACTION = 0.5
"""A control pool narrower than half the calibration spread is floored there: two short
answers can look unrealistically consistent."""

SHIFT_SIGNALS: tuple[str, ...] = (
    "head.yaw_deg",
    "head.pitch_deg",
    "head.speed_deg_s",
    "gaze.horizontal",
    "gaze.vertical",
    "eye.aspect_ratio_mean",
    "blendshape.browInnerUp",
    "blendshape.browDownLeft",
    "blendshape.browDownRight",
    "blendshape.mouthPressLeft",
    "blendshape.mouthPressRight",
    "blendshape.jawOpen",
    "au.AU1",
    "au.AU2",
    "au.AU4",
    "au.AU6",
    "au.AU7",
    "au.AU12",
    "au.AU14",
    "au.AU15",
    "au.AU17",
    "au.AU23",
    "au.AU24",
)


def _mask(
    t_us: npt.NDArray[np.integer], windows: Sequence[tuple[int, int]]
) -> npt.NDArray[np.bool_]:
    m = np.zeros(t_us.shape, dtype=bool)
    for a, b in windows:
        m |= (t_us >= a) & (t_us < b)
    return m


def control_pool(
    *,
    t_us: npt.NDArray[np.integer],
    quality: npt.NDArray[np.floating],
    signals: Mapping[str, npt.NDArray[np.floating]],
    windows: Sequence[tuple[int, int]],
    calibration_scale: Mapping[str, float],
    min_quality: float = 0.4,
) -> tuple[dict[str, float], dict[str, float]] | None:
    """(center, scale) per signal over the pooled control windows, or None when too few frames."""
    m = _mask(t_us, windows) & (np.asarray(quality, dtype=float) >= min_quality)
    if int(m.sum()) < MIN_POOL_FRAMES:
        return None
    center: dict[str, float] = {}
    scale: dict[str, float] = {}
    for name, col in signals.items():
        v = np.asarray(col, dtype=float)[m]
        v = v[np.isfinite(v)]
        if v.size < MIN_POOL_FRAMES:
            continue
        med = float(np.median(v))
        mad = float(np.median(np.abs(v - med))) * 1.4826
        floor = SCALE_FLOOR_FRACTION * float(calibration_scale.get(name, 0.0) or 0.0)
        sc = max(mad, floor)
        if sc > 0 and np.isfinite(sc):
            center[name] = med
            scale[name] = sc
    return center, scale


def control_shift(
    *,
    t_us: npt.NDArray[np.integer],
    quality: npt.NDArray[np.floating],
    signals: Mapping[str, npt.NDArray[np.floating]],
    window: tuple[int, int],
    center: Mapping[str, float],
    scale: Mapping[str, float],
    top: int = 5,
    min_quality: float = 0.4,
) -> list[dict[str, Any]]:
    """Signals whose answer median moved furthest from the control pool, in pool SD."""
    m = _mask(t_us, [window]) & (np.asarray(quality, dtype=float) >= min_quality)
    rows: list[dict[str, Any]] = []
    for name in SHIFT_SIGNALS:
        if name not in center or name not in signals:
            continue
        v = np.asarray(signals[name], dtype=float)[m]
        v = v[np.isfinite(v)]
        if v.size < 5:
            continue
        z = (float(np.median(v)) - center[name]) / scale[name]
        rows.append({"signal": name, "shift_sd": round(z, 2)})
    rows.sort(key=lambda r: -abs(r["shift_sd"]))
    return rows[:top]


def control_referenced(
    *,
    questions: Sequence[Any],
    t_us: npt.NDArray[np.integer],
    quality: npt.NDArray[np.floating],
    signals: Mapping[str, npt.NDArray[np.floating]],
    calibration_scale: Mapping[str, float],
    events: list[Any],
    blink_times_us: list[int],
    voice_f0_z: tuple[npt.NDArray[np.integer], npt.NDArray[np.floating]] | None,
    latencies: Mapping[str, float | None],
) -> dict[str, dict[str, Any]]:
    """Per question id: {"index": ..., "cues": ..., "shift": [...], "pool": {...}}.

    ``questions`` need ``id``, ``category``, ``start_us``, ``end_us``."""
    controls = [q for q in questions if q.category == "control"]
    if len(controls) < 2:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for q in questions:
        ref = [c for c in controls if c.id != q.id]
        if len(ref) < 1 or (q.category == "control" and len(ref) < 1):
            continue
        windows = [(c.start_us, c.end_us) for c in ref]
        pool = control_pool(
            t_us=t_us,
            quality=quality,
            signals=signals,
            windows=windows,
            calibration_scale=calibration_scale,
        )
        if pool is None:
            continue
        center, scale = pool
        ref_minutes = max(1e-6, sum(b - a for a, b in windows) / 60e6)
        ref_blinks = sum(1 for t in blink_times_us if any(a <= t < b for a, b in windows))
        pitch_offset = None
        if voice_f0_z is not None:
            vt, vz = voice_f0_z
            pm = _mask(vt, windows) & np.isfinite(vz)
            if pm.sum() >= 10:
                pitch_offset = float(np.mean(vz[pm]))
        ref_lat = [latencies.get(c.id) for c in ref]
        ref_lat_v = [x for x in ref_lat if x is not None]
        prof = cue_profile(
            window=(q.start_us, q.end_us),
            t_us=t_us,
            signals=signals,
            baseline_center=center,
            baseline_scale=scale,
            voice_f0_z=voice_f0_z,
            blink_times_us=blink_times_us,
            reference_blink_rate=(ref_blinks / ref_minutes) or None,
            response_latency_ms=latencies.get(q.id),
            control_latency_ms=float(np.mean(ref_lat_v)) if ref_lat_v else None,
            events=events,
            reference_windows=windows,
            pitch_offset=pitch_offset,
        )
        out[q.id] = {
            "index": prof["index"],
            "cues": prof,
            "shift": control_shift(
                t_us=t_us,
                quality=quality,
                signals=signals,
                window=(q.start_us, q.end_us),
                center=center,
                scale=scale,
            ),
            "pool": {"controls": [c.id for c in ref], "seconds": round(ref_minutes * 60, 1)},
        }
    return out
