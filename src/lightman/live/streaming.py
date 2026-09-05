"""Streaming counterparts of the offline baseline and detectors.

Same statistics and thresholds as the offline path (median/MAD baseline, hysteresis
deviations, subject-relative blinks), applied frame by frame with explicit state. Differences
from offline are deliberate and documented: the baseline freezes after the calibration window,
events are emitted when they close (or when they exceed ``emit_open_after_ms`` while still
open), and no merge-gap post-processing is applied.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np

from lightman.baseline.robust import BaselineSnapshot, SignalBaseline, robust_center_scale
from lightman.config import BaselineConfig, EventsConfig
from lightman.events.deviation import _label_for
from lightman.features.table import signal_unit
from lightman.schema.events import Event, EvidenceLevel, FeatureContribution


class StreamingBaseline:
    """Collects quality-gated samples for ``window_s`` seconds, then freezes."""

    def __init__(self, cfg: BaselineConfig, signals: list[str]) -> None:
        self.cfg = cfg
        self.signals = signals
        self._values: dict[str, list[float]] = {s: [] for s in signals}
        self._quality: list[float] = []
        self._n_window = 0
        self._last_t_us = 0
        self.snapshot: BaselineSnapshot | None = None

    @property
    def ready(self) -> bool:
        return self.snapshot is not None

    def update(self, t_us: int, quality: float, values: Mapping[str, float]) -> bool:
        """Feed one frame. Returns True the moment the baseline becomes ready."""
        if self.ready:
            return False
        window_end = round(self.cfg.window_s * 1_000_000)
        self._last_t_us = t_us
        if t_us <= window_end:
            self._n_window += 1
            if quality >= self.cfg.min_quality:
                self._quality.append(quality)
                for s in self.signals:
                    self._values[s].append(float(values.get(s, math.nan)))
            return False
        self.finalize()
        return True

    def finalize(self) -> None:
        if self.ready:
            return
        per_signal: dict[str, SignalBaseline] = {}
        for s in self.signals:
            unit = signal_unit(s)
            center, scale, n, floored = robust_center_scale(np.asarray(self._values[s]), unit)
            per_signal[s] = SignalBaseline(
                feature=s, unit=unit, center=center, scale=scale, n=n, floor_applied=floored
            )
        n_used = len(self._quality)
        size_term = min(1.0, n_used / self.cfg.good_samples) if self.cfg.good_samples else 0.0
        q_term = float(np.mean(self._quality)) if n_used else 0.0
        notes: list[str] = []
        if n_used < self.cfg.min_samples:
            notes.append(
                f"only {n_used} quality-gated frames in the calibration window; "
                "deviations are unreliable"
            )
        self.snapshot = BaselineSnapshot(
            mode="leading_window",
            window_start_us=0,
            window_end_us=self._last_t_us,
            frames_in_window=self._n_window,
            frames_used=n_used,
            quality=max(0.0, min(1.0, size_term * q_term)),
            notes=notes,
            signals=per_signal,
        )


@dataclass(slots=True)
class _OpenRun:
    start_us: int
    peak_us: int
    peak_z: float
    peak_value: float
    qualities: list[float] = field(default_factory=list)
    emitted_open: bool = False


class StreamingDeviationDetector:
    def __init__(
        self,
        cfg: EventsConfig,
        baseline: BaselineSnapshot,
        *,
        subject_id: str,
        extractor_id: str,
        frame_period_us: int,
        emit_open_after_ms: int = 1500,
        id_start: int = 0,
    ) -> None:
        self.cfg = cfg
        self.baseline = baseline
        self.subject_id = subject_id
        self.extractor_id = extractor_id
        self.period_us = frame_period_us
        self.emit_open_after_us = emit_open_after_ms * 1000
        self._k = id_start
        self._open: dict[str, _OpenRun] = {}
        self._last_t_us = 0

    def _next_id(self) -> str:
        eid = f"ev_{self._k:05d}"
        self._k += 1
        return eid

    def _event(self, name: str, run: _OpenRun, end_us: int, *, provisional: bool) -> Event:
        sb = self.baseline.signals[name]
        direction = "increase" if run.peak_z > 0 else "decrease"
        q = float(np.mean(run.qualities)) if run.qualities else 0.0
        return Event(
            event_id=self._next_id(),
            subject_id=self.subject_id,
            source="video",
            event_type="baseline_deviation",
            level=EvidenceLevel.OBSERVATION,
            start_us=run.start_us,
            end_us=end_us,
            peak_us=run.peak_us,
            label=_label_for(name, direction),
            description=(
                f"{name} reached {run.peak_value:.3f} {sb.unit} "
                f"({run.peak_z:+.1f} robust SD from baseline median {sb.center:.3f})"
                + (" [still open]" if provisional else "")
            ),
            contributions=[
                FeatureContribution(
                    feature=name,
                    unit=sb.unit,
                    peak_value=run.peak_value,
                    baseline_center=sb.center,
                    baseline_scale=sb.scale,
                    peak_deviation=run.peak_z,
                    direction=direction,
                )
            ],
            severity=abs(run.peak_z),
            confidence=min(1.0, q),
            quality=q,
            baseline_quality=self.baseline.quality,
            extractor_id=self.extractor_id,
            tags=[name.split(".", maxsplit=1)[0]] + (["provisional"] if provisional else []),
        )

    def update(self, t_us: int, quality: float, values: Mapping[str, float]) -> list[Event]:
        out: list[Event] = []
        ok = quality >= self.cfg.min_frame_quality
        self._last_t_us = t_us
        for name in self.cfg.signals:
            sb = self.baseline.signals.get(name)
            if sb is None or not math.isfinite(sb.center):
                continue
            v = float(values.get(name, math.nan))
            z = (v - sb.center) / sb.scale if math.isfinite(v) else math.nan
            valid = ok and math.isfinite(z)
            run = self._open.get(name)
            if run is None:
                if valid and abs(z) >= self.cfg.z_enter:
                    self._open[name] = _OpenRun(t_us, t_us, z, v, [quality])
            elif not valid or abs(z) < self.cfg.z_exit:
                end = t_us  # closes at the first non-qualifying frame
                if end - run.start_us >= self.cfg.min_duration_ms * 1000 and not run.emitted_open:
                    out.append(self._event(name, run, end, provisional=False))
                del self._open[name]
            else:
                run.qualities.append(quality)
                if abs(z) > abs(run.peak_z):
                    run.peak_z, run.peak_us, run.peak_value = z, t_us, v
                if not run.emitted_open and t_us - run.start_us >= self.emit_open_after_us:
                    out.append(self._event(name, run, t_us + self.period_us, provisional=True))
                    run.emitted_open = True
        return out

    def flush(self) -> list[Event]:
        """Close everything still open (end of stream)."""
        out: list[Event] = []
        end = self._last_t_us + self.period_us
        for name, run in list(self._open.items()):
            if end - run.start_us >= self.cfg.min_duration_ms * 1000 and not run.emitted_open:
                out.append(self._event(name, run, end, provisional=False))
        self._open.clear()
        return out


class StreamingBlinkDetector:
    def __init__(
        self,
        cfg: EventsConfig,
        threshold: float,
        *,
        baseline: BaselineSnapshot | None,
        subject_id: str,
        extractor_id: str,
        frame_period_us: int,
        id_start: int = 0,
    ) -> None:
        self.cfg = cfg
        self.threshold = threshold
        self.baseline = baseline
        self.subject_id = subject_id
        self.extractor_id = extractor_id
        self.period_us = frame_period_us
        self._k = id_start
        self._start: int | None = None
        self._min_ear = math.inf
        self._q: list[float] = []
        self.blink_count = 0

    def update(self, t_us: int, quality: float, ear: float) -> list[Event]:
        closed = (
            math.isfinite(ear) and ear < self.threshold and quality >= self.cfg.min_frame_quality
        )
        if closed:
            if self._start is None:
                self._start, self._min_ear, self._q = t_us, ear, []
            self._min_ear = min(self._min_ear, ear)
            self._q.append(quality)
            return []
        if self._start is None:
            return []
        start, min_ear, q = self._start, self._min_ear, self._q
        self._start = None
        dur_ms = (t_us - start) / 1000
        if dur_ms < self.cfg.blink_min_ms:
            return []
        is_blink = dur_ms <= self.cfg.blink_max_ms
        if is_blink:
            self.blink_count += 1
        sb = self.baseline.signals.get("eye.aspect_ratio_mean") if self.baseline else None
        center = sb.center if sb and math.isfinite(sb.center) else 0.0
        scale = sb.scale if sb and math.isfinite(sb.scale) else 0.0
        dev = (min_ear - center) / scale if scale > 0 else 0.0
        eid = f"ev_{self._k:05d}"
        self._k += 1
        qm = float(np.mean(q)) if q else 0.0
        return [
            Event(
                event_id=eid,
                subject_id=self.subject_id,
                source="video",
                event_type="blink" if is_blink else "eye_closure",
                level=EvidenceLevel.INTERPRETATION,
                start_us=start,
                end_us=t_us,
                peak_us=start,
                label="blink" if is_blink else f"eye closure {dur_ms:.0f} ms",
                description=(
                    f"Eye aspect ratio fell to {min_ear:.3f} (threshold {self.threshold:.3f}) "
                    f"for {dur_ms:.0f} ms"
                ),
                contributions=[
                    FeatureContribution(
                        feature="eye.aspect_ratio_mean",
                        unit="ratio",
                        peak_value=min_ear,
                        baseline_center=center,
                        baseline_scale=scale,
                        peak_deviation=dev,
                        direction="decrease",
                    )
                ],
                severity=abs(dev),
                confidence=min(1.0, qm),
                quality=qm,
                baseline_quality=self.baseline.quality if self.baseline else 0.0,
                extractor_id=self.extractor_id,
                tags=["eye"],
            )
        ]
