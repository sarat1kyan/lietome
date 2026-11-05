"""Expressed affect: valence and arousal estimated from the face and the voice.

This is the circumplex description of what the face and voice *show* (Russell 1980), built from
Action Units with well-replicated associations: lip-corner pull and cheek raise for positive
valence (AU12, AU6); brow lowering, lip-corner depression, nose wrinkle, upper-lip raise and
lip stretch for negative valence (AU4, AU15, AU9, AU10, AU20); upper-lid raise, jaw drop, brow
raise and head movement for arousal (AU5, AU26, AU1, AU2), plus voice loudness and pitch when
the person speaks. Each raw score is measured against the same person's calibration, so
0 means "as during calibration", positive and negative values are departures from it, and the
scale is the person's own spread. It is an estimate of expression, not of feeling.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Mapping

import numpy as np
import numpy.typing as npt

SCALE_FLOOR = 0.05
"""Smallest calibration spread used for normalization (probability units)."""
SOFT = 3.0
"""tanh(z / SOFT): 3 calibration SD reach about 0.76."""


def _g(values: Mapping[str, npt.NDArray[np.floating]], k: str, n: int) -> npt.NDArray[np.float64]:
    v = values.get(k)
    if v is None:
        return np.full(n, np.nan)
    return np.asarray(v, dtype=np.float64)


def raw_affect(
    values: Mapping[str, npt.NDArray[np.floating]], n: int
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """(valence_raw, arousal_raw) per frame. Uses Action Units when present, else blendshapes."""
    au12 = _g(values, "au.AU12", n)
    if np.isfinite(au12).any():
        pos = au12 + 0.5 * np.nan_to_num(_g(values, "au.AU6", n))
        neg = (
            np.nan_to_num(_g(values, "au.AU4", n))
            + np.nan_to_num(_g(values, "au.AU15", n))
            + 0.5 * np.nan_to_num(_g(values, "au.AU9", n))
            + 0.5 * np.nan_to_num(_g(values, "au.AU10", n))
            + 0.5 * np.nan_to_num(_g(values, "au.AU20", n))
        )
        aro = (
            np.nan_to_num(_g(values, "au.AU5", n))
            + 0.5 * np.nan_to_num(_g(values, "au.AU26", n))
            + 0.25
            * (np.nan_to_num(_g(values, "au.AU1", n)) + np.nan_to_num(_g(values, "au.AU2", n)))
        )
        valid = np.isfinite(au12)
    else:
        smile = 0.5 * (
            _g(values, "blendshape.mouthSmileLeft", n) + _g(values, "blendshape.mouthSmileRight", n)
        )
        pos = smile
        neg = (
            0.5
            * (
                np.nan_to_num(_g(values, "blendshape.browDownLeft", n))
                + np.nan_to_num(_g(values, "blendshape.browDownRight", n))
            )
            + 0.5
            * (
                np.nan_to_num(_g(values, "blendshape.mouthFrownLeft", n))
                + np.nan_to_num(_g(values, "blendshape.mouthFrownRight", n))
            )
            + 0.5 * np.nan_to_num(_g(values, "blendshape.noseSneerLeft", n))
        )
        aro = (
            0.5
            * (
                np.nan_to_num(_g(values, "blendshape.eyeWideLeft", n))
                + np.nan_to_num(_g(values, "blendshape.eyeWideRight", n))
            )
            + 0.5 * np.nan_to_num(_g(values, "blendshape.jawOpen", n))
            + 0.5 * np.nan_to_num(_g(values, "blendshape.browInnerUp", n))
        )
        valid = np.isfinite(smile)
    speed = _g(values, "head.speed_deg_s", n)
    aro = aro + 0.5 * np.clip(np.nan_to_num(speed) / 60.0, 0.0, 1.0)
    val = pos - 0.6 * neg
    val[~valid] = np.nan
    aro[~valid] = np.nan
    return val, aro


def _norm(x: npt.NDArray[np.float64], ref: npt.NDArray[np.bool_]) -> tuple[float, float]:
    v = x[ref & np.isfinite(x)]
    if v.size < 10:
        v = x[np.isfinite(x)]
    if v.size == 0:
        return 0.0, 1.0
    med = float(np.median(v))
    mad = float(np.median(np.abs(v - med))) * 1.4826
    return med, max(mad, SCALE_FLOOR)


def _smooth(x: npt.NDArray[np.float64], k: int) -> npt.NDArray[np.float64]:
    if k <= 1 or x.size < k:
        return x
    pad = np.pad(x, k // 2, mode="edge")
    out = np.full(x.shape, np.nan)
    for i in range(x.size):
        w = pad[i : i + k]
        w = w[np.isfinite(w)]
        if w.size:
            out[i] = float(np.median(w))
    return out


def affect_series(
    t_us: npt.NDArray[np.integer],
    values: Mapping[str, npt.NDArray[np.floating]],
    quality: npt.NDArray[np.floating],
    calibration_end_us: int,
    *,
    voice_z: tuple[npt.NDArray[np.integer], npt.NDArray[np.floating]] | None = None,
    min_quality: float = 0.4,
) -> dict[str, npt.NDArray[np.float64]]:
    """Per-frame valence and arousal in [-1, 1] relative to this person's calibration.

    ``voice_z``: (t_us, combined loudness and pitch z) from the audio stream; it adds to
    arousal while the person speaks."""
    t = np.asarray(t_us, dtype=np.int64)
    n = t.size
    val, aro = raw_affect(values, n)
    ok = np.asarray(quality, dtype=float) >= min_quality
    val[~ok] = np.nan
    aro[~ok] = np.nan
    ref = t < calibration_end_us
    vm, vs = _norm(val, ref)
    am, as_ = _norm(aro, ref)
    vz = (val - vm) / vs
    az = (aro - am) / as_
    if voice_z is not None and n:
        vt, vv = voice_z
        vt = np.asarray(vt, dtype=np.float64)
        vv = np.asarray(vv, dtype=np.float64)
        good = np.isfinite(vv)
        if good.sum() >= 5:
            interp = np.interp(t, vt[good], vv[good], left=np.nan, right=np.nan)
            near = (
                np.abs(t[:, None] - vt[good][None, :]).min(axis=1) <= 300_000
                if good.sum() < 20000
                else np.ones(n, bool)
            )
            interp[~near] = np.nan
            az = np.where(np.isfinite(interp), 0.7 * az + 0.3 * interp, az)
    fps = 1e6 / float(np.median(np.diff(t))) if n > 1 else 15.0
    k = max(1, round(fps))  # about one second
    return {
        "valence": np.tanh(_smooth(vz, k) / SOFT),
        "arousal": np.tanh(_smooth(az, k) / SOFT),
    }


def affect_summary(
    t_us: npt.NDArray[np.integer],
    series: dict[str, npt.NDArray[np.float64]],
    start_us: int,
) -> dict[str, float | None]:
    """Means after calibration and the share of time in each circumplex quadrant."""
    t = np.asarray(t_us, dtype=np.int64)
    m = t >= start_us
    v = series["valence"][m]
    a = series["arousal"][m]
    ok = np.isfinite(v) & np.isfinite(a)
    if ok.sum() < 5:
        return {"valence_mean": None, "arousal_mean": None}
    v, a = v[ok], a[ok]
    dead = 0.15
    return {
        "valence_mean": round(float(np.mean(v)), 3),
        "arousal_mean": round(float(np.mean(a)), 3),
        "positive_share": round(float(np.mean(v > dead)), 3),
        "negative_share": round(float(np.mean(v < -dead)), 3),
        "activated_share": round(float(np.mean(a > dead)), 3),
        "calm_share": round(float(np.mean(a < -dead)), 3),
        "valence_trend_per_min": _trend(t[m][ok], v),
    }


def _trend(t: npt.NDArray[np.int64], x: npt.NDArray[np.float64]) -> float | None:
    if x.size < 20 or (t[-1] - t[0]) < 30_000_000:
        return None
    slope = np.polyfit((t - t[0]) / 6e7, x, 1)[0]
    return round(float(slope), 4)


class StreamingAffect:
    """Live counterpart: learns the calibration level, then reports smoothed valence and arousal."""

    def __init__(self, fps: float = 13.0) -> None:
        self._cal_v: list[float] = []
        self._cal_a: list[float] = []
        self.norm: tuple[float, float, float, float] | None = None
        self._buf_v: deque[float] = deque(maxlen=max(3, int(fps)))
        self._buf_a: deque[float] = deque(maxlen=max(3, int(fps)))

    @staticmethod
    def _raw(values: Mapping[str, float]) -> tuple[float, float]:
        arrs = {k: np.array([v], dtype=np.float64) for k, v in values.items()}
        v, a = raw_affect(arrs, 1)
        return float(v[0]), float(a[0])

    def learn(self, values: Mapping[str, float], quality: float) -> None:
        if quality < 0.4:
            return
        v, a = self._raw(values)
        if math.isfinite(v) and math.isfinite(a):
            self._cal_v.append(v)
            self._cal_a.append(a)

    def finish_learning(self) -> None:
        cv, ca = np.asarray(self._cal_v), np.asarray(self._cal_a)
        if cv.size < 10:
            self.norm = (0.0, 1.0, 0.0, 1.0)
            return
        mv = float(np.median(cv))
        ma = float(np.median(ca))
        sv = max(float(np.median(np.abs(cv - mv))) * 1.4826, SCALE_FLOOR)
        sa = max(float(np.median(np.abs(ca - ma))) * 1.4826, SCALE_FLOOR)
        self.norm = (mv, sv, ma, sa)

    def update(self, values: Mapping[str, float], quality: float) -> tuple[float, float] | None:
        if self.norm is None or quality < 0.4:
            return None
        v, a = self._raw(values)
        if not (math.isfinite(v) and math.isfinite(a)):
            return None
        mv, sv, ma, sa = self.norm
        self._buf_v.append((v - mv) / sv)
        self._buf_a.append((a - ma) / sa)
        return (
            math.tanh(float(np.median(self._buf_v)) / SOFT),
            math.tanh(float(np.median(self._buf_a)) / SOFT),
        )
