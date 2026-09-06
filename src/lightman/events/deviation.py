"""Baseline-deviation events: per-signal robust-z excursions with hysteresis, and
INTERPRETATION-level clusters when several signals deviate at the same time."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import numpy.typing as npt

from lightman.baseline.robust import BaselineSnapshot, per_frame_center_scale, robust_z
from lightman.config import EventsConfig
from lightman.events.segments import (
    hysteresis_segments,
    median_frame_period_us,
    merge_close_segments,
    segment_end_us,
)
from lightman.features.action_units import au_description
from lightman.features.blendshapes import au_hint
from lightman.schema.events import Event, EvidenceLevel, FeatureContribution


def _label_for(signal: str, direction: str) -> str:
    if signal.startswith("blendshape."):
        name = signal.split(".", 1)[1]
        hint = au_hint(name)
        base = f"{name} {direction}"
        return f"{base} - {hint}" if hint else base
    if signal.startswith("au."):
        name = signal.split(".", 1)[1]
        desc = au_description(name)
        return f"{name} {desc} {direction}" if desc else f"{name} {direction}"
    if signal.startswith("head."):
        return f"head {signal.split('.', 1)[1].replace('_deg', '')} {direction}"
    if signal.startswith("eye."):
        return f"eye openness {direction}"
    if signal == "voice.f0_hz":
        return f"voice pitch {direction}"
    if signal == "voice.energy_db":
        return f"voice loudness {direction}"
    return f"{signal} {direction}"


def detect_deviation_events(
    *,
    t_us: npt.NDArray[np.integer],
    quality: npt.NDArray[np.floating],
    signals: dict[str, npt.NDArray[np.floating]],
    baseline: BaselineSnapshot,
    cfg: EventsConfig,
    subject_id: str,
    extractor_id: str,
    id_start: int = 0,
    exclude_intervals: list[tuple[int, int]] | None = None,
    exclude_signal_prefixes: tuple[str, ...] = ("eye.",),
    source: str = "video",
    state_baselines: Mapping[str, BaselineSnapshot] | None = None,
    frame_state: npt.NDArray[np.str_] | None = None,
) -> list[Event]:
    """One OBSERVATION-level event per sustained per-signal excursion.

    ``exclude_intervals`` (e.g. detected blinks) suppress events for signals whose name
    starts with one of ``exclude_signal_prefixes`` so a blink is not double-reported as an
    eye-openness deviation. Other signals are unaffected.
    """
    period = median_frame_period_us(t_us)
    ok = np.asarray(quality >= cfg.min_frame_quality, dtype=np.bool_)
    events: list[Event] = []
    k = id_start
    for name in cfg.signals:
        if name not in signals or name not in baseline.signals:
            continue
        exclude = (exclude_intervals or []) if name.startswith(exclude_signal_prefixes) else []
        sb = baseline.signals[name]
        if state_baselines is not None and frame_state is not None:
            center_arr, scale_arr, _ = per_frame_center_scale(name, state_baselines, frame_state)
            z = robust_z(signals[name], center_arr, scale_arr)
        else:
            center_arr = np.full(t_us.shape, sb.center)
            scale_arr = np.full(t_us.shape, sb.scale)
            z = robust_z(signals[name], sb.center, sb.scale)
        segs = hysteresis_segments(np.abs(z), ok, enter=cfg.z_enter, exit_=cfg.z_exit)
        segs = merge_close_segments(segs, t_us, cfg.merge_gap_ms * 1000)
        for s in segs:
            start = int(t_us[s.start_idx])
            end = segment_end_us(t_us, s.end_idx, period)
            if end - start < cfg.min_duration_ms * 1000:
                continue
            if any(start >= a and end <= b for a, b in exclude):
                continue
            peak_z = float(z[s.peak_idx])
            direction = "increase" if peak_z > 0 else "decrease"
            contrib = FeatureContribution(
                feature=name,
                unit=sb.unit,
                peak_value=float(signals[name][s.peak_idx]),
                baseline_center=float(center_arr[s.peak_idx]),
                baseline_scale=float(scale_arr[s.peak_idx]),
                peak_deviation=peak_z,
                direction=direction,
            )
            state_tag = (
                [str(frame_state[s.peak_idx])]
                if frame_state is not None
                and str(frame_state[s.peak_idx]) in state_baselines_keys(state_baselines)
                else []
            )
            q = float(np.nanmean(quality[s.start_idx : s.end_idx + 1]))
            events.append(
                Event(
                    event_id=f"ev_{k:05d}",
                    subject_id=subject_id,
                    source=source,
                    event_type="baseline_deviation",
                    level=EvidenceLevel.OBSERVATION,
                    start_us=start,
                    end_us=end,
                    peak_us=int(t_us[s.peak_idx]),
                    label=_label_for(name, direction),
                    description=(
                        f"{name} reached {contrib.peak_value:.3f} {sb.unit} "
                        f"({peak_z:+.1f} robust SD from baseline median "
                        f"{contrib.baseline_center:.3f}"
                        + (f", {state_tag[0]} state" if state_tag else "")
                        + ")"
                    ),
                    contributions=[contrib],
                    severity=abs(peak_z),
                    confidence=min(1.0, q),
                    quality=q,
                    baseline_quality=baseline.quality,
                    extractor_id=extractor_id,
                    tags=[name.split(".")[0], *state_tag],
                )
            )
            k += 1
    return events


def state_baselines_keys(sb: Mapping[str, BaselineSnapshot] | None) -> set[str]:
    return {k for k in (sb or {}) if k != "all"}


def cluster_cooccurring(
    events: list[Event],
    *,
    min_signals: int = 2,
    subject_id: str,
    extractor_id: str,
    id_start: int,
) -> list[Event]:
    """Group overlapping per-signal deviation events into INTERPRETATION-level clusters.

    A cluster says only: "several measured signals departed from baseline together".
    It does not name an emotion or a state.
    """
    dev = sorted(
        (e for e in events if e.event_type == "baseline_deviation"), key=lambda e: e.start_us
    )
    clusters: list[list[Event]] = []
    for e in dev:
        if clusters and e.start_us <= max(x.end_us for x in clusters[-1]):
            clusters[-1].append(e)
        else:
            clusters.append([e])
    out: list[Event] = []
    k = id_start
    for group in clusters:
        feats = {c.feature for e in group for c in e.contributions}
        if len(feats) < min_signals:
            continue
        contribs = sorted(
            (c for e in group for c in e.contributions),
            key=lambda c: abs(c.peak_deviation),
            reverse=True,
        )
        start = min(e.start_us for e in group)
        end = max(e.end_us for e in group)
        peak_event = max(group, key=lambda e: e.severity)
        out.append(
            Event(
                event_id=f"ev_{k:05d}",
                subject_id=subject_id,
                source="video",
                event_type="multi_signal_deviation",
                level=EvidenceLevel.INTERPRETATION,
                start_us=start,
                end_us=end,
                peak_us=peak_event.peak_us,
                label=f"co-occurring deviation across {len(feats)} signals",
                description=(
                    "Several facial/head signals departed from baseline in the same interval. "
                    "This describes measured motion only; it does not establish any "
                    "psychological state."
                ),
                contributions=contribs,
                severity=max(e.severity for e in group),
                confidence=float(np.mean([e.confidence for e in group])),
                quality=float(np.mean([e.quality for e in group])),
                baseline_quality=group[0].baseline_quality,
                extractor_id=extractor_id,
                tags=sorted({t for e in group for t in e.tags}),
            )
        )
        k += 1
    return out
