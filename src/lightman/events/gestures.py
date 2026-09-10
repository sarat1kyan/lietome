"""Head gestures: nods (pitch oscillation) and shakes (yaw oscillation).

A gesture is a run of at least three alternating extrema in the smoothed angle with per-swing
amplitude above a floor and swing intervals within the range people actually nod and shake at
(about 0.6-5 Hz). Events say what the head did; they carry no meaning by themselves (a nod is
also "yes", rhythm, emphasis and a glance at notes).
"""

from __future__ import annotations

import itertools
import warnings
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from lightman.schema.events import Event, EvidenceLevel, FeatureContribution

MIN_EXTREMA = 3
MIN_SWING_US = 100_000
MAX_SWING_US = 800_000


@dataclass(frozen=True, slots=True)
class Gesture:
    kind: str  # "nod" | "shake"
    start_us: int
    end_us: int
    cycles: float
    amplitude_deg: float
    peak_us: int


def _extrema(x: npt.NDArray[np.float64]) -> list[int]:
    d = np.diff(x)
    idx: list[int] = []
    last_sign = 0
    for i in range(d.size):
        s = 1 if d[i] > 0 else (-1 if d[i] < 0 else 0)
        if s == 0:
            continue
        if last_sign and s != last_sign:
            idx.append(i)
        last_sign = s
    return idx


def find_gestures(
    t_us: npt.NDArray[np.integer],
    angle_deg: npt.NDArray[np.floating],
    ok: npt.NDArray[np.bool_],
    *,
    kind: str,
    min_amplitude_deg: float,
) -> list[Gesture]:
    t = np.asarray(t_us, dtype=np.int64)
    x = np.asarray(angle_deg, dtype=np.float64).copy()
    x[~np.asarray(ok, dtype=bool)] = np.nan
    if x.size < 5:
        return []
    # light smoothing: 3-point median then mean; NaN stays NaN
    pad = np.pad(x, 1, mode="edge")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN rows are gaps, kept NaN
        med = np.nanmedian(np.column_stack([pad[:-2], pad[1:-1], pad[2:]]), axis=1)
    out: list[Gesture] = []
    # split on NaN gaps
    valid = np.isfinite(med)
    starts = np.flatnonzero(valid & ~np.roll(valid, 1))
    ends = np.flatnonzero(valid & ~np.roll(valid, -1))
    if valid[0]:
        starts = np.concatenate([[0], starts[starts != 0]])
    if valid[-1]:
        ends = np.concatenate([ends[ends != valid.size - 1], [valid.size - 1]])
    for a_, b_ in zip(starts, ends, strict=False):
        a, b = int(a_), int(b_)
        seg = med[a : b + 1]
        if seg.size < 5:
            continue
        ext = _extrema(seg)
        if len(ext) < MIN_EXTREMA:
            continue
        run: list[int] = [ext[0]]
        for i in ext[1:]:
            prev = run[-1]
            swing = abs(seg[i] - seg[prev])
            dt = int(t[a + i] - t[a + prev])
            if swing >= min_amplitude_deg and MIN_SWING_US <= dt <= MAX_SWING_US:
                run.append(i)
            else:
                out += _close(run, seg, t, a, kind)
                run = [i]
        out += _close(run, seg, t, a, kind)
    return out


def _close(
    run: list[int], seg: npt.NDArray[np.float64], t: npt.NDArray[np.int64], a: int, kind: str
) -> list[Gesture]:
    if len(run) < MIN_EXTREMA:
        return []
    swings = [abs(seg[j] - seg[i]) for i, j in itertools.pairwise(run)]
    amp = float(np.max(swings))
    peak_i = run[int(np.argmax(swings)) + 1]
    return [
        Gesture(
            kind=kind,
            start_us=int(t[a + run[0]]),
            end_us=int(t[a + run[-1]]),
            cycles=(len(run) - 1) / 2.0,
            amplitude_deg=amp,
            peak_us=int(t[a + peak_i]),
        )
    ]


def detect_head_gestures(
    *,
    t_us: npt.NDArray[np.integer],
    quality: npt.NDArray[np.floating],
    yaw_deg: npt.NDArray[np.floating],
    pitch_deg: npt.NDArray[np.floating],
    subject_id: str,
    extractor_id: str,
    baseline_quality: float,
    id_start: int,
    nod_min_deg: float = 3.0,
    shake_min_deg: float = 4.0,
    min_quality: float = 0.4,
) -> list[Event]:
    ok = np.asarray(quality, dtype=float) >= min_quality
    nods = find_gestures(t_us, pitch_deg, ok, kind="nod", min_amplitude_deg=nod_min_deg)
    shakes = find_gestures(t_us, yaw_deg, ok, kind="shake", min_amplitude_deg=shake_min_deg)
    # when both axes oscillate over the same span keep the larger one
    keep: list[Gesture] = []
    for g in sorted(nods + shakes, key=lambda g: g.start_us):
        clash = [
            h for h in keep if h.start_us < g.end_us and g.start_us < h.end_us and h.kind != g.kind
        ]
        if clash and max(h.amplitude_deg for h in clash) >= g.amplitude_deg:
            continue
        keep = [h for h in keep if h not in clash or h.amplitude_deg >= g.amplitude_deg]
        keep.append(g)
    events: list[Event] = []
    k = id_start
    for g in keep:
        events.append(gesture_event(g, subject_id, extractor_id, baseline_quality, k))
        k += 1
    return events


def gesture_event(
    g: Gesture, subject_id: str, extractor_id: str, baseline_quality: float, k: int
) -> Event:
    feature = "head.pitch_deg" if g.kind == "nod" else "head.yaw_deg"
    return Event(
        event_id=f"ev_{k:05d}",
        subject_id=subject_id,
        source="video",
        event_type="head_gesture",
        level=EvidenceLevel.OBSERVATION,
        start_us=g.start_us,
        end_us=g.end_us,
        peak_us=g.peak_us,
        label=f"head {g.kind}: {g.cycles:.1f} cycles, {g.amplitude_deg:.0f} deg",
        description=(
            f"The head {'moved up and down' if g.kind == 'nod' else 'turned side to side'} "
            f"{g.cycles:.1f} times over {(g.end_us - g.start_us) / 1000:.0f} ms with swings up to "
            f"{g.amplitude_deg:.0f} degrees. Nods and shakes accompany agreement, disagreement, "
            "rhythm, emphasis and listening; the movement alone does not say which."
        ),
        contributions=[
            FeatureContribution(
                feature=feature,
                unit="deg",
                peak_value=g.amplitude_deg,
                baseline_center=0.0,
                baseline_scale=1.0,
                peak_deviation=g.amplitude_deg,
                direction="increase",
            )
        ],
        severity=round(min(10.0, g.amplitude_deg / 2.0), 2),
        confidence=round(min(1.0, 0.5 + 0.15 * g.cycles), 3),
        quality=1.0,
        baseline_quality=baseline_quality,
        extractor_id=extractor_id,
        tags=["gesture", g.kind],
    )


class StreamingHeadGestures:
    """Runs the offline detector over a rolling buffer and emits each gesture once it has ended."""

    def __init__(
        self,
        *,
        subject_id: str,
        extractor_id: str,
        baseline_quality: float,
        id_start: int,
        buffer_s: float = 4.0,
        settle_us: int = 500_000,
        nod_min_deg: float = 3.0,
        shake_min_deg: float = 4.0,
    ) -> None:
        self.subject_id = subject_id
        self.extractor_id = extractor_id
        self.baseline_quality = baseline_quality
        self._k = id_start
        self.buffer_us = int(buffer_s * 1e6)
        self.settle_us = settle_us
        self.nod_min_deg = nod_min_deg
        self.shake_min_deg = shake_min_deg
        self._t: list[int] = []
        self._yaw: list[float] = []
        self._pitch: list[float] = []
        self._q: list[float] = []
        self._emitted_until: dict[str, int] = {"nod": 0, "shake": 0}

    def update(self, t_us: int, quality: float, yaw: float, pitch: float) -> list[Event]:
        self._t.append(t_us)
        self._yaw.append(yaw)
        self._pitch.append(pitch)
        self._q.append(quality)
        while self._t and self._t[0] < t_us - self.buffer_us:
            self._t.pop(0)
            self._yaw.pop(0)
            self._pitch.pop(0)
            self._q.pop(0)
        if len(self._t) < 6:
            return []
        t = np.asarray(self._t, dtype=np.int64)
        ok = np.asarray(self._q, dtype=float) >= 0.4
        found = find_gestures(
            t, np.asarray(self._pitch), ok, kind="nod", min_amplitude_deg=self.nod_min_deg
        ) + find_gestures(
            t, np.asarray(self._yaw), ok, kind="shake", min_amplitude_deg=self.shake_min_deg
        )
        out: list[Event] = []
        for g in sorted(found, key=lambda g: g.start_us):
            # emit only gestures that ended a while ago (so they are complete) and are new
            if t_us - g.end_us < self.settle_us or g.start_us < self._emitted_until[g.kind]:
                continue
            out.append(
                gesture_event(g, self.subject_id, self.extractor_id, self.baseline_quality, self._k)
            )
            self._k += 1
            self._emitted_until[g.kind] = g.end_us
        return out
