"""Session store: a directory of session directories written by the analyze/live pipelines.

Session ids are validated against a strict pattern so a request can never escape the root.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq

from lightman.core.errors import LightmanError

SESSION_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{6}$")
EVENT_ID_RE = re.compile(r"^ev_[0-9]{5}$")
SIGNAL_RE = re.compile(r"^[A-Za-z0-9_.]{1,64}$")


class SessionNotFoundError(LightmanError):
    pass


class SessionStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _dir(self, session_id: str) -> Path:
        if not SESSION_ID_RE.match(session_id):
            raise SessionNotFoundError("invalid session id")
        d = self.root / session_id
        if not d.is_dir() or not (d / "manifest.json").is_file():
            raise SessionNotFoundError(f"unknown session {session_id}")
        return d

    def list_sessions(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not self.root.is_dir():
            return out
        for d in sorted(self.root.iterdir(), reverse=True):
            if not SESSION_ID_RE.match(d.name) or not (d / "manifest.json").is_file():
                continue
            try:
                m = json.loads((d / "manifest.json").read_text("utf-8"))
                a = json.loads((d / "analysis.json").read_text("utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            events = 0
            if (d / "events.json").is_file():
                try:
                    events = len(json.loads((d / "events.json").read_text("utf-8"))["events"])
                except (OSError, json.JSONDecodeError, KeyError):
                    events = 0
            out.append(
                {
                    "session_id": d.name,
                    "created_utc": m.get("created_utc"),
                    "mode": a.get("mode", "prerecorded"),
                    "media_name": m.get("media", {}).get("path_name"),
                    "duration_us": m.get("media", {}).get("duration_us") or a.get("duration_us"),
                    "face_coverage": m.get("quality", {}).get("face_coverage"),
                    "baseline_quality": m.get("quality", {}).get("baseline_quality"),
                    "events": events,
                    "has_audio": (d / "audio_features.parquet").is_file(),
                    "has_media": (d / "media.mp4").is_file(),
                }
            )
        return out

    def read_json(self, session_id: str, name: str) -> Any:
        d = self._dir(session_id)
        if name not in {
            "manifest.json",
            "analysis.json",
            "events.json",
            "baseline.json",
            "metadata.json",
            "audio_baseline.json",
            "speech_segments.json",
            "protocol.json",
            "state_baselines.json",
        }:
            raise SessionNotFoundError("unknown artifact")
        p = d / name
        if not p.is_file():
            return None
        return json.loads(p.read_text("utf-8"))

    def features(
        self, session_id: str, *, table: str, signals: list[str] | None, max_points: int
    ) -> dict[str, Any]:
        """Return t_us plus requested signal columns, evenly decimated to ``max_points``."""
        d = self._dir(session_id)
        fname = {"video": "features.parquet", "audio": "audio_features.parquet"}.get(table)
        if fname is None:
            raise SessionNotFoundError("unknown table")
        p = d / fname
        if not p.is_file():
            return {"t_us": [], "signals": {}, "columns": []}
        pf = pq.ParquetFile(p)
        columns = list(pf.schema_arrow.names)
        wanted: list[str] = [s for s in (signals or []) if SIGNAL_RE.match(s) and s in columns]
        cols = ["t_us", *wanted]
        if "quality" in columns and "quality" not in cols:
            cols.append("quality")
        tbl = pf.read(columns=cols)
        n = tbl.num_rows
        idx = np.arange(n) if n <= max_points else np.linspace(0, n - 1, max_points).astype(int)
        out: dict[str, Any] = {
            "t_us": tbl.column("t_us").to_numpy()[idx].astype(int).tolist(),
            "columns": columns,
            "signals": {},
            "decimated": n > max_points,
            "rows": n,
        }
        for c in cols[1:]:
            arr = tbl.column(c).to_numpy(zero_copy_only=False)[idx].astype(float)
            out["signals"][c] = [None if not np.isfinite(v) else round(float(v), 5) for v in arr]
        return out

    def frame(self, session_id: str, t_us: int) -> dict[str, Any]:
        """All signal values at the frame nearest ``t_us`` plus baseline center/scale per signal.

        The baseline used is the speaking/silent state baseline when the session has one
        and the frame has a speaking flag, else the session-wide baseline.
        """
        d = self._dir(session_id)
        p = d / "features.parquet"
        if not p.is_file():
            return {"t_us": None, "values": {}, "baseline": {}, "state": None}
        pf = pq.ParquetFile(p)
        columns = [c for c in pf.schema_arrow.names if SIGNAL_RE.match(c) or c == "t_us"]
        tbl = pf.read(columns=columns)
        ts = tbl.column("t_us").to_numpy().astype(np.int64)
        if ts.size == 0:
            return {"t_us": None, "values": {}, "baseline": {}, "state": None}
        i = int(np.clip(np.searchsorted(ts, t_us), 0, ts.size - 1))
        if i > 0 and abs(int(ts[i - 1]) - t_us) < abs(int(ts[i]) - t_us):
            i -= 1
        values: dict[str, float | None] = {}
        for c in columns:
            if c == "t_us":
                continue
            v = tbl.column(c)[i].as_py()
            values[c] = None if v is None or not np.isfinite(float(v)) else round(float(v), 5)
        speaking = values.get("speaking")
        state = None
        base: dict[str, Any] = {}
        states = self.read_json(session_id, "state_baselines.json")
        if isinstance(states, dict) and speaking is not None:
            state = "speaking" if speaking >= 0.5 else "silent"
            base = states.get(state) or states.get("all") or {}
        if not base:
            base = self.read_json(session_id, "baseline.json") or {}
        sigs = base.get("signals", {}) if isinstance(base, dict) else {}
        baseline = {
            k: {"center": v.get("center"), "scale": v.get("scale")}
            for k, v in sigs.items()
            if isinstance(v, dict)
        }
        return {"t_us": int(ts[i]), "values": values, "baseline": baseline, "state": state}

    def thumbnail(self, session_id: str, event_id: str) -> Path:
        d = self._dir(session_id)
        if not EVENT_ID_RE.match(event_id):
            raise SessionNotFoundError("invalid event id")
        for ext in (".jpg", ".png"):
            p = d / "thumbnails" / f"{event_id}{ext}"
            if p.is_file():
                return p
        raise SessionNotFoundError("no thumbnail")

    def media(self, session_id: str) -> Path:
        p = self._dir(session_id) / "media.mp4"
        if not p.is_file():
            raise SessionNotFoundError("no retained media for this session")
        return p
