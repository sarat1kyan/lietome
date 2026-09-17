"""Research layer: cues that the deception literature associates with lying, checked against
this person's baseline. Output is a checklist with the published effect size next to each cue.
It is not a probability of lying and it is not an Event.

Sources for the effect sizes (Cohen's d, liars minus truth-tellers, as reported):
* DePaulo et al. 2003, Psychological Bulletin 129(1), meta-analysis of 158 cues: vocal pitch
  d = 0.21; pressed lips d = 0.16; illustrators (hand gestures) d = -0.14; response latency
  d = 0.02 (not significant); nervousness impression d = 0.27; few cues above 0.3.
* Sporer & Schwandt 2006, Applied Cognitive Psychology 20: paraverbal cues; response latency
  and pause measures small and heterogeneous.
* Leal & Vrij 2008, Journal of Nonverbal Behavior 32: blink rate reduced during lying,
  increased immediately after (cognitive load account).
* Bond & DePaulo 2006: human accuracy about 54%; the cues are weak individually and together.
* Porter & ten Brinke 2008, Psychological Science 19; ten Brinke & Porter 2012, Law and Human
  Behavior 36: in falsified or high-stakes emotional accounts, brief expressions inconsistent
  with the claimed emotion and leaked negative affect were more frequent (moderate effects in
  small samples; treated here as d about 0.3 and 0.2).
* DePaulo et al. 2003: impression of nervousness / tension d = 0.27 (facial tension proxy).

Lightman reports which of these cues moved in the "lie-associated" direction relative to the
person's own baseline in a window (a question or the whole session). That is all it can do.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True, slots=True)
class CueSpec:
    key: str
    name: str
    direction: str  # "increase" or "decrease" = direction reported for liars
    effect_size: float
    source: str


CUES: tuple[CueSpec, ...] = (
    CueSpec("pitch", "higher voice pitch", "increase", 0.21, "DePaulo et al. 2003"),
    CueSpec(
        "lip_press", "pressed lips (AU24 / lip press)", "increase", 0.16, "DePaulo et al. 2003"
    ),
    CueSpec(
        "movement",
        "less head movement (illustrator proxy)",
        "decrease",
        -0.14,
        "DePaulo et al. 2003 (hand illustrators)",
    ),
    CueSpec(
        "latency",
        "longer response latency",
        "increase",
        0.02,
        "DePaulo et al. 2003 (n.s.); Sporer & Schwandt 2006 small",
    ),
    CueSpec(
        "blink", "blink rate change", "change", 0.0, "Leal & Vrij 2008 (down during, up after)"
    ),
    CueSpec(
        "negative_affect",
        "negative-affect expression pattern during the answer",
        "increase",
        0.30,
        "ten Brinke & Porter 2012 (leaked emotion, high-stakes lies)",
    ),
    CueSpec(
        "brief_pattern",
        "brief expression pattern (under 500 ms) during the answer",
        "increase",
        0.20,
        "Porter & ten Brinke 2008 (inconsistent brief expressions)",
    ),
    CueSpec(
        "tension",
        "facial tension (brow lowering, lid tightening, lip tightening)",
        "increase",
        0.27,
        "DePaulo et al. 2003 (nervousness / tension impression)",
    ),
)
NEGATIVE_PATTERNS = frozenset(
    {"fear", "anger", "sadness", "disgust", "contempt", "embarrassment", "distress", "tension"}
)
# weights for the index: |d| of each cue; latency and blink carry almost nothing
INDEX_WEIGHTS = {c.key: max(0.02, abs(c.effect_size)) for c in CUES}
INDEX_WEIGHTS["blink"] = 0.05

CAVEAT = (
    "Cues from meta-analyses of deception research; individual effect sizes are small "
    "(mostly d < 0.3) and human accuracy with them is about 54%. Presence of cues is not a "
    "probability of lying; stress, effort, humor and the question itself move the same cues."
)


def cue_profile(
    *,
    window: tuple[int, int],
    t_us: npt.NDArray[np.integer],
    signals: Mapping[str, npt.NDArray[np.floating]],
    baseline_center: Mapping[str, float],
    baseline_scale: Mapping[str, float],
    voice_f0_z: tuple[npt.NDArray[np.integer], npt.NDArray[np.floating]] | None,
    blink_times_us: list[int],
    reference_blink_rate: float | None,
    response_latency_ms: float | None,
    control_latency_ms: float | None,
    z_threshold: float = 1.0,
    events: list[Any] | None = None,
    state_baselines: Mapping[str, Mapping[str, tuple[float, float]]] | None = None,
    frame_state: npt.NDArray[np.str_] | None = None,
) -> dict[str, Any]:
    """Evaluate each cue in ``window`` (start_us, end_us) against baseline statistics.

    ``events`` (optional) supplies expression patterns for the affect cues. ``state_baselines``
    maps state -> signal -> (center, scale); with ``frame_state`` each frame is scored against
    its own state's baseline, so articulation during speech is not read as lip press or
    tension."""
    a, b = window
    m = (t_us >= a) & (t_us < b)
    minutes = max(1e-6, (b - a) / 60e6)
    results: list[dict[str, Any]] = []

    def z_of(name: str) -> float | None:
        v = signals.get(name)
        if v is None or name not in baseline_center or not m.any():
            return None
        sc = baseline_scale.get(name, 0.0)
        if not sc or not np.isfinite(sc):
            return None
        vals = np.asarray(v, dtype=float)[m]
        center = np.full(vals.shape, float(baseline_center[name]))
        scale = np.full(vals.shape, float(sc))
        if state_baselines is not None and frame_state is not None:
            fs = np.asarray(frame_state)[m]
            for state, sigs in state_baselines.items():
                cs = sigs.get(name)
                if cs is None or not (np.isfinite(cs[0]) and np.isfinite(cs[1]) and cs[1] > 0):
                    continue
                sel = fs == state
                center[sel] = cs[0]
                scale[sel] = cs[1]
        ok = np.isfinite(vals)
        if ok.sum() < 5:
            return None
        return float(np.mean((vals[ok] - center[ok]) / scale[ok]))

    # pitch
    pz = None
    if voice_f0_z is not None:
        vt, vz = voice_f0_z
        mm = (vt >= a) & (vt < b) & np.isfinite(vz)
        if mm.sum() >= 10:
            pz = float(np.mean(vz[mm]))
    results.append(_row(CUES[0], pz, present=pz is not None and pz >= z_threshold, unit="SD"))
    # lip press: mean of AU24 and mouthPress blendshapes z
    lz = [
        z
        for z in (
            z_of("au.AU24"),
            z_of("blendshape.mouthPressLeft"),
            z_of("blendshape.mouthPressRight"),
        )
        if z is not None
    ]
    lp = float(np.mean(lz)) if lz else None
    results.append(_row(CUES[1], lp, present=lp is not None and lp >= z_threshold, unit="SD"))
    # movement: head speed z (decrease = cue)
    hz = z_of("head.speed_deg_s")
    results.append(_row(CUES[2], hz, present=hz is not None and hz <= -z_threshold, unit="SD"))
    # latency vs control questions
    lat = None
    if response_latency_ms is not None and control_latency_ms:
        lat = response_latency_ms - control_latency_ms
    results.append(
        _row(CUES[3], lat, present=lat is not None and lat >= 300.0, unit="ms vs control")
    )
    # blink change vs reference
    bl = None
    if reference_blink_rate:
        n = sum(1 for t in blink_times_us if a <= t < b)
        rate = n / minutes
        bl = rate / reference_blink_rate
    results.append(
        _row(CUES[4], bl, present=bl is not None and (bl <= 0.5 or bl >= 2.0), unit="x reference")
    )
    # expression-based cues: rate inside the window against the rate outside it (the rest of
    # the session, calibration included). A pattern that this face makes all the time is not
    # a cue; one that appears only in this answer is.
    session_fraction = float((b - a) / max(1, int(t_us[-1]) - int(t_us[0]))) if t_us.size else 1.0
    if events is not None and t_us.size and session_fraction <= 0.7:
        span = (int(t_us[0]), int(t_us[-1]))
        out_min = max(1e-6, ((span[1] - span[0]) - (b - a)) / 60e6)
        pats = [e for e in events if e.event_type == "expression_pattern"]
        inside = [e for e in pats if e.start_us < b and e.end_us > a]
        outside = [e for e in pats if not (e.start_us < b and e.end_us > a)]

        def rate_cue(spec: CueSpec, pick: Any) -> None:
            n_in = sum(1 for e in inside if pick(e))
            n_out = sum(1 for e in outside if pick(e))
            rate_in, rate_out = n_in / minutes, n_out / out_min
            present = n_in >= 1 and (
                rate_in >= 2.0 * rate_out if n_out else n_in >= 2 or minutes < 0.5
            )
            results.append(_row(spec, rate_in, present=present, unit="per min"))

        rate_cue(CUES[5], lambda e: any(t in NEGATIVE_PATTERNS for t in e.tags))
        rate_cue(CUES[6], lambda e: "brief" in e.tags)
    else:
        results.append(_row(CUES[5], None, present=False, unit="per min"))
        results.append(_row(CUES[6], None, present=False, unit="per min"))
    tz = [z for z in (z_of("au.AU4"), z_of("au.AU7"), z_of("au.AU23")) if z is not None]
    tens = float(np.mean(tz)) if tz else None
    results.append(_row(CUES[7], tens, present=tens is not None and tens >= z_threshold, unit="SD"))
    present = sum(1 for r in results if r["present"])
    evaluated = sum(1 for r in results if r["value"] is not None)
    speech_unscored = bool(
        frame_state is not None
        and m.any()
        and (np.asarray(frame_state)[m] == "speaking").mean() > 0.3
        and not (state_baselines and "speaking" in state_baselines)
    )
    out = {
        "window_us": [a, b],
        "speech_unscored": speech_unscored,
        "session_fraction": round(min(1.0, session_fraction), 3),
        "cues": results,
        "present": present,
        "evaluated": evaluated,
        "summary": (
            f"{present} of {evaluated} evaluable literature cues moved in the lie-associated "
            "direction"
        ),
        "caveat": CAVEAT,
    }
    out["index"] = deception_cue_index(out)
    return out


BANDS: tuple[tuple[float, str], ...] = (
    (40.0, "low"),
    (55.0, "unremarkable"),
    (70.0, "some"),
    (85.0, "elevated"),
    (101.0, "high"),
)

INDEX_CAVEAT = (
    "The index is the effect-size-weighted share of literature cues that moved in the "
    "lie-associated direction against this person's own baseline, shrunk toward 50 when few "
    "cues could be evaluated or the window is short. It is not a calibrated probability: with "
    "every cue combined, published accuracy is about 54-60%. Stress, effort, humor and the "
    "question itself move the same cues."
)


def _moved_other_way(key: str, v: float) -> bool:
    """True when a cue moved clearly against its lie-associated direction."""
    if key in ("pitch", "lip_press", "tension"):
        return v <= -1.0
    if key == "movement":
        return v >= 1.0
    if key == "latency":
        return v <= -300.0
    return False


def deception_cue_index(profile: dict[str, Any]) -> dict[str, Any]:
    """Possibility-of-deception index in [0, 100] from a cue profile.

    Meaningful for a question or an answer compared with the rest of the session; a
    whole-session window has no within-person comparison and is discounted.

    Each evaluated cue contributes +1 (moved in the lie direction), -1 (moved clearly the other
    way) or 0, weighted by its |effect size|. 50 means no net evidence either way. Reliability
    (share of cues evaluable, window length) shrinks the index toward 50.
    """
    a, b = profile["window_us"]
    window_s = max(0.0, (b - a) / 1e6)
    num = 0.0
    den = 0.0
    drivers: list[str] = []
    counters: list[str] = []
    for r in profile["cues"]:
        w = INDEX_WEIGHTS.get(r["key"], 0.05)
        v = r["value"]
        if v is None:
            continue
        den += w
        s = 0.0
        if r["present"]:
            s = 1.0
        elif _moved_other_way(r["key"], v):
            s = -1.0
        num += w * s
        if s > 0:
            drivers.append(r["name"])
        elif s < 0:
            counters.append(r["name"])
    if den <= 0:
        return {
            "value": None,
            "band": "not evaluable",
            "drivers": [],
            "counters": [],
            "reliability": 0.0,
            "text": "Possibility of deception: not evaluable (no cues could be measured).",
            "caveat": INDEX_CAVEAT,
        }
    total_w = sum(INDEX_WEIGHTS.values())
    reliability = min(1.0, den / total_w) * min(1.0, window_s / 20.0)
    if profile.get("speech_unscored"):
        reliability *= 0.5  # speech in the window but no speaking-state baseline
    if profile.get("session_fraction", 0.0) > 0.7:
        reliability *= 0.6  # whole-session window: nothing of this person to compare against
    raw = num / den  # [-1, 1]
    value = 50.0 + 50.0 * raw * reliability
    band = next(name for lim, name in BANDS if value < lim)
    text = (
        f"Possibility of deception, cue-based: {band} ({value:.0f}/100, reliability "
        f"{reliability:.2f}). "
    )
    if drivers:
        text += "Moved in the lie-associated direction: " + ", ".join(drivers) + ". "
    if counters:
        text += "Moved the other way: " + ", ".join(counters) + ". "
    text += "Not a probability; see caveat."
    return {
        "value": round(value, 1),
        "band": band,
        "drivers": drivers,
        "counters": counters,
        "reliability": round(reliability, 2),
        "text": text,
        "caveat": INDEX_CAVEAT,
    }


def _row(spec: CueSpec, value: float | None, *, present: bool, unit: str) -> dict[str, Any]:
    return {
        **asdict(spec),
        "value": None if value is None else round(value, 2),
        "unit": unit,
        "present": bool(present) if value is not None else False,
    }
