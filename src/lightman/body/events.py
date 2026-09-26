"""Body events: self-touch of the face and shoulder shrugs.

Self-touch ("self-adaptors") is folk-famous as a lying sign; the meta-analytic effect is about
zero (DePaulo et al. 2003, self-fidgeting d = -0.01). Shrugs accompany uncertainty and
dismissal. Both are reported as what the body did.
"""

from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt

from lightman.events.segments import segment_end_us
from lightman.schema.events import Event, EvidenceLevel, FeatureContribution

TOUCH_MAX = 0.1
TOUCH_MIN_MS = 400
SHRUG_MIN = 0.08
SHRUG_SD = 3.0
SHRUG_MS = (150, 2000)


def _event(
    kind: str, start: int, end: int, peak: int, value: float, center: float, scale: float,
    subject_id: str, extractor_id: str, baseline_quality: float, k: int,
) -> Event:  # fmt: skip
    dur = (end - start) / 1e6
    if kind == "touch":
        label = f"self-touch (face): {dur:.1f} s"
        desc = (
            f"A hand was at or on the face for {dur:.1f} s. Self-touch is widely believed to "
            "signal lying; meta-analyses find no such effect (self-fidgeting d = -0.01). It "
            "accompanies thinking, itching, fatigue and nerves."
        )
        feature, unit = "body.hand_face", "face_widths"
    else:
        label = f"shoulder shrug: {dur:.1f} s"
        desc = (
            f"Both shoulders rose for {dur:.1f} s ({center - value:.2f} face heights above their "
            "usual height). Shrugs accompany uncertainty, dismissal and emphasis."
        )
        feature, unit = "body.shoulder_y", "face_heights"
    return Event(
        event_id=f"ev_{k:05d}",
        subject_id=subject_id,
        source="video",
        event_type="self_touch" if kind == "touch" else "shrug",
        level=EvidenceLevel.OBSERVATION,
        start_us=start,
        end_us=end,
        peak_us=peak,
        label=label,
        description=desc,
        contributions=[
            FeatureContribution(
                feature=feature,
                unit=unit,
                peak_value=value,
                baseline_center=center,
                baseline_scale=max(1e-6, scale),
                peak_deviation=(value - center) / max(1e-6, scale),
                direction="decrease",
            )
        ],
        severity=round(min(10.0, 2.0 + dur), 2),
        confidence=0.6,
        quality=1.0,
        baseline_quality=baseline_quality,
        extractor_id=extractor_id,
        tags=["body", kind],
    )


def detect_body_events(
    *,
    t_us: npt.NDArray[np.integer],
    hand_face: npt.NDArray[np.floating],
    shoulder_y: npt.NDArray[np.floating],
    shoulder_center: float,
    shoulder_scale: float,
    start_us: int,
    subject_id: str,
    extractor_id: str,
    baseline_quality: float,
    id_start: int,
) -> list[Event]:
    t = np.asarray(t_us, dtype=np.int64)
    if t.size < 2:
        return []
    period = int(np.median(np.diff(t)))
    out: list[Event] = []
    k = id_start
    hf = np.asarray(hand_face, dtype=float)
    touch = np.isfinite(hf) & (hf <= TOUCH_MAX) & (t >= start_us)
    sy = np.asarray(shoulder_y, dtype=float)
    thr = max(SHRUG_MIN, SHRUG_SD * shoulder_scale) if math.isfinite(shoulder_scale) else SHRUG_MIN
    shrug = (
        np.isfinite(sy) & (sy < shoulder_center - thr) & (t >= start_us)
        if math.isfinite(shoulder_center)
        else np.zeros(t.shape, dtype=bool)
    )
    for kind, mask in (("touch", touch), ("shrug", shrug)):
        i = 0
        while i < t.size:
            if not mask[i]:
                i += 1
                continue
            j = i
            while j + 1 < t.size and mask[j + 1]:
                j += 1
            s, e = int(t[i]), segment_end_us(t, j, period)
            ms = (e - s) / 1000
            ok = ms >= TOUCH_MIN_MS if kind == "touch" else SHRUG_MS[0] <= ms <= SHRUG_MS[1]
            if ok:
                seg = hf[i : j + 1] if kind == "touch" else sy[i : j + 1]
                pk = int(np.nanargmin(seg))
                out.append(
                    _event(
                        kind,
                        s,
                        e,
                        int(t[i + pk]),
                        float(seg[pk]),
                        0.0 if kind == "touch" else shoulder_center,
                        TOUCH_MAX if kind == "touch" else thr / SHRUG_SD,
                        subject_id,
                        extractor_id,
                        baseline_quality,
                        k,
                    )
                )
                k += 1
            i = j + 1
    out.sort(key=lambda e: e.start_us)
    return out


class StreamingBodyEvents:
    def __init__(
        self,
        *,
        shoulder_center: float,
        shoulder_scale: float,
        subject_id: str,
        extractor_id: str,
        baseline_quality: float,
        id_start: int,
        frame_period_us: int,
    ) -> None:
        self.center = shoulder_center
        self.scale = shoulder_scale
        self.thr = (
            max(SHRUG_MIN, SHRUG_SD * shoulder_scale)
            if math.isfinite(shoulder_scale)
            else SHRUG_MIN
        )
        self.subject_id = subject_id
        self.extractor_id = extractor_id
        self.baseline_quality = baseline_quality
        self._k = id_start
        self.period_us = frame_period_us
        self._run: dict[str, tuple[int, int, float]] = {}  # kind -> (start, peak_t, peak_value)
        self.touching = False

    def update(self, t_us: int, hand_face: float, shoulder_y: float) -> list[Event]:
        out: list[Event] = []
        states = {
            "touch": math.isfinite(hand_face) and hand_face <= TOUCH_MAX,
            "shrug": math.isfinite(shoulder_y)
            and math.isfinite(self.center)
            and shoulder_y < self.center - self.thr,
        }
        self.touching = states["touch"]
        vals = {"touch": hand_face, "shrug": shoulder_y}
        for kind, on in states.items():
            run = self._run.get(kind)
            if on:
                if run is None:
                    self._run[kind] = (t_us, t_us, vals[kind])
                elif vals[kind] < run[2]:
                    self._run[kind] = (run[0], t_us, vals[kind])
            elif run is not None:
                out += self._close(kind, run, t_us)
                del self._run[kind]
        return out

    def _close(self, kind: str, run: tuple[int, int, float], end: int) -> list[Event]:
        s, pk, v = run
        ms = (end - s) / 1000
        ok = ms >= TOUCH_MIN_MS if kind == "touch" else SHRUG_MS[0] <= ms <= SHRUG_MS[1]
        if not ok:
            return []
        ev = _event(
            kind,
            s,
            end,
            pk,
            v,
            0.0 if kind == "touch" else self.center,
            TOUCH_MAX if kind == "touch" else self.thr / SHRUG_SD,
            self.subject_id,
            self.extractor_id,
            self.baseline_quality,
            self._k,
        )
        self._k += 1
        return [ev]

    def flush(self, t_us: int) -> list[Event]:
        out: list[Event] = []
        for kind, run in list(self._run.items()):
            out += self._close(kind, run, t_us + self.period_us)
        self._run.clear()
        return out
