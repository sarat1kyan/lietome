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
)

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
) -> dict[str, Any]:
    """Evaluate each cue in ``window`` (start_us, end_us) against baseline statistics."""
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
        vals = vals[np.isfinite(vals)]
        if vals.size < 5:
            return None
        return float((np.mean(vals) - baseline_center[name]) / sc)

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
    present = sum(1 for r in results if r["present"])
    evaluated = sum(1 for r in results if r["value"] is not None)
    return {
        "window_us": [a, b],
        "cues": results,
        "present": present,
        "evaluated": evaluated,
        "summary": (
            f"{present} of {evaluated} evaluable literature cues moved in the lie-associated "
            "direction"
        ),
        "caveat": CAVEAT,
    }


def _row(spec: CueSpec, value: float | None, *, present: bool, unit: str) -> dict[str, Any]:
    return {
        **asdict(spec),
        "value": None if value is None else round(value, 2),
        "unit": unit,
        "present": bool(present) if value is not None else False,
    }
