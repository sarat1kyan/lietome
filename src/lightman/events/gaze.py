"""Sustained gaze-away episodes.

The gaze proxy comes from MediaPipe eye-look blendshapes (horizontal: subject's left positive;
vertical: up positive) plus head yaw. A gaze-away episode is a run of frames where the eyes or
the head point well off the camera for at least ``min_ms``. The event says where the gaze went
and for how long; looking away accompanies thinking, reading, and discomfort alike, and
conversational gaze aversion is normal (people look away while formulating answers).
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from lightman.events.segments import segment_end_us
from lightman.schema.events import Event, EvidenceLevel, FeatureContribution

GAZE_MAG_ENTER = 0.45
GAZE_MAG_EXIT = 0.30
HEAD_YAW_ENTER_DEG = 25.0
HEAD_YAW_EXIT_DEG = 18.0


def _direction(h: float, v: float, yaw: float) -> str:
    parts: list[str] = []
    horiz = h + yaw / 40.0  # yaw 20 deg adds 0.5 to the horizontal proxy
    if abs(horiz) >= 0.25:
        parts.append("left" if horiz > 0 else "right")
    if abs(v) >= 0.25:
        parts.append("up" if v > 0 else "down")
    return " and ".join(parts) or "away"


def gaze_away_event(
    *,
    start_us: int,
    end_us: int,
    peak_us: int,
    direction: str,
    peak_mag: float,
    yaw_deg: float,
    quality: float,
    subject_id: str,
    extractor_id: str,
    baseline_quality: float,
    k: int,
) -> Event:
    dur_s = (end_us - start_us) / 1e6
    return Event(
        event_id=f"ev_{k:05d}",
        subject_id=subject_id,
        source="video",
        event_type="gaze_away",
        level=EvidenceLevel.OBSERVATION,
        start_us=start_us,
        end_us=end_us,
        peak_us=peak_us,
        label=f"gaze away ({direction}): {dur_s:.1f} s",
        description=(
            f"Eyes or head pointed {direction} of the camera for {dur_s:.1f} s "
            f"(gaze proxy {peak_mag:.2f}, head yaw {yaw_deg:.0f} deg). People look away while "
            "thinking, reading and listening; sustained aversion is described, not interpreted."
        ),
        contributions=[
            FeatureContribution(
                feature="gaze.magnitude",
                unit="coefficient",
                peak_value=peak_mag,
                baseline_center=0.0,
                baseline_scale=GAZE_MAG_ENTER,
                peak_deviation=peak_mag / GAZE_MAG_ENTER,
                direction="increase",
            )
        ],
        severity=round(min(10.0, dur_s), 2),
        confidence=round(0.7 * min(1.0, quality), 3),
        quality=float(quality),
        baseline_quality=baseline_quality,
        extractor_id=extractor_id,
        tags=["gaze", direction.split(" ", maxsplit=1)[0]],
    )


def detect_gaze_away(
    *,
    t_us: npt.NDArray[np.integer],
    quality: npt.NDArray[np.floating],
    gaze_h: npt.NDArray[np.floating],
    gaze_v: npt.NDArray[np.floating],
    yaw_deg: npt.NDArray[np.floating],
    subject_id: str,
    extractor_id: str,
    baseline_quality: float,
    id_start: int,
    min_ms: int = 1000,
    min_quality: float = 0.4,
) -> list[Event]:
    t = np.asarray(t_us, dtype=np.int64)
    n = t.size
    if n < 2:
        return []
    period = int(np.median(np.diff(t)))
    h = np.asarray(gaze_h, dtype=float)
    v = np.asarray(gaze_v, dtype=float)
    y = np.asarray(yaw_deg, dtype=float)
    q = np.asarray(quality, dtype=float)
    mag = np.hypot(h, v)
    ok = np.isfinite(mag) & (q >= min_quality)
    events: list[Event] = []
    k = id_start
    i = 0
    while i < n:
        away = ok[i] and (mag[i] >= GAZE_MAG_ENTER or abs(y[i]) >= HEAD_YAW_ENTER_DEG)
        if not away:
            i += 1
            continue
        j = i
        peak = i
        while (
            j + 1 < n
            and ok[j + 1]
            and (mag[j + 1] >= GAZE_MAG_EXIT or abs(y[j + 1]) >= HEAD_YAW_EXIT_DEG)
        ):
            j += 1
            if mag[j] + abs(y[j]) / 40.0 > mag[peak] + abs(y[peak]) / 40.0:
                peak = j
        start, end = int(t[i]), segment_end_us(t, j, period)
        if end - start >= min_ms * 1000:
            events.append(
                gaze_away_event(
                    start_us=start,
                    end_us=end,
                    peak_us=int(t[peak]),
                    direction=_direction(float(h[peak]), float(v[peak]), float(y[peak])),
                    peak_mag=float(mag[peak]),
                    yaw_deg=float(y[peak]),
                    quality=float(np.nanmean(q[i : j + 1])),
                    subject_id=subject_id,
                    extractor_id=extractor_id,
                    baseline_quality=baseline_quality,
                    k=k,
                )
            )
            k += 1
        i = j + 1
    return events


class StreamingGazeAway:
    """Same rule, one frame at a time; the event is emitted when the episode ends."""

    def __init__(
        self,
        *,
        subject_id: str,
        extractor_id: str,
        baseline_quality: float,
        id_start: int,
        frame_period_us: int,
        min_ms: int = 1000,
        min_quality: float = 0.4,
    ) -> None:
        self.subject_id = subject_id
        self.extractor_id = extractor_id
        self.baseline_quality = baseline_quality
        self._k = id_start
        self.period_us = frame_period_us
        self.min_us = min_ms * 1000
        self.min_quality = min_quality
        self._start: int | None = None
        self._peak: tuple[int, float, float, float, float] | None = None  # t, score, h, v, yaw
        self._qs: list[float] = []
        self.active_since_us: int | None = None

    def update(self, t_us: int, quality: float, h: float, v: float, yaw: float) -> list[Event]:
        mag = float(np.hypot(h, v)) if np.isfinite(h) and np.isfinite(v) else float("nan")
        ok = quality >= self.min_quality and np.isfinite(mag) and np.isfinite(yaw)
        if self._start is None:
            if ok and (mag >= GAZE_MAG_ENTER or abs(yaw) >= HEAD_YAW_ENTER_DEG):
                self._start = t_us
                self.active_since_us = t_us
                self._peak = (t_us, mag + abs(yaw) / 40.0, h, v, yaw)
                self._qs = [quality]
            return []
        if ok and (mag >= GAZE_MAG_EXIT or abs(yaw) >= HEAD_YAW_EXIT_DEG):
            score = mag + abs(yaw) / 40.0
            if self._peak is None or score > self._peak[1]:
                self._peak = (t_us, score, h, v, yaw)
            self._qs.append(quality)
            return []
        return self._close(t_us)

    def _close(self, end_us: int) -> list[Event]:
        start, peak = self._start, self._peak
        self._start = None
        self.active_since_us = None
        if start is None or peak is None or end_us - start < self.min_us:
            return []
        pt, _score, h, v, yaw = peak
        ev = gaze_away_event(
            start_us=start,
            end_us=end_us,
            peak_us=pt,
            direction=_direction(h, v, yaw),
            peak_mag=float(np.hypot(h, v)),
            yaw_deg=yaw,
            quality=float(np.mean(self._qs)) if self._qs else 0.0,
            subject_id=self.subject_id,
            extractor_id=self.extractor_id,
            baseline_quality=self.baseline_quality,
            k=self._k,
        )
        self._k += 1
        return [ev]

    def flush(self, t_us: int) -> list[Event]:
        return self._close(t_us + self.period_us) if self._start is not None else []
