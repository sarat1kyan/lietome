"""Practice summary for one session: the measures a practitioner looks at first.

Computed from the saved session (features.parquet, audio_features.parquet, baselines, events)
so it works the same for live, uploaded and older sessions. Written to practice.json.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq

from lightman.practice.affect import affect_series, affect_summary
from lightman.practice.conversation import engagement, talk_time

FRAME_COLS = (
    "t_us",
    "quality",
    "face_present",
    "speaking",
    "head.yaw_deg",
    "head.speed_deg_s",
    "gaze.horizontal",
    "gaze.vertical",
    "blendshape.jawOpen",
    "blendshape.mouthSmileLeft",
    "blendshape.mouthSmileRight",
    "blendshape.browDownLeft",
    "blendshape.browDownRight",
    "blendshape.mouthFrownLeft",
    "blendshape.mouthFrownRight",
    "blendshape.noseSneerLeft",
    "blendshape.eyeWideLeft",
    "blendshape.eyeWideRight",
    "blendshape.browInnerUp",
    "au.AU1",
    "au.AU2",
    "au.AU4",
    "au.AU5",
    "au.AU6",
    "au.AU9",
    "au.AU10",
    "au.AU12",
    "au.AU15",
    "au.AU20",
    "au.AU25",
    "au.AU26",
)
NEGATIVE = {
    "fear",
    "anger",
    "sadness",
    "disgust",
    "contempt",
    "embarrassment",
    "distress",
    "tension",
}
POSITIVE = {"happiness", "social smile"}
META = {"expression", "brief", "fast_onset", "negative", "positive", "neutral"}


def _read(d: Path, name: str) -> Any:
    p = d / name
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _voice_z(d: Path) -> tuple[np.ndarray, np.ndarray] | None:
    p = d / "audio_features.parquet"
    base = _read(d, "audio_baseline.json")
    if not p.is_file() or not base:
        return None
    tbl = pq.read_table(p)
    names = tbl.schema.names
    if "t_us" not in names:
        return None
    t = tbl.column("t_us").to_numpy().astype(np.int64)
    parts = []
    for k in ("voice.energy_db", "voice.f0_hz"):
        sb = (base.get("signals") or {}).get(k) or {}
        c, s = sb.get("center"), sb.get("scale")
        if k in names and c is not None and s:
            x = tbl.column(k).to_numpy(zero_copy_only=False).astype(float)
            parts.append((x - c) / s)
    if not parts:
        return None
    z = np.nanmean(np.vstack(parts), axis=0) if len(parts) > 1 else parts[0]
    return t, z


def build_practice_summary(session_dir: Path) -> dict[str, Any]:
    d = Path(session_dir)
    p = d / "features.parquet"
    if not p.is_file():
        return {"status": "unavailable", "reason": "no feature table"}
    schema = pq.ParquetFile(p).schema_arrow.names
    tbl = pq.read_table(p, columns=[c for c in FRAME_COLS if c in schema])
    cols = {c: tbl.column(c).to_numpy(zero_copy_only=False) for c in tbl.schema.names}
    t = cols["t_us"].astype(np.int64)
    if t.size < 10:
        return {"status": "unavailable", "reason": "session too short"}
    base = _read(d, "baseline.json") or {}
    cal_end = int(base.get("window_end_us") or 0)
    sigs = base.get("signals") or {}
    centers = {
        k: float(v["center"])
        for k, v in sigs.items()
        if isinstance(v, dict) and v.get("center") is not None and math.isfinite(v["center"])
    }
    vals = {
        k: v.astype(np.float64)
        for k, v in cols.items()
        if k not in ("t_us", "face_present", "speaking")
    }
    face = cols.get("face_present", np.ones(t.size, dtype=bool)).astype(bool)
    quality = vals.get("quality", np.ones(t.size))
    series = affect_series(t, vals, quality, cal_end, voice_z=_voice_z(d))
    step = max(1, int(t.size / max(1, (t[-1] - t[0]) / 5e5)))  # about 2 points per second
    events = (_read(d, "events.json") or {}).get("events", [])
    after = [e for e in events if e["start_us"] >= cal_end]
    pats = [e for e in after if e["event_type"] == "expression_pattern"]
    names = [next((x for x in e["tags"] if x not in META), "") for e in pats]
    analysis = _read(d, "analysis.json") or {}
    post_min = max(1e-6, (int(t[-1]) - cal_end) / 6e7)
    rate = None
    ap = d / "audio_features.parquet"
    if ap.is_file() and "voice.rate_syl_s" in pq.ParquetFile(ap).schema_arrow.names:
        r = (
            pq.read_table(ap, columns=["voice.rate_syl_s"])
            .column(0)
            .to_numpy(zero_copy_only=False)
            .astype(float)
        )
        r = r[np.isfinite(r)]
        rate = round(float(np.median(r)), 2) if r.size else None
    talk = (
        talk_time(t, cols["speaking"].astype(bool), face, vals, start_us=cal_end)
        if "speaking" in cols
        else None
    )
    out: dict[str, Any] = {
        "status": "done",
        "duration_s": round(float(t[-1]) / 1e6, 1),
        "calibration_end_s": round(cal_end / 1e6, 1),
        "affect": affect_summary(t, series, cal_end),
        "affect_series": {
            "t_us": t[::step].tolist(),
            "valence": [
                None if not math.isfinite(x) else round(float(x), 3)
                for x in series["valence"][::step]
            ],
            "arousal": [
                None if not math.isfinite(x) else round(float(x), 3)
                for x in series["arousal"][::step]
            ],
        },
        "engagement": engagement(t, face, vals, centers, start_us=cal_end),
        "talk": talk,
        "speech_rate_syl_s": rate,
        "pauses": sum(1 for e in after if e["event_type"] == "speech_pause"),
        "patterns": {
            "positive": sum(1 for n in names if n in POSITIVE),
            "negative": sum(1 for n in names if n in NEGATIVE),
            "other": sum(1 for n in names if n and n not in POSITIVE | NEGATIVE),
            "per_min": round(len(pats) / post_min, 2),
        },
        "gaze_away": sum(1 for e in after if e["event_type"] == "gaze_away"),
        "self_touch": sum(1 for e in after if e["event_type"] == "self_touch"),
        "blink_rate_per_min": analysis.get("blink_rate_per_min"),
        "pulse_bpm": (analysis.get("pulse") or {}).get("median_bpm"),
        "note": (
            "Expressed affect is estimated from face and voice against this person's "
            "calibration. It describes expression, not feeling, and is most useful as a trend "
            "across this person's sessions."
        ),
    }
    return out


def write_practice_summary(session_dir: Path) -> dict[str, Any]:
    doc = build_practice_summary(session_dir)
    (Path(session_dir) / "practice.json").write_text(json.dumps(doc))
    return doc


def _measure(doc: dict[str, Any], key: str) -> Any:
    post_min = max(1e-6, doc["duration_s"] - doc["calibration_end_s"]) / 60
    return {
        "valence": (doc.get("affect") or {}).get("valence_mean"),
        "arousal": (doc.get("affect") or {}).get("arousal_mean"),
        "engagement": (doc.get("engagement") or {}).get("share"),
        "client_talk_share": (doc.get("talk") or {}).get("client_share"),
        "speech_rate": doc.get("speech_rate_syl_s"),
        "negative_patterns_per_min": round(doc["patterns"]["negative"] / post_min, 2),
        "blink_rate": doc.get("blink_rate_per_min"),
    }[key]


TREND_KEYS = (
    "valence",
    "arousal",
    "engagement",
    "client_talk_share",
    "speech_rate",
    "negative_patterns_per_min",
    "blink_rate",
)


def client_trends(session_dirs: list[Path]) -> dict[str, Any]:
    """One row per session (oldest first) with the headline measures."""
    rows = []
    for d in sorted(session_dirs, key=lambda x: x.name):
        doc = _read(d, "practice.json")
        if not doc or doc.get("status") != "done":
            try:
                doc = write_practice_summary(d)
            except (OSError, ValueError, KeyError):
                continue
        if doc.get("status") != "done":
            continue
        row: dict[str, Any] = {"session_id": d.name, "duration_s": doc["duration_s"]}
        for key in TREND_KEYS:
            row[key] = _measure(doc, key)
        rows.append(row)
    return {"sessions": rows, "measures": list(TREND_KEYS)}
