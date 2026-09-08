"""Plain-language session narrative, generated from the numbers with fixed templates.

No language model. Every sentence is traceable to a field in analysis/baseline/events, and the
wording stays on the observation/interpretation rungs. The narrative is stored in
analysis.json and shown in the UI and report.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from lightman.core.timebase import format_timecode
from lightman.features.action_units import au_description
from lightman.schema import Event


def _human_signal(name: str) -> str:
    if name.startswith("au."):
        d = au_description(name[3:])
        return f"{name[3:]} ({d})" if d else name[3:]
    return {
        "blendshape.browInnerUp": "inner brow raise",
        "blendshape.browDownLeft": "left brow lowering",
        "blendshape.browDownRight": "right brow lowering",
        "blendshape.jawOpen": "jaw opening",
        "blendshape.mouthPressLeft": "left lip press",
        "blendshape.mouthPressRight": "right lip press",
        "blendshape.eyeSquintLeft": "left eye squint",
        "blendshape.eyeSquintRight": "right eye squint",
        "head.yaw_deg": "head turn",
        "head.pitch_deg": "head nod",
        "head.roll_deg": "head tilt",
        "head.speed_deg_s": "head movement speed",
        "gaze.horizontal": "horizontal gaze",
        "gaze.vertical": "vertical gaze",
        "asym.brow_lower": "brow asymmetry",
        "asym.mouth_smile": "smile asymmetry",
        "voice.f0_hz": "voice pitch",
        "voice.energy_db": "voice loudness",
        "eye.aspect_ratio_mean": "eye openness",
    }.get(name, name)


def build_narrative(
    *,
    duration_us: int,
    quality: dict[str, Any],
    baseline: dict[str, Any],
    state_baselines: dict[str, Any] | None,
    events: list[Event],
    audio: dict[str, Any] | None,
    mode: str,
) -> list[str]:
    lines: list[str] = []
    dur = format_timecode(duration_us)
    cov = quality.get("face_coverage")
    lines.append(
        f"{'Live' if mode == 'live' else 'Recorded'} session of {dur}. "
        + (f"A face was visible in {cov:.0%} of analyzed frames." if cov is not None else "")
    )
    mfq = quality.get("mean_face_quality")
    if mfq is not None:
        adj = "good" if mfq >= 0.8 else "fair" if mfq >= 0.5 else "poor"
        lines.append(f"Image quality for facial analysis was {adj} (mean {mfq:.2f}).")
    bq = baseline.get("quality", 0.0)
    fu = baseline.get("frames_used", 0)
    wend = baseline.get("window_end_us", 0)
    states = ""
    if state_baselines:
        parts = [f"{k} {v.get('frames_used', 0)}" for k, v in state_baselines.items() if k != "all"]
        if parts:
            states = " (" + ", ".join(parts) + " frames)"
    lines.append(
        f"Baseline calibrated on the first {format_timecode(wend)} from {fu} frames, reliability "
        f"{bq:.2f}{states}. Later values are compared with this person's own calibration, adapted "
        "slowly within bounds."
    )
    dev = [e for e in events if e.event_type == "baseline_deviation"]
    episodes = [e for e in events if e.event_type in ("episode", "multi_signal_deviation")]
    blinks = [e for e in events if e.event_type == "blink"]
    post_s = max(1.0, (duration_us - wend) / 1e6)
    if blinks:
        per_min = 60 * len(blinks) / max(1.0, duration_us / 1e6)
        lines.append(f"{len(blinks)} blinks, about {per_min:.0f} per minute.")
    rate_ev = [e for e in events if e.event_type == "blink_rate_change"]
    lines.extend(f"At {format_timecode(e.start_us)}: {e.label}." for e in rate_ev[:3])
    if dev:
        by = Counter(c.feature for e in dev for c in e.contributions[:1])
        top = ", ".join(f"{_human_signal(n)} ({k})" for n, k in by.most_common(4))
        speaking = sum("speaking" in e.tags for e in dev)
        lines.append(
            f"{len(dev)} signal deviations after calibration "
            f"({60 * len(dev) / post_s:.0f} per minute), grouped into {len(episodes)} episodes. "
            f"Most frequent: {top}."
        )
        if speaking:
            lines.append(
                f"{speaking} of them occurred while speaking; mouth and jaw motion during "
                "speech is articulation and is scored against the speaking-state baseline "
                "where one exists."
            )
        strongest = max(dev, key=lambda e: e.severity)
        c = strongest.contributions[0]
        lines.append(
            f"Largest single deviation at {format_timecode(strongest.start_us)}: "
            f"{_human_signal(c.feature)} {c.direction} to {c.peak_value:.2f} {c.unit}, "
            f"{abs(c.peak_deviation):.0f} robust SD from its baseline."
        )
    else:
        lines.append("No signal left its baseline range after calibration.")
    if audio:
        sf = audio.get("speech_fraction")
        snr = audio.get("snr_db")
        seg = audio.get("speech_segments")
        if sf is not None:
            s = f"Speech was detected in {sf:.0%} of the audio"
            if seg is not None:
                s += f" across {seg} segments"
            if snr is not None:
                s += f"; signal-to-noise about {snr:.0f} dB"
            lines.append(s + ".")
        voice = [e for e in events if e.source == "audio"]
        if voice:
            kinds = Counter(" ".join(e.label.split(" ")[:2]) for e in voice if " " in e.label)
            listed = ", ".join(f"{k} ({n})" for k, n in kinds.most_common(3))
            lines.append(f"{len(voice)} voice events: {listed}.")
    expr = [e for e in events if e.event_type == "expression_pattern"]
    if expr:
        by = Counter(t for e in expr for t in e.tags if t not in ("expression", "brief"))
        brief = sum("brief" in e.tags for e in expr)
        listed = ", ".join(f"{k} ({n})" for k, n in by.most_common(4))
        lines.append(
            f"{len(expr)} FACS expression patterns appeared ({brief} brief, under 500 ms): "
            f"{listed}. These name what the face looked like, not what was felt."
        )
    lines.append(
        "These are measurements of movement and voice relative to this person's own baseline. They "
        "do not identify emotions, intent or truthfulness."
    )
    return lines


def cues_narrative(cues: dict[str, Any] | None) -> list[str]:
    if not cues:
        return []
    present = [c["name"] for c in cues.get("cues", []) if c.get("present")]
    txt = f"Deception-research cue check for the session: {cues.get('summary', '')}."
    if present:
        txt += " Present: " + ", ".join(present) + "."
    return [txt, cues.get("caveat", "")]


def protocol_narrative(protocol: Any) -> list[str]:
    """Sentences for an interview protocol summary (ProtocolSummary or its dict form)."""
    d = protocol if isinstance(protocol, dict) else protocol.model_dump(mode="json")
    qs = d.get("questions", [])
    if not qs:
        return []
    lines = [f"{len(qs)} questions were marked."]
    for q in qs:
        rl = q.get("response_latency_ms")
        lat = f"answered after {rl:.0f} ms" if rl is not None else "no speech onset detected"
        top = ", ".join(_human_signal(t["feature"]) for t in q.get("top_signals", [])[:2]) or "none"
        lines.append(
            f"Q{q['id'].lstrip('q')} ({q['category']}): {lat}; {q['deviations']} deviations "
            f"({q['deviations_per_min']:.0f}/min), strongest {q['max_severity']:.0f} SD; "
            f"signals: {top}."
        )
    cvr = d.get("control_vs_relevant") or {}
    if cvr.get("delta_deviations_per_min") is not None:
        p = cvr.get("permutation_p_deviations")
        ptxt = f", permutation p = {p:.2f}" if p is not None else ""
        dl = cvr.get("delta_latency_ms")
        ltxt = f", {dl:+.0f} ms response latency" if dl is not None else ""
        lines.append(
            f"Relevant minus control questions: "
            f"{cvr['delta_deviations_per_min']:+.1f} deviations/min{ltxt}{ptxt}. "
            "Question type, length and order all move these numbers."
        )
    gt = d.get("ground_truth") or {}
    if gt.get("auroc") is not None:
        lines.append(
            f"Discrimination of the operator's expected classes by the deviation score: AUROC "
            f"{gt['auroc']:.2f} over {gt['n_truth']} truth and {gt['n_lie']} lie items "
            "(0.5 = chance). "
            "Experimental, one person, one session; not evidence of lie detection."
        )
    lines.extend(
        f"Q{q['id'].lstrip('q')}: {q['cues']['summary']}."
        for q in qs
        if q.get("cues") and q["cues"].get("present")
    )
    lines.extend(f"Note: {n}." for n in d.get("notes", []))
    return lines
