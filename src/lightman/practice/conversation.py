"""Conversation measures: talk time, turns and engagement.

Talk time splits detected speech between the person on camera and everyone else, using what
the camera sees: speech while the mouth is moving belongs to the person on camera; speech while
the mouth is still belongs to someone off camera (the practitioner). One microphone cannot
separate voices; the mouth can. Overlaps and a client who listens with the mouth moving
(nodding along with "mm") are counted as client speech, so the split is approximate.

Engagement is the share of time the face is oriented to the conversation: face visible, head
within 25 degrees of its usual direction and gaze within its usual range. Looking away to think
is normal; the measure is useful as a trend within a person, not as a score.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt

MOUTH_WINDOW_S = 0.6
MIN_TURN_S = 0.5


def _rolling_std(x: npt.NDArray[np.float64], k: int) -> npt.NDArray[np.float64]:
    out = np.full(x.shape, np.nan)
    if x.size < 2:
        return out
    half = max(1, k // 2)
    for i in range(x.size):
        w = x[max(0, i - half) : i + half + 1]
        w = w[np.isfinite(w)]
        if w.size >= 2:
            out[i] = float(np.std(w))
    return out


def mouth_activity(
    t_us: npt.NDArray[np.integer], values: dict[str, npt.NDArray[np.floating]]
) -> npt.NDArray[np.float64]:
    """Short-window variability of mouth opening (jaw open; lips-part AU when present)."""
    t = np.asarray(t_us, dtype=np.int64)
    fps = 1e6 / float(np.median(np.diff(t))) if t.size > 1 else 15.0
    k = max(3, round(MOUTH_WINDOW_S * fps))
    jaw = np.asarray(values.get("blendshape.jawOpen", np.full(t.size, np.nan)), dtype=float)
    act = _rolling_std(jaw, k)
    au25 = values.get("au.AU25")
    if au25 is not None and np.isfinite(au25).any():
        act = np.fmax(act, 0.5 * _rolling_std(np.asarray(au25, dtype=float), k))
    return act


GAP_S = 0.4
"""Pauses up to this long inside one speaker's stretch do not end the turn."""


def _turns(labels: npt.NDArray[np.int_], period: float) -> list[tuple[int, float]]:
    """(speaker, seconds) per turn: same-speaker runs joined across short pauses."""
    runs: list[list[int]] = []  # [speaker, first index, last index]
    for i, lab in enumerate(labels):
        if lab == 0:
            continue
        if runs and runs[-1][0] == lab and (i - runs[-1][2] - 1) * period <= GAP_S:
            runs[-1][2] = i
        else:
            runs.append([int(lab), i, i])
    out: list[tuple[int, float]] = []
    for spk, a, b in runs:
        dur = (b - a + 1) * period
        if dur < MIN_TURN_S:
            continue
        if out and out[-1][0] == spk:
            out[-1] = (spk, out[-1][1] + dur)
        else:
            out.append((spk, dur))
    return out


def talk_time(
    t_us: npt.NDArray[np.integer],
    speaking: npt.NDArray[np.bool_],
    face_present: npt.NDArray[np.bool_],
    values: dict[str, npt.NDArray[np.floating]],
    *,
    start_us: int = 0,
) -> dict[str, Any] | None:
    """Seconds of speech by the person on camera and by others, with turn counts."""
    t = np.asarray(t_us, dtype=np.int64)
    sp = np.asarray(speaking, dtype=bool)
    if t.size < 10 or not sp.any():
        return None
    act = mouth_activity(t, values)
    silent = (~sp) & np.isfinite(act) & np.asarray(face_present, dtype=bool)
    thr = float(np.percentile(act[silent], 75)) * 1.5 if silent.sum() >= 20 else 0.02
    thr = max(thr, 0.01)
    period = float(np.median(np.diff(t))) / 1e6
    m = t >= start_us
    client = sp & m & np.isfinite(act) & (act > thr)
    other = sp & m & ~client
    labels = np.where(client, 1, np.where(other, 2, 0))
    turns = _turns(labels, period)
    c_s = float(client.sum() * period)
    o_s = float(other.sum() * period)
    total = c_s + o_s
    ct = [d for s, d in turns if s == 1]
    ot = [d for s, d in turns if s == 2]
    return {
        "client_s": round(c_s, 1),
        "other_s": round(o_s, 1),
        "client_share": round(c_s / total, 3) if total > 0 else None,
        "client_turns": len(ct),
        "other_turns": len(ot),
        "client_turn_mean_s": round(float(np.mean(ct)), 1) if ct else None,
        "other_turn_mean_s": round(float(np.mean(ot)), 1) if ot else None,
        "mouth_threshold": round(thr, 4),
        "note": "speech attributed by mouth movement; approximate with one microphone",
    }


def engagement(
    t_us: npt.NDArray[np.integer],
    face_present: npt.NDArray[np.bool_],
    values: dict[str, npt.NDArray[np.floating]],
    centers: dict[str, float],
    *,
    start_us: int = 0,
    window_s: float = 10.0,
) -> dict[str, Any]:
    """Share of time oriented to the conversation, overall and per window."""
    t = np.asarray(t_us, dtype=np.int64)
    fp = np.asarray(face_present, dtype=bool)
    yaw = np.asarray(
        values.get("head.yaw_deg", np.full(t.size, np.nan)), dtype=float
    ) - centers.get("head.yaw_deg", 0.0)
    gh = np.asarray(
        values.get("gaze.horizontal", np.full(t.size, np.nan)), dtype=float
    ) - centers.get("gaze.horizontal", 0.0)
    gv = np.asarray(
        values.get("gaze.vertical", np.full(t.size, np.nan)), dtype=float
    ) - centers.get("gaze.vertical", 0.0)
    oriented = (
        fp
        & (np.abs(np.nan_to_num(yaw, nan=99.0)) <= 25.0)
        & (np.hypot(np.nan_to_num(gh, nan=9.0), np.nan_to_num(gv, nan=9.0)) <= 0.45)
    )
    m = t >= start_us
    if not m.any():
        return {"share": None, "windows": []}
    win = int(window_s * 1e6)
    windows = []
    a = int(t[m][0])
    end = int(t[-1])
    while a < end:
        w = m & (t >= a) & (t < a + win)
        if w.sum() >= 3:
            windows.append({"t_us": a, "share": round(float(oriented[w].mean()), 3)})
        a += win
    return {"share": round(float(oriented[m].mean()), 3), "windows": windows}
