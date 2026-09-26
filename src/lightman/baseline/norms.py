"""Personal norms: a subject's typical baseline across their own sessions.

After each session the calibration baseline (center and robust scale per signal) is appended to
``<output root>/_subjects/<subject>.json`` (last 20 sessions). From two earlier sessions on, a
new calibration is compared with the norm:

* a signal whose calibration spread is under half its usual spread is widened to that half:
  a 40 s calibration that happened to be unusually still would otherwise turn ordinary movement
  into deviations for the rest of the session;
* a signal whose calibration center sits more than 3 usual spreads from its usual center is
  reported as calibration drift (lighting, camera distance, posture or mood on the day).

The norm never replaces the calibration; it only bounds it from below and explains it.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import numpy as np

from lightman.baseline.robust import BaselineSnapshot

MAX_SESSIONS = 20
MIN_SESSIONS = 2
SCALE_FLOOR_FRACTION = 0.5
DRIFT_SD = 3.0
SUBJECT_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def norms_path(root: Path, subject: str) -> Path | None:
    if not SUBJECT_RE.match(subject):
        return None
    return root / "_subjects" / f"{subject}.json"


def update_norms(
    root: Path, subject: str, session_id: str, created_utc: str, snap: BaselineSnapshot
) -> None:
    """Append this session's calibration to the subject's norm file."""
    p = norms_path(root, subject)
    if p is None or snap.quality < 0.5:
        return
    data: dict[str, Any] = {"subject_id": subject, "sessions": []}
    if p.is_file():
        try:
            data = json.loads(p.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {"subject_id": subject, "sessions": []}
    sessions = [s for s in data.get("sessions", []) if s.get("session_id") != session_id]
    sessions.append(
        {
            "session_id": session_id,
            "created_utc": created_utc,
            "quality": round(snap.quality, 3),
            "centers": {k: v.center for k, v in snap.signals.items() if math.isfinite(v.center)},
            "scales": {k: v.scale for k, v in snap.signals.items() if math.isfinite(v.scale)},
        }
    )
    data["sessions"] = sessions[-MAX_SESSIONS:]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=1))


def load_norms(root: Path, subject: str, *, exclude: str | None = None) -> dict[str, Any] | None:
    """Median center and median scale per signal across earlier sessions, or None."""
    p = norms_path(root, subject)
    if p is None or not p.is_file():
        return None
    try:
        data = json.loads(p.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    sessions = [s for s in data.get("sessions", []) if s.get("session_id") != exclude]
    if len(sessions) < MIN_SESSIONS:
        return None
    names = {k for s in sessions for k in s.get("centers", {})}
    centers: dict[str, float] = {}
    scales: dict[str, float] = {}
    for k in names:
        c = [s["centers"][k] for s in sessions if k in s.get("centers", {})]
        sc = [s["scales"][k] for s in sessions if k in s.get("scales", {})]
        if len(c) >= MIN_SESSIONS and len(sc) >= MIN_SESSIONS:
            centers[k] = float(np.median(c))
            scales[k] = float(np.median(sc))
    return {"sessions": len(sessions), "centers": centers, "scales": scales}


def apply_norms(
    snap: BaselineSnapshot, norms: dict[str, Any] | None
) -> tuple[BaselineSnapshot, dict[str, Any] | None]:
    """(adjusted snapshot, report). Report lists widened and drifting signals."""
    if not norms:
        return snap, None
    widened: list[str] = []
    drift: list[dict[str, Any]] = []
    new_signals = dict(snap.signals)
    for k, sb in snap.signals.items():
        n_scale = norms["scales"].get(k)
        n_center = norms["centers"].get(k)
        if n_scale is None or n_center is None or not n_scale > 0:
            continue
        floor = SCALE_FLOOR_FRACTION * n_scale
        if math.isfinite(sb.scale) and sb.scale < floor:
            new_signals[k] = sb.model_copy(update={"scale": floor})
            widened.append(k)
        if math.isfinite(sb.center) and abs(sb.center - n_center) > DRIFT_SD * n_scale:
            drift.append(
                {
                    "signal": k,
                    "calibration": round(sb.center, 4),
                    "usual": round(n_center, 4),
                    "shift_sd": round((sb.center - n_center) / n_scale, 1),
                }
            )
    drift.sort(key=lambda r: -abs(r["shift_sd"]))
    notes = list(snap.notes)
    if widened:
        notes.append(
            f"{len(widened)} signals had an unusually narrow calibration and were widened to "
            "half this person's usual spread"
        )
    if drift:
        notes.append(
            "calibration differs from this person's usual baseline in "
            + ", ".join(d["signal"] for d in drift[:4])
        )
    report = {
        "sessions_used": norms["sessions"],
        "widened": widened,
        "drift": drift[:8],
    }
    return snap.model_copy(update={"signals": new_signals, "notes": notes}), report
