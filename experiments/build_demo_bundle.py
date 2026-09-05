"""Build a self-contained demo of the web UI with one session's data inlined.

    uv run python experiments/build_demo_bundle.py output/<session_id> frontend/demo-data.json

The frontend's demo build (npm run build:demo) inlines this JSON as window.__LIGHTMAN_DEMO__ so
the page runs with no server. Thumbnails are embedded as data URIs. Use only with sessions you
are allowed to share.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

from lightman.api.sessions import SessionNotFoundError, SessionStore

VIDEO_SIGNALS = [
    "head.yaw_deg", "head.pitch_deg", "eye.aspect_ratio_mean", "blendshape.browDownLeft",
    "blendshape.mouthPressLeft", "blendshape.jawOpen", "au.AU4", "au.AU6", "au.AU12", "au.AU24",
]  # fmt: skip
AUDIO_SIGNALS = ["voice.f0_hz", "voice.energy_db"]


def main() -> None:
    session_dir, out = Path(sys.argv[1]), Path(sys.argv[2])
    store = SessionStore(session_dir.parent)
    sid = session_dir.name
    summary = next(s for s in store.list_sessions() if s["session_id"] == sid)
    detail = {
        "manifest": store.read_json(sid, "manifest.json"),
        "analysis": store.read_json(sid, "analysis.json"),
        "baseline": store.read_json(sid, "baseline.json"),
        "audio_baseline": store.read_json(sid, "audio_baseline.json"),
        "segments": store.read_json(sid, "speech_segments.json"),
    }
    events = store.read_json(sid, "events.json") or {"events": []}
    features = {"video": store.features(sid, table="video", signals=VIDEO_SIGNALS, max_points=2000)}
    if summary["has_audio"]:
        features["audio"] = store.features(
            sid, table="audio", signals=AUDIO_SIGNALS, max_points=2000
        )
    thumbs: dict[str, str] = {}
    for e in events["events"]:
        try:
            p = store.thumbnail(sid, e["event_id"])
        except SessionNotFoundError:
            continue
        mime = "image/jpeg" if p.suffix == ".jpg" else "image/png"
        thumbs[e["event_id"]] = f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()
    bundle = {
        "sessions": [summary],
        "detail": {sid: detail},
        "events": {sid: events},
        "features": {sid: features},
        "thumbnails": {sid: thumbs},
    }
    out.write_text(json.dumps(bundle), "utf-8")
    print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
