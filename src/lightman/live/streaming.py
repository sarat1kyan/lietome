"""Streaming counterparts of the offline baseline and detectors.

Same statistics and thresholds as the offline path (median/MAD baseline, hysteresis
deviations, subject-relative blinks), applied frame by frame with explicit state. Differences
from offline are deliberate and documented: the baseline freezes after the calibration window,
events are emitted when they close (or when they exceed ``emit_open_after_ms`` while still
open), and no merge-gap post-processing is applied.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

import numpy as np

from lightman.baseline.robust import (
    STATE_ALL,
    STATE_SILENT,
    STATE_SPEAKING,
    BaselineSnapshot,
    SignalBaseline,
    robust_center_scale,
)
from lightman.config import BaselineConfig, EventsConfig
from lightman.events.deviation import _label_for
from lightman.features.table import signal_unit
from lightman.schema.events import Event, EvidenceLevel, FeatureContribution


class StreamingBaseline:
    """Collects quality-gated samples for ``window_s`` seconds, then freezes."""

    def __init__(self, cfg: BaselineConfig, signals: list[str]) -> None:
        self.cfg = cfg
        self.signals = list(dict.fromkeys(signals))  # dedupe: a repeated name would double-append
        self._values: dict[str, list[float]] = {s: [] for s in self.signals}
        self._quality: list[float] = []
        self._states: list[str] = []
        self._n_window = 0
        self._last_t_us = 0
        self.snapshot: BaselineSnapshot | None = None
        self.state_snapshots: dict[str, BaselineSnapshot] = {}

    @property
    def ready(self) -> bool:
        return self.snapshot is not None

    def update(
        self, t_us: int, quality: float, values: Mapping[str, float], *, speaking: bool = False
    ) -> bool:
        """Feed one frame. Returns True the moment the baseline becomes ready."""
        if self.ready:
            return False
        window_end = round(self.cfg.window_s * 1_000_000)
        self._last_t_us = t_us
        if t_us <= window_end:
            self._n_window += 1
            if quality >= self.cfg.min_quality:
                self._quality.append(quality)
                self._states.append(STATE_SPEAKING if speaking else STATE_SILENT)
                for s in self.signals:
                    self._values[s].append(float(values.get(s, math.nan)))
            return False
        self.finalize()
        return True

    def _snapshot_for(self, mask: np.ndarray, state: str) -> BaselineSnapshot | None:
        n_used = int(mask.sum())
        if n_used < self.cfg.min_samples:
            return None
        per_signal: dict[str, SignalBaseline] = {}
        for s in self.signals:
            unit = signal_unit(s)
            vals = np.asarray(self._values[s])[mask]
            center, scale, n, floored = robust_center_scale(vals, unit)
            per_signal[s] = SignalBaseline(
                feature=s, unit=unit, center=center, scale=scale, n=n, floor_applied=floored
            )
        q = np.asarray(self._quality)[mask]
        size_term = min(1.0, n_used / self.cfg.good_samples) if self.cfg.good_samples else 0.0
        return BaselineSnapshot(
            mode="leading_window",
            state=state,
            window_start_us=0,
            window_end_us=self._last_t_us,
            frames_in_window=self._n_window,
            frames_used=n_used,
            quality=max(0.0, min(1.0, size_term * float(q.mean()))),
            notes=[],
            signals=per_signal,
        )

    def finalize(self) -> None:
        if self.ready:
            return
        states = np.asarray(self._states, dtype=str)
        for state in (STATE_SILENT, STATE_SPEAKING):
            snap = self._snapshot_for(states == state, state) if states.size else None
            if snap is not None:
                self.state_snapshots[state] = snap
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
        if STATE_SPEAKING in self.state_snapshots:
            notes.append("separate speaking-state baseline available")
        self.snapshot = BaselineSnapshot(
            mode="leading_window",
            state=STATE_ALL,
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
    state: str | None = None
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
        state_baselines: Mapping[str, BaselineSnapshot] | None = None,
        center_scale: Callable[[str, str], tuple[float, float] | None] | None = None,
    ) -> None:
        self.cfg = cfg
        self.baseline = baseline
        self.state_baselines: dict[str, BaselineSnapshot] = dict(state_baselines or {})
        self.center_scale = center_scale
        """Optional (state, signal) -> (center, scale) provider, e.g. an adaptive baseline."""
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

    def _signal_baseline(self, name: str, state: str | None) -> SignalBaseline:
        if self.center_scale is not None:
            cs = self.center_scale(state or STATE_ALL, name)
            if cs is None and state:
                cs = self.center_scale(STATE_ALL, name)
            if cs is not None:
                base = self.baseline.signals[name]
                return base.model_copy(update={"center": cs[0], "scale": cs[1]})
        if state and state in self.state_baselines:
            sb = self.state_baselines[state].signals.get(name)
            if sb is not None and math.isfinite(sb.center) and math.isfinite(sb.scale):
                return sb
        return self.baseline.signals[name]

    def _event(self, name: str, run: _OpenRun, end_us: int, *, provisional: bool) -> Event:
        sb = self._signal_baseline(name, run.state)
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
            tags=[
                name.split(".", maxsplit=1)[0],
                *([run.state] if run.state and run.state in self.state_baselines else []),
                *(["provisional"] if provisional else []),
            ],
        )

    def update(
        self,
        t_us: int,
        quality: float,
        values: Mapping[str, float],
        *,
        state: str | None = None,
        suppress_prefixes: tuple[str, ...] = (),
    ) -> list[Event]:
        out: list[Event] = []
        ok = quality >= self.cfg.min_frame_quality
        self._last_t_us = t_us
        for name in self.cfg.signals:
            base_sb = self.baseline.signals.get(name)
            if base_sb is None or not math.isfinite(base_sb.center):
                continue
            sb = self._signal_baseline(name, state)
            v = float(values.get(name, math.nan))
            z = (v - sb.center) / sb.scale if math.isfinite(v) else math.nan
            valid = ok and math.isfinite(z) and not name.startswith(suppress_prefixes)
            enter, exit_ = self.cfg.thresholds_for(name)
            run = self._open.get(name)
            if run is None:
                if valid and abs(z) >= enter:
                    self._open[name] = _OpenRun(t_us, t_us, z, v, [quality], state=state)
            elif not valid or abs(z) < exit_:
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

    @property
    def eyes_closed(self) -> bool:
        return self._start is not None

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


MOUTH_SIGNAL_PREFIXES: tuple[str, ...] = (
    "blendshape.jaw",
    "blendshape.mouth",
    "au.AU10",
    "au.AU12",
    "au.AU13",
    "au.AU14",
    "au.AU15",
    "au.AU16",
    "au.AU17",
    "au.AU18",
    "au.AU20",
    "au.AU22",
    "au.AU23",
    "au.AU24",
    "au.AU25",
    "au.AU26",
    "au.AU27",
    "au.AU28",
)


def is_mouth_signal(name: str) -> bool:
    return name.startswith(MOUTH_SIGNAL_PREFIXES)


def tag_speaking(event: Event) -> Event:
    """Mark a mouth-region video event that happened while the subject was speaking.

    Speech moves the jaw and lips; such deviations describe articulation, not expression.
    Confidence is halved and the tag lets the UI fold them away.
    """
    if event.source != "video" or "speaking" in event.tags:
        return event
    if not any(is_mouth_signal(c.feature) for c in event.contributions):
        return event
    return event.model_copy(
        update={"tags": [*event.tags, "speaking"], "confidence": round(event.confidence * 0.5, 3)}
    )


class StreamingEpisodes:
    """Group overlapping per-signal deviation events into INTERPRETATION-level episodes.

    An episode opens with the first deviation event and stays open while new events start
    before ``gap_us`` after the last one ended. Closing emits one event whose contributions
    are the per-signal peaks. Same claim as the offline cluster: several measured signals
    departed from baseline together; nothing about psychological state.
    """

    def __init__(
        self,
        *,
        subject_id: str,
        extractor_id: str,
        gap_us: int = 400_000,
        min_signals: int = 2,
        id_start: int = 300_000,
    ) -> None:
        self.subject_id = subject_id
        self.extractor_id = extractor_id
        self.gap_us = gap_us
        self.min_signals = min_signals
        self._k = id_start
        self._members: list[Event] = []
        self._end_us = 0

    def add(self, events: list[Event], now_us: int) -> list[Event]:
        out: list[Event] = []
        for e in events:
            if e.event_type != "baseline_deviation":
                continue
            if self._members and e.start_us > self._end_us + self.gap_us:
                out += self._close()
            self._members.append(e)
            self._end_us = max(self._end_us, e.end_us)
        if self._members and now_us > self._end_us + self.gap_us:
            out += self._close()
        return out

    def flush(self) -> list[Event]:
        return self._close()

    def _close(self) -> list[Event]:
        members, self._members = self._members, []
        if not members:
            return []
        feats = {c.feature for e in members for c in e.contributions}
        if len(feats) < self.min_signals:
            return []
        best: dict[str, FeatureContribution] = {}
        for e in members:
            for c in e.contributions:
                prev = best.get(c.feature)
                if prev is None or abs(c.peak_deviation) > abs(prev.peak_deviation):
                    best[c.feature] = c
        contribs = sorted(best.values(), key=lambda c: abs(c.peak_deviation), reverse=True)
        speaking = sum("speaking" in e.tags for e in members)
        sources = {e.source for e in members}
        eid = f"ev_{self._k:05d}"
        self._k += 1
        tags = sorted({t for e in members for t in e.tags if t != "provisional"})
        if speaking and speaking >= len(members) / 2:
            tags = sorted({*tags, "speaking"})
        return [
            Event(
                event_id=eid,
                subject_id=self.subject_id,
                source="multimodal" if len(sources) > 1 else next(iter(sources)),
                event_type="episode",
                level=EvidenceLevel.INTERPRETATION,
                start_us=min(e.start_us for e in members),
                end_us=max(e.end_us for e in members),
                peak_us=max(members, key=lambda e: e.severity).peak_us,
                label=f"episode: {len(feats)} signals deviate together",
                description=(
                    "Several measured signals departed from baseline in the same interval. "
                    "This describes measured motion or voice only; it does not establish any "
                    "psychological state."
                ),
                contributions=contribs[:12],
                severity=max(e.severity for e in members),
                confidence=float(np.mean([e.confidence for e in members])),
                quality=float(np.mean([e.quality for e in members])),
                baseline_quality=members[0].baseline_quality,
                extractor_id=self.extractor_id,
                tags=tags,
            )
        ]
