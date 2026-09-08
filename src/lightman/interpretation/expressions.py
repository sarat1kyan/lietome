"""Prototypical facial expression patterns from Action Unit probabilities.

The patterns are the classic FACS/EMFACS combinations (Ekman & Friesen; Ekman, Friesen &
Hager 2002). A pattern event says that the face *looked like* the prototype for some time;
it does not say the person felt that emotion. Spontaneous expressions rarely match prototypes
exactly, the same combination appears while joking, concentrating or talking, and display
rules vary by culture (see Barrett et al. 2019 for the review). Patterns shorter than
``BRIEF_MAX_MS`` are tagged "brief": candidates for what the microexpression literature
studies, not confirmed microexpressions (those need 100-200 fps and FACS coders).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from lightman.events.segments import hysteresis_segments, median_frame_period_us, segment_end_us
from lightman.schema.events import Event, EvidenceLevel, FeatureContribution


@dataclass(frozen=True, slots=True)
class Prototype:
    name: str
    required: tuple[str, ...]
    """AU columns (``au.AUx``) whose mean probability forms the pattern score."""
    unilateral: tuple[tuple[str, str], ...] = ()
    """(left, right) AU pairs whose *difference* forms the score (contempt)."""
    absent: tuple[str, ...] = ()
    """AU columns that must stay low (probability < ABSENT_MAX) for the pattern to count."""
    note: str = ""


PROTOTYPES: tuple[Prototype, ...] = (
    Prototype(
        "happiness", ("au.AU6", "au.AU12"), note="Duchenne smile: cheek raise with lip corner pull"
    ),
    Prototype(
        "social smile",
        ("au.AU12",),
        absent=("au.AU6",),
        note="lip corners without cheek raise; polite or masking smiles look like this",
    ),
    Prototype(
        "brow flash",
        ("au.AU1", "au.AU2"),
        absent=("au.AU5", "au.AU26"),
        note="brow raise without eye widening or jaw drop: conversational emphasis, greeting",
    ),
    Prototype("surprise", ("au.AU1", "au.AU2", "au.AU5", "au.AU26")),
    Prototype("fear", ("au.AU1", "au.AU2", "au.AU4", "au.AU5", "au.AU7", "au.AU20", "au.AU26")),
    Prototype("anger", ("au.AU4", "au.AU5", "au.AU7", "au.AU23")),
    Prototype("sadness", ("au.AU1", "au.AU4", "au.AU15")),
    Prototype("disgust", ("au.AU9", "au.AU15")),
    Prototype("contempt", (), (("au.AUL12", "au.AUR12"), ("au.AUL14", "au.AUR14"))),
    Prototype("lip press", ("au.AU24",), absent=("au.AU12",), note="lips pressed together"),
    Prototype(
        "brow furrow",
        ("au.AU4",),
        absent=("au.AU1", "au.AU2", "au.AU12"),
        note="brow lowering alone: concentration, bright light, displeasure",
    ),
)
ABSENT_MAX = 0.35

PATTERN_ENTER = 0.55
PATTERN_EXIT = 0.40
MIN_MS = 100
BRIEF_MAX_MS = 500
UNILATERAL_ENTER = 0.35


def pattern_scores(
    signals: dict[str, npt.NDArray[np.floating]], n: int
) -> dict[str, npt.NDArray[np.float64]]:
    """Per-frame score in [0, 1] for each prototype; NaN where AUs are missing."""
    out: dict[str, npt.NDArray[np.float64]] = {}
    for p in PROTOTYPES:
        if p.required:
            cols = [signals.get(c) for c in p.required]
            if any(c is None for c in cols):
                continue
            stack = np.vstack([np.asarray(c, dtype=np.float64) for c in cols if c is not None])
            # geometric-ish combination: all required AUs must be present, weakest matters
            score = 0.5 * np.nanmean(stack, axis=0) + 0.5 * np.nanmin(stack, axis=0)
            if p.absent:
                acols = [signals.get(c) for c in p.absent]
                if any(c is None for c in acols):
                    continue
                astack = np.vstack(
                    [np.asarray(c, dtype=np.float64) for c in acols if c is not None]
                )
                # any "absent" AU above ABSENT_MAX cancels the pattern (it is then another one)
                score = np.where(np.nanmax(astack, axis=0) < ABSENT_MAX, score, 0.0)
        else:
            diffs = []
            for left, right in p.unilateral:
                left_v, right_v = signals.get(left), signals.get(right)
                if left_v is None or right_v is None:
                    continue
                diffs.append(
                    np.abs(np.asarray(left_v, dtype=float) - np.asarray(right_v, dtype=float))
                )
            if not diffs:
                continue
            score = np.nanmax(np.vstack(diffs), axis=0) / UNILATERAL_ENTER * PATTERN_ENTER
        out[p.name] = np.clip(np.where(np.isfinite(score), score, np.nan), 0.0, 1.0)[:n]
    return out


def _au_list(p: Prototype) -> str:
    if p.required:
        base = "+".join(c[3:] for c in p.required)
        if p.absent:
            base += " without " + "/".join(c[3:] for c in p.absent)
        return base
    return "one-sided " + "/".join(f"{left[4:]}" for left, _ in p.unilateral)


def detect_expression_patterns(
    *,
    t_us: npt.NDArray[np.integer],
    quality: npt.NDArray[np.floating],
    signals: dict[str, npt.NDArray[np.floating]],
    subject_id: str,
    extractor_id: str,
    baseline_quality: float,
    id_start: int = 600_000,
    min_quality: float = 0.4,
) -> list[Event]:
    n = t_us.shape[0]
    period = median_frame_period_us(t_us)
    ok = np.asarray(quality >= min_quality, dtype=np.bool_)
    scores = pattern_scores(signals, n)
    events: list[Event] = []
    k = id_start
    proto_by_name = {p.name: p for p in PROTOTYPES}
    for name, score in scores.items():
        p = proto_by_name[name]
        segs = hysteresis_segments(score, ok, enter=PATTERN_ENTER, exit_=PATTERN_EXIT)
        for s in segs:
            start = int(t_us[s.start_idx])
            end = segment_end_us(t_us, s.end_idx, period)
            dur_ms = (end - start) / 1000
            if dur_ms < MIN_MS:
                continue
            brief = dur_ms <= BRIEF_MAX_MS
            peak = float(score[s.peak_idx])
            contribs = []
            for c in p.required or tuple(x for pair in p.unilateral for x in pair):
                v = signals.get(c)
                if v is None:
                    continue
                contribs.append(
                    FeatureContribution(
                        feature=c,
                        unit="probability",
                        peak_value=float(v[s.peak_idx]),
                        baseline_center=0.0,
                        baseline_scale=1.0,
                        peak_deviation=float(v[s.peak_idx]),
                        direction="increase",
                    )
                )
            q = float(np.nanmean(quality[s.start_idx : s.end_idx + 1]))
            events.append(
                Event(
                    event_id=f"ev_{k:05d}",
                    subject_id=subject_id,
                    source="video",
                    event_type="expression_pattern",
                    level=EvidenceLevel.INTERPRETATION,
                    start_us=start,
                    end_us=end,
                    peak_us=int(t_us[s.peak_idx]),
                    label=f"{'brief ' if brief else ''}expression pattern: {name} ({_au_list(p)})",
                    description=(
                        f"Action Units matched the FACS prototype for {name} for {dur_ms:.0f} ms "
                        f"(pattern score {peak:.2f}). This describes the appearance of the face, "
                        "not a felt emotion; the same pattern occurs in speech, humor and "
                        "concentration."
                    ),
                    contributions=contribs,
                    severity=round(peak * 5, 2),
                    confidence=round(min(1.0, q) * min(1.0, peak / PATTERN_ENTER) * 0.8, 3),
                    quality=q,
                    baseline_quality=baseline_quality,
                    extractor_id=extractor_id,
                    tags=["expression", name] + (["brief"] if brief else []),
                )
            )
            k += 1
    events.sort(key=lambda e: (e.start_us, e.event_id))
    return events


class StreamingExpressionDetector:
    """Live counterpart: per-frame update with hysteresis state per prototype."""

    def __init__(
        self,
        *,
        subject_id: str,
        extractor_id: str,
        baseline_quality: float,
        frame_period_us: int,
        id_start: int = 600_000,
        min_quality: float = 0.4,
    ) -> None:
        self.subject_id = subject_id
        self.extractor_id = extractor_id
        self.baseline_quality = baseline_quality
        self.period_us = frame_period_us
        self.min_quality = min_quality
        self._k = id_start
        self._open: dict[str, tuple[int, int, float, dict[str, float], list[float]]] = {}

    def update(self, t_us: int, quality: float, values: dict[str, float]) -> list[Event]:
        out: list[Event] = []
        arrs = {k: np.array([v]) for k, v in values.items() if k.startswith("au.")}
        scores = pattern_scores(arrs, 1) if arrs else {}
        for p in PROTOTYPES:
            sc = scores.get(p.name)
            s = float(sc[0]) if sc is not None and sc.size else float("nan")
            valid = quality >= self.min_quality and np.isfinite(s)
            run = self._open.get(p.name)
            if run is None:
                if valid and s >= PATTERN_ENTER:
                    self._open[p.name] = (t_us, t_us, s, dict(values), [quality])
            elif not valid or s < PATTERN_EXIT:
                out += self._close(p, run, t_us)
                del self._open[p.name]
            else:
                start, _peak_t, peak_s, _peak_vals, qs = run
                qs.append(quality)
                if s > peak_s:
                    self._open[p.name] = (start, t_us, s, dict(values), qs)
        return out

    def flush(self, t_us: int) -> list[Event]:
        out: list[Event] = []
        for name, run in list(self._open.items()):
            p = next(x for x in PROTOTYPES if x.name == name)
            out += self._close(p, run, t_us + self.period_us)
        self._open.clear()
        return out

    def _close(
        self, p: Prototype, run: tuple[int, int, float, dict[str, float], list[float]], end_us: int
    ) -> list[Event]:
        start, peak_t, peak_s, vals, qs = run
        dur_ms = (end_us - start) / 1000
        if dur_ms < MIN_MS:
            return []
        brief = dur_ms <= BRIEF_MAX_MS
        cols = p.required or tuple(x for pair in p.unilateral for x in pair)
        contribs = [
            FeatureContribution(
                feature=c,
                unit="probability",
                peak_value=float(vals.get(c, 0.0)),
                baseline_center=0.0,
                baseline_scale=1.0,
                peak_deviation=float(vals.get(c, 0.0)),
                direction="increase",
            )
            for c in cols
            if c in vals
        ]
        q = float(np.mean(qs)) if qs else 0.0
        eid = f"ev_{self._k:05d}"
        self._k += 1
        return [
            Event(
                event_id=eid,
                subject_id=self.subject_id,
                source="video",
                event_type="expression_pattern",
                level=EvidenceLevel.INTERPRETATION,
                start_us=start,
                end_us=end_us,
                peak_us=peak_t,
                label=f"{'brief ' if brief else ''}expression pattern: {p.name} ({_au_list(p)})",
                description=(
                    f"Action Units matched the FACS prototype for {p.name} for {dur_ms:.0f} ms "
                    f"(pattern score {peak_s:.2f}). This describes the appearance of the face, not "
                    "a felt emotion; the same pattern occurs in speech, humor and concentration."
                ),
                contributions=contribs,
                severity=round(peak_s * 5, 2),
                confidence=round(min(1.0, q) * min(1.0, peak_s / PATTERN_ENTER) * 0.8, 3),
                quality=q,
                baseline_quality=self.baseline_quality,
                extractor_id=self.extractor_id,
                tags=["expression", p.name] + (["brief"] if brief else []),
            )
        ]
