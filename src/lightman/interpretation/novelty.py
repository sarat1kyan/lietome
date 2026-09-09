"""Unfamiliar Action Unit pairings.

During calibration the detector records which pairs of Action Units are active together
(probability above a threshold, per frame). Afterwards, a frame whose active AUs include a
pairing never seen in calibration, held for a minimum time, is reported once, the first time
that pairing appears. It is a data-driven "this face has not combined these before in this
session" flag; it names the AUs and implies nothing about why.

Articulation-dominated AUs (lips part, upper lip raiser, dimpler, jaw drop and the unilateral
variants) are excluded: during speech they pair with everything.
"""

from __future__ import annotations

import itertools

import numpy as np
import numpy.typing as npt

from lightman.schema.events import Event, EvidenceLevel, FeatureContribution

WATCHED_AUS: tuple[str, ...] = tuple(
    f"au.AU{n}" for n in (1, 2, 4, 5, 6, 7, 9, 12, 15, 17, 20, 23, 24)
)


class AUNoveltyDetector:
    """Feed frames in time order; ``update`` returns events for newly seen AU pairings."""

    def __init__(
        self,
        *,
        subject_id: str,
        extractor_id: str,
        id_start: int,
        threshold: float = 0.5,
        min_ms: int = 300,
        min_quality: float = 0.4,
        max_events: int = 40,
    ) -> None:
        self.subject_id = subject_id
        self.extractor_id = extractor_id
        self._k = id_start
        self.threshold = threshold
        self.min_us = min_ms * 1000
        self.min_quality = min_quality
        self.max_events = max_events
        self.familiar: set[tuple[str, str]] = set()
        self.learning = True
        self.baseline_quality = 1.0
        self._open: tuple[frozenset[tuple[str, str]], int, dict[str, float]] | None = None
        self._emitted = 0

    def active(self, values: dict[str, float]) -> tuple[str, ...]:
        return tuple(
            c
            for c in WATCHED_AUS
            if c in values and np.isfinite(values[c]) and values[c] >= self.threshold
        )

    def finish_learning(self, baseline_quality: float) -> None:
        self.learning = False
        self.baseline_quality = baseline_quality

    def update(self, t_us: int, quality: float, values: dict[str, float]) -> list[Event]:
        if quality < self.min_quality or not any(c in values for c in WATCHED_AUS):
            self._open = None
            return []
        combo = self.active(values)
        pairs = set(itertools.combinations(combo, 2))
        if self.learning:
            self.familiar |= pairs
            return []
        unseen = frozenset(pairs - self.familiar)
        if not unseen:
            self._open = None
            return []
        if self._open is None or self._open[0] != unseen:
            self._open = (unseen, t_us, {c: values[c] for c in combo})
            return []
        _u, start, peak_vals = self._open
        for c in combo:
            peak_vals[c] = max(peak_vals.get(c, 0.0), values[c])
        if t_us - start < self.min_us:
            return []
        self.familiar |= unseen
        self._open = None
        if self._emitted >= self.max_events:
            return []
        self._emitted += 1
        involved = sorted({c for pr in unseen for c in pr}, key=WATCHED_AUS.index)
        names = "+".join(c[3:] for c in involved)
        pair_txt = ", ".join(f"{a[3:]} with {b[3:]}" for a, b in sorted(unseen))
        ev = Event(
            event_id=f"ev_{self._k:05d}",
            subject_id=self.subject_id,
            source="video",
            event_type="au_novelty",
            level=EvidenceLevel.INTERPRETATION,
            start_us=start,
            end_us=t_us,
            peak_us=start,
            label=f"new AU pairing: {names}",
            description=(
                f"Action Units were active together for at least {(t_us - start) / 1000:.0f} ms "
                f"in a pairing not seen during calibration ({pair_txt}). Reported once, the first "
                "time the pairing appears. It marks a change in what the face is doing, not why."
            ),
            contributions=[
                FeatureContribution(
                    feature=c,
                    unit="probability",
                    peak_value=float(peak_vals.get(c, values[c])),
                    baseline_center=0.0,
                    baseline_scale=1.0,
                    peak_deviation=float(peak_vals.get(c, values[c])),
                    direction="increase",
                )
                for c in involved
            ],
            severity=round(min(10.0, 2.0 * len(unseen)), 2),
            confidence=round(0.5 * min(1.0, quality), 3),
            quality=float(quality),
            baseline_quality=self.baseline_quality,
            extractor_id=self.extractor_id,
            tags=["novelty", *[c[3:] for c in involved]],
        )
        self._k += 1
        return [ev]


def detect_au_novelty(
    *,
    t_us: npt.NDArray[np.integer],
    quality: npt.NDArray[np.floating],
    signals: dict[str, npt.NDArray[np.floating]],
    calibration_end_us: int,
    subject_id: str,
    extractor_id: str,
    baseline_quality: float,
    id_start: int,
    threshold: float = 0.5,
    min_ms: int = 300,
) -> list[Event]:
    """Offline wrapper: learn on frames before ``calibration_end_us``, report after."""
    cols = [c for c in WATCHED_AUS if c in signals]
    if not cols:
        return []
    det = AUNoveltyDetector(
        subject_id=subject_id,
        extractor_id=extractor_id,
        id_start=id_start,
        threshold=threshold,
        min_ms=min_ms,
    )
    out: list[Event] = []
    t = np.asarray(t_us, dtype=np.int64)
    q = np.asarray(quality, dtype=float)
    mats = np.column_stack([np.asarray(signals[c], dtype=float) for c in cols])
    for i in range(t.size):
        if det.learning and t[i] >= calibration_end_us:
            det.finish_learning(baseline_quality)
        vals = {c: float(mats[i, j]) for j, c in enumerate(cols)}
        out += det.update(int(t[i]), float(q[i]), vals)
    return out
