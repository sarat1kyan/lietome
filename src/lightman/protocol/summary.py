"""Per-question summaries for an interview protocol.

The operator marks questions (with a category: control, relevant, neutral) and optionally an
expected answer class for a ground-truth game. Lightman then reports, per question: response
latency (first speech onset after the mark), answer duration and speech fraction, deviations
and episodes inside the answer window, the strongest signals, blink rate, and the mean voice
pitch deviation. Categories are compared with effect sizes and a permutation p-value; when
expected classes are given for enough questions, a per-session AUROC of a simple deviation
score is computed.

What this is not: a lie detector. A relevant question can differ from a control question
because it is harder, longer, more emotional or asked later; the numbers here describe those
differences and nothing else. With five to ten questions per session every estimate is noisy;
the summary says so in its notes.
"""

from __future__ import annotations

import itertools
import math
from collections import Counter
from typing import Any, Literal

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict, Field

from lightman.interpretation.cues import cue_profile
from lightman.schema import Event

Category = Literal["control", "relevant", "neutral"]
Expected = Literal["truth", "lie"] | None


class Marker(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["question", "note", "end"]
    t_us: int = Field(ge=0)
    id: str = ""
    text: str = ""
    category: Category = "neutral"
    expected: Expected = None


class QuestionSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    text: str
    category: Category
    expected: Expected
    start_us: int
    end_us: int
    response_latency_ms: float | None
    answer_speech_s: float
    speech_fraction: float
    deviations: int
    deviations_per_min: float
    episodes: int
    max_severity: float
    top_signals: list[dict[str, Any]]
    blink_rate_per_min: float | None
    voice_pitch_delta_sd: float | None
    score: float = Field(description="deviations_per_min + max_severity; a descriptive score only")
    expression_patterns: list[str] = Field(default_factory=list)
    cues: dict[str, Any] | None = None


class ProtocolSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = 1
    markers: list[Marker]
    questions: list[QuestionSummary]
    by_category: dict[str, dict[str, float | int | None]]
    control_vs_relevant: dict[str, float | int | None]
    ground_truth: dict[str, Any]
    notes: list[str]
    session_cues: dict[str, Any] | None = None


def _speech_onsets(
    speaking_t_us: npt.NDArray[np.integer], speaking: npt.NDArray[np.bool_]
) -> list[int]:
    if speaking.size == 0:
        return []
    flips = np.nonzero(np.diff(speaking.astype(np.int8)) == 1)[0] + 1
    onsets = [int(speaking_t_us[i]) for i in flips]
    if speaking[0]:
        onsets.insert(0, int(speaking_t_us[0]))
    return onsets


def _permutation_p(
    a: list[float], b: list[float], iters: int = 5000, seed: int = 0
) -> float | None:
    if len(a) < 2 or len(b) < 2:
        return None
    rng = np.random.default_rng(seed)
    pooled = np.array(a + b, dtype=float)
    observed = abs(np.mean(a) - np.mean(b))
    n = len(a)
    count = 0
    for _ in range(iters):
        rng.shuffle(pooled)
        if abs(pooled[:n].mean() - pooled[n:].mean()) >= observed - 1e-12:
            count += 1
    return (count + 1) / (iters + 1)


def _auroc(scores: list[float], labels: list[int]) -> float | None:
    pos = [s for s, y in zip(scores, labels, strict=True) if y == 1]
    neg = [s for s, y in zip(scores, labels, strict=True) if y == 0]
    if len(pos) < 2 or len(neg) < 2:
        return None
    wins = sum(1.0 if p > q else 0.5 if p == q else 0.0 for p, q in itertools.product(pos, neg))
    return wins / (len(pos) * len(neg))


def summarize_protocol(
    markers: list[Marker],
    *,
    events: list[Event],
    t_us: npt.NDArray[np.integer],
    speaking: npt.NDArray[np.bool_] | None,
    session_end_us: int,
    voice_f0_z: tuple[npt.NDArray[np.integer], npt.NDArray[np.floating]] | None = None,
    cue_inputs: dict[str, Any] | None = None,
) -> ProtocolSummary:
    """``cue_inputs`` (optional): signals, baseline_center, baseline_scale, reference_blink_rate
    for the literature cue profile."""
    qs = sorted((m for m in markers if m.kind == "question"), key=lambda m: m.t_us)
    ends = sorted(m.t_us for m in markers if m.kind == "end")
    onsets = _speech_onsets(t_us, speaking) if speaking is not None else []
    blinks = [e.start_us for e in events if e.event_type == "blink"]
    dev = [e for e in events if e.event_type == "baseline_deviation"]
    eps = [e for e in events if e.event_type in ("episode", "multi_signal_deviation")]
    notes: list[str] = []
    out: list[QuestionSummary] = []
    for i, q in enumerate(qs):
        nxt = qs[i + 1].t_us if i + 1 < len(qs) else session_end_us
        end_candidates = [e for e in ends if q.t_us < e <= nxt]
        end = end_candidates[0] if end_candidates else nxt
        if end <= q.t_us:
            continue
        window_min = (end - q.t_us) / 60e6
        latency = None
        if onsets:
            after = [o for o in onsets if q.t_us <= o < end]
            if after:
                latency = (after[0] - q.t_us) / 1000
        in_win = (t_us >= q.t_us) & (t_us < end)
        speech_s = 0.0
        speech_frac = 0.0
        if speaking is not None and in_win.any():
            frames = int(in_win.sum())
            sp = int(speaking[in_win].sum())
            speech_frac = sp / frames
            speech_s = speech_frac * (end - q.t_us) / 1e6
        d = [e for e in dev if e.start_us < end and e.end_us > q.t_us]
        ep = [e for e in eps if e.start_us < end and e.end_us > q.t_us]
        by = Counter(c.feature for e in d for c in e.contributions[:1])
        top = []
        for name, n in by.most_common(3):
            mx = max(
                abs(c.peak_deviation) for e in d for c in e.contributions[:1] if c.feature == name
            )
            top.append({"feature": name, "count": n, "max_dev": round(mx, 1)})
        nblink = sum(1 for b in blinks if q.t_us <= b < end)
        blink_rate = nblink / window_min if window_min > 0 else None
        pitch = None
        if voice_f0_z is not None:
            vt, vz = voice_f0_z
            m = (vt >= q.t_us) & (vt < end) & np.isfinite(vz)
            if m.sum() >= 10:
                pitch = float(np.mean(vz[m]))
        dpm = len(d) / window_min if window_min > 0 else 0.0
        mx_sev = max((e.severity for e in d), default=0.0)
        expr = [
            e.label.replace("expression pattern: ", "")
            for e in events
            if e.event_type == "expression_pattern" and e.start_us < end and e.end_us > q.t_us
        ]
        out.append(
            QuestionSummary(
                id=q.id or f"q{i + 1}",
                text=q.text,
                category=q.category,
                expected=q.expected,
                start_us=q.t_us,
                end_us=end,
                response_latency_ms=latency,
                answer_speech_s=round(speech_s, 2),
                speech_fraction=round(speech_frac, 3),
                deviations=len(d),
                deviations_per_min=round(dpm, 1),
                episodes=len(ep),
                max_severity=round(mx_sev, 1),
                top_signals=top,
                blink_rate_per_min=round(blink_rate, 1) if blink_rate is not None else None,
                voice_pitch_delta_sd=round(pitch, 2) if pitch is not None else None,
                score=round(dpm + mx_sev, 2),
                expression_patterns=expr[:8],
            )
        )
    # cue profiles need the control latency mean: second pass
    if cue_inputs is not None:
        ctrl_lat = [
            r.response_latency_ms
            for r in out
            if r.category == "control" and r.response_latency_ms is not None
        ]
        ctrl_mean = float(np.mean(ctrl_lat)) if ctrl_lat else None
        out = [
            r.model_copy(
                update={
                    "cues": cue_profile(
                        window=(r.start_us, r.end_us),
                        t_us=t_us,
                        signals=cue_inputs["signals"],
                        baseline_center=cue_inputs["baseline_center"],
                        baseline_scale=cue_inputs["baseline_scale"],
                        voice_f0_z=voice_f0_z,
                        blink_times_us=blinks,
                        reference_blink_rate=cue_inputs.get("reference_blink_rate"),
                        response_latency_ms=r.response_latency_ms,
                        control_latency_ms=ctrl_mean if r.category != "control" else None,
                    )
                }
            )
            for r in out
        ]
    by_cat: dict[str, dict[str, float | int | None]] = {}
    for cat in ("control", "relevant", "neutral"):
        rows = [r for r in out if r.category == cat]
        if not rows:
            continue
        lat = [r.response_latency_ms for r in rows if r.response_latency_ms is not None]
        by_cat[cat] = {
            "n": len(rows),
            "mean_deviations_per_min": round(
                float(np.mean([r.deviations_per_min for r in rows])), 1
            ),
            "mean_max_severity": round(float(np.mean([r.max_severity for r in rows])), 1),
            "mean_latency_ms": round(float(np.mean(lat)), 0) if lat else None,
        }
    cvr: dict[str, float | int | None] = {}
    ctrl = [r for r in out if r.category == "control"]
    rel = [r for r in out if r.category == "relevant"]
    if ctrl and rel:
        a = [r.deviations_per_min for r in rel]
        b = [r.deviations_per_min for r in ctrl]
        cvr["delta_deviations_per_min"] = round(float(np.mean(a) - np.mean(b)), 1)
        la = [r.response_latency_ms for r in rel if r.response_latency_ms is not None]
        lb = [r.response_latency_ms for r in ctrl if r.response_latency_ms is not None]
        cvr["delta_latency_ms"] = round(float(np.mean(la) - np.mean(lb)), 0) if la and lb else None
        cvr["permutation_p_deviations"] = _permutation_p(a, b)
        cvr["n_control"] = len(ctrl)
        cvr["n_relevant"] = len(rel)
        if len(ctrl) < 3 or len(rel) < 3:
            notes.append(
                "fewer than 3 questions per category: the control-vs-relevant comparison is "
                "anecdotal"
            )
    gt: dict[str, Any] = {"n_truth": 0, "n_lie": 0, "auroc": None}
    labeled = [r for r in out if r.expected in ("truth", "lie")]
    if labeled:
        labels = [1 if r.expected == "lie" else 0 for r in labeled]
        scores = [r.score for r in labeled]
        gt = {
            "n_truth": labels.count(0),
            "n_lie": labels.count(1),
            "auroc": _auroc(scores, labels),
            "score_definition": "deviations_per_min + max_severity within the answer window",
            "note": (
                "Experimental. AUROC of a descriptive deviation score against the operator's "
                "expected labels for this one person and session. 0.5 is chance. Wide "
                "uncertainty with few questions; a high value here is not evidence of lie "
                "detection, a low value is expected."
            ),
        }
        if gt["auroc"] is not None and (labels.count(0) < 3 or labels.count(1) < 3):
            notes.append(
                "fewer than 3 items per class: the discrimination score is not interpretable"
            )
    if not out:
        notes.append("no questions were marked")
    if speaking is None:
        notes.append("no speech detection in this session: response latency not available")
    session_cues = None
    if cue_inputs is not None and t_us.size:
        start = int(cue_inputs.get("session_start_us", 0))
        session_cues = cue_profile(
            window=(start, session_end_us),
            t_us=t_us,
            signals=cue_inputs["signals"],
            baseline_center=cue_inputs["baseline_center"],
            baseline_scale=cue_inputs["baseline_scale"],
            voice_f0_z=voice_f0_z,
            blink_times_us=blinks,
            reference_blink_rate=cue_inputs.get("reference_blink_rate"),
            response_latency_ms=None,
            control_latency_ms=None,
        )
    return ProtocolSummary(
        markers=markers,
        questions=out,
        by_category=by_cat,
        control_vs_relevant=cvr,
        ground_truth=gt,
        notes=notes,
        session_cues=session_cues,
    )


def parse_question_script(text: str) -> list[dict[str, str | None]]:
    """Parse operator text: one question per line, optional prefix 'C:'/'R:'/'N:' for the
    category and optional suffix '[truth]' or '[lie]' for the expected class."""
    out: list[dict[str, str | None]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        cat = "neutral"
        head = line[:2].upper()
        if head in ("C:", "R:", "N:"):
            cat = {"C:": "control", "R:": "relevant", "N:": "neutral"}[head]
            line = line[2:].strip()
        expected: str | None = None
        low = line.lower()
        for tag in ("[truth]", "[lie]"):
            if low.endswith(tag):
                expected = tag.strip("[]")
                line = line[: -len(tag)].strip()
        out.append({"text": line, "category": cat, "expected": expected})
    return out


__all__ = [
    "Marker",
    "ProtocolSummary",
    "QuestionSummary",
    "math",
    "parse_question_script",
    "summarize_protocol",
]
