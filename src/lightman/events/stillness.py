"""Stillness episodes: the head stays nearly motionless for several seconds.

Reduced movement is one of the few nonverbal cues with a consistent (small) direction in the
deception meta-analyses (illustrators d = -0.14; DePaulo et al. 2003), and it is also what
concentration, listening and fatigue look like. The episode is reported with its duration and
the speed it fell to, relative to this person's usual head speed.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from lightman.events.segments import segment_end_us
from lightman.schema.events import Event, EvidenceLevel, FeatureContribution

MIN_S = 3.0


def stillness_threshold(center_speed_deg_s: float) -> float:
    """Speed below which the head counts as still: 35% of this person's usual speed,
    clamped to 1-3 deg/s."""
    if not np.isfinite(center_speed_deg_s):
        return 2.0
    return float(max(1.0, min(3.0, 0.35 * center_speed_deg_s)))


def stillness_event(
    *,
    start_us: int,
    end_us: int,
    mean_speed: float,
    center: float,
    threshold: float,
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
        event_type="stillness",
        level=EvidenceLevel.OBSERVATION,
        start_us=start_us,
        end_us=end_us,
        peak_us=start_us,
        label=f"stillness: {dur_s:.1f} s",
        description=(
            f"Head speed stayed under {threshold:.1f} deg/s for {dur_s:.1f} s (mean "
            f"{mean_speed:.1f} against a usual {center:.1f} deg/s). Listening, concentrating "
            "and fatigue produce the same stillness; the literature links reduced movement to "
            "deception only weakly."
        ),
        contributions=[
            FeatureContribution(
                feature="head.speed_deg_s",
                unit="deg_s",
                peak_value=mean_speed,
                baseline_center=center,
                baseline_scale=max(1.0, center * 0.5),
                peak_deviation=(mean_speed - center) / max(1.0, center * 0.5),
                direction="decrease",
            )
        ],
        severity=round(min(10.0, dur_s / 2.0), 2),
        confidence=round(0.7 * min(1.0, quality), 3),
        quality=float(quality),
        baseline_quality=baseline_quality,
        extractor_id=extractor_id,
        tags=["stillness"],
    )


def detect_stillness(
    *,
    t_us: npt.NDArray[np.integer],
    quality: npt.NDArray[np.floating],
    speed_deg_s: npt.NDArray[np.floating],
    center_speed: float,
    start_us: int,
    subject_id: str,
    extractor_id: str,
    baseline_quality: float,
    id_start: int,
    min_s: float = MIN_S,
    min_quality: float = 0.4,
) -> list[Event]:
    """Episodes after ``start_us`` (calibration end) where speed stays under the threshold."""
    t = np.asarray(t_us, dtype=np.int64)
    n = t.size
    if n < 2:
        return []
    period = int(np.median(np.diff(t)))
    sp = np.asarray(speed_deg_s, dtype=float)
    q = np.asarray(quality, dtype=float)
    thr = stillness_threshold(center_speed)
    still = np.isfinite(sp) & (sp < thr) & (q >= min_quality) & (t >= start_us)
    out: list[Event] = []
    k = id_start
    i = 0
    while i < n:
        if not still[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and still[j + 1]:
            j += 1
        s, e = int(t[i]), segment_end_us(t, j, period)
        if e - s >= int(min_s * 1e6):
            out.append(
                stillness_event(
                    start_us=s,
                    end_us=e,
                    mean_speed=float(np.mean(sp[i : j + 1])),
                    center=float(center_speed),
                    threshold=thr,
                    quality=float(np.mean(q[i : j + 1])),
                    subject_id=subject_id,
                    extractor_id=extractor_id,
                    baseline_quality=baseline_quality,
                    k=k,
                )
            )
            k += 1
        i = j + 1
    return out


class StreamingStillness:
    def __init__(
        self,
        *,
        center_speed: float,
        subject_id: str,
        extractor_id: str,
        baseline_quality: float,
        id_start: int,
        frame_period_us: int,
        min_s: float = MIN_S,
        min_quality: float = 0.4,
    ) -> None:
        self.center = float(center_speed)
        self.thr = stillness_threshold(center_speed)
        self.subject_id = subject_id
        self.extractor_id = extractor_id
        self.baseline_quality = baseline_quality
        self._k = id_start
        self.period_us = frame_period_us
        self.min_us = int(min_s * 1e6)
        self.min_quality = min_quality
        self._start: int | None = None
        self._speeds: list[float] = []
        self._qs: list[float] = []
        self.active_since_us: int | None = None

    def update(self, t_us: int, quality: float, speed: float) -> list[Event]:
        still = np.isfinite(speed) and speed < self.thr and quality >= self.min_quality
        if self._start is None:
            if still:
                self._start = t_us
                self.active_since_us = t_us
                self._speeds, self._qs = [speed], [quality]
            return []
        if still:
            self._speeds.append(speed)
            self._qs.append(quality)
            return []
        return self._close(t_us)

    def _close(self, end_us: int) -> list[Event]:
        start = self._start
        self._start = None
        self.active_since_us = None
        if start is None or end_us - start < self.min_us:
            return []
        ev = stillness_event(
            start_us=start,
            end_us=end_us,
            mean_speed=float(np.mean(self._speeds)),
            center=self.center,
            threshold=self.thr,
            quality=float(np.mean(self._qs)),
            subject_id=self.subject_id,
            extractor_id=self.extractor_id,
            baseline_quality=self.baseline_quality,
            k=self._k,
        )
        self._k += 1
        return [ev]

    def flush(self, t_us: int) -> list[Event]:
        return self._close(t_us + self.period_us) if self._start is not None else []
