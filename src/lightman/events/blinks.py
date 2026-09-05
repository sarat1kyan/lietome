"""Blink detection from the Eye Aspect Ratio time series.

Threshold is subject-relative when a baseline exists (EAR below 70 % of the subject's own
median open-eye EAR) and falls back to an absolute constant otherwise. Closures longer than
``blink_max_ms`` are reported as "eye closure" rather than blinks.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from lightman.baseline.robust import BaselineSnapshot
from lightman.config import EventsConfig
from lightman.events.segments import (
    hysteresis_segments,
    median_frame_period_us,
    segment_end_us,
)
from lightman.schema.events import Event, EvidenceLevel, FeatureContribution

RELATIVE_CLOSED_FRACTION = 0.7
EAR_SIGNAL = "eye.aspect_ratio_mean"


def blink_threshold(baseline: BaselineSnapshot | None, cfg: EventsConfig) -> float:
    if baseline and EAR_SIGNAL in baseline.signals:
        center = baseline.signals[EAR_SIGNAL].center
        if np.isfinite(center) and center > 0:
            return min(cfg.blink_ear_threshold, RELATIVE_CLOSED_FRACTION * center)
    return cfg.blink_ear_threshold


def detect_blinks(
    *,
    t_us: npt.NDArray[np.integer],
    quality: npt.NDArray[np.floating],
    ear: npt.NDArray[np.floating],
    baseline: BaselineSnapshot | None,
    cfg: EventsConfig,
    subject_id: str,
    extractor_id: str,
    id_start: int = 0,
) -> list[Event]:
    thr = blink_threshold(baseline, cfg)
    period = median_frame_period_us(t_us)
    # Score = how far below threshold; >0 means closed. Use hysteresis with a tiny margin.
    score = np.where(np.isfinite(ear), thr - ear, np.nan)
    ok = np.asarray(quality >= cfg.min_frame_quality, dtype=np.bool_)
    segs = hysteresis_segments(score, ok, enter=0.0, exit_=-0.005)
    events: list[Event] = []
    k = id_start
    center = (
        baseline.signals[EAR_SIGNAL].center
        if baseline and EAR_SIGNAL in baseline.signals
        else float("nan")
    )
    scale = (
        baseline.signals[EAR_SIGNAL].scale
        if baseline and EAR_SIGNAL in baseline.signals
        else float("nan")
    )
    for s in segs:
        start = int(t_us[s.start_idx])
        end = segment_end_us(t_us, s.end_idx, period)
        dur_ms = (end - start) / 1000
        if dur_ms < cfg.blink_min_ms:
            continue
        is_blink = dur_ms <= cfg.blink_max_ms
        min_ear = float(np.nanmin(ear[s.start_idx : s.end_idx + 1]))
        q = float(np.nanmean(quality[s.start_idx : s.end_idx + 1]))
        dev = (min_ear - center) / scale if np.isfinite(center) and scale > 0 else float("nan")
        contrib = FeatureContribution(
            feature=EAR_SIGNAL,
            unit="ratio",
            peak_value=min_ear,
            baseline_center=center if np.isfinite(center) else 0.0,
            baseline_scale=scale if np.isfinite(scale) else 0.0,
            peak_deviation=dev if np.isfinite(dev) else 0.0,
            direction="decrease",
        )
        events.append(
            Event(
                event_id=f"ev_{k:05d}",
                subject_id=subject_id,
                source="video",
                event_type="blink" if is_blink else "eye_closure",
                level=EvidenceLevel.INTERPRETATION,
                start_us=start,
                end_us=end,
                peak_us=int(t_us[s.peak_idx]),
                label="blink" if is_blink else f"eye closure {dur_ms:.0f} ms",
                description=(
                    f"Eye aspect ratio fell to {min_ear:.3f} (threshold {thr:.3f}) "
                    f"for {dur_ms:.0f} ms"
                ),
                contributions=[contrib],
                severity=abs(dev) if np.isfinite(dev) else 0.0,
                confidence=min(1.0, q),
                quality=q,
                baseline_quality=baseline.quality if baseline else 0.0,
                extractor_id=extractor_id,
                tags=["eye"],
            )
        )
        k += 1
    return events
