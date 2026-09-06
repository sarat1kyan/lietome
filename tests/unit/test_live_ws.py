"""WebSocket live endpoint with a fake landmarker: frames in, results and a session out."""

from __future__ import annotations

import json
import struct
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

from lightman.api.app import create_app
from lightman.config import BaselineConfig, LightmanConfig, ModelsConfig
from tests.unit.test_pipeline_fake import FakeLandmarker


def _jpeg(w: int = 160, h: int = 120, seed: int = 0) -> bytes:
    rng = np.random.default_rng(seed)
    img = rng.integers(0, 255, (h, w, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


def _frame_msg(t_us: int, payload: bytes, kind: int = 1) -> bytes:
    return bytes([kind]) + struct.pack(">Q", t_us) + payload


def test_live_ws_round_trip(tmp_path: Path) -> None:
    cfg = LightmanConfig(
        baseline=BaselineConfig(window_s=1.0, min_samples=10, good_samples=30),
        models=ModelsConfig(allow_download=False),
    )
    fake = FakeLandmarker()
    app = create_app(tmp_path, cfg, landmarker_factory=lambda _c, _r: fake)
    client = TestClient(app)
    with client.websocket_connect("/api/live") as ws:
        ws.send_text(json.dumps({"type": "start", "au": False, "audio": False, "source": "test"}))
        ready = ws.receive_json()
        assert ready["type"] == "ready" and ready["session_id"]
        jpeg = _jpeg()
        got_events = False
        frames = 0
        for i in range(90):
            ws.send_bytes(_frame_msg(i * 33_333, jpeg))
            while True:  # events messages may precede the frame acknowledgement
                msg = ws.receive_json()
                if msg["type"] == "events":
                    got_events = True
                    continue
                break
            assert msg["type"] == "frame"
            frames += 1
            assert msg["t_us"] == i * 33_333
            if msg["face"]:
                assert msg["bbox"] and len(msg["landmarks"]) == 478 * 2
                assert "head.yaw_deg" in msg["values"]
        assert frames == 90
        ws.send_text(json.dumps({"type": "stop"}))
        # remaining messages: possibly events, then session
        session_id = None
        for _ in range(20):
            m = ws.receive_json()
            if m["type"] == "events":
                got_events = True
            if m["type"] == "session":
                session_id = m["session_id"]
                break
        assert session_id == ready["session_id"]
    d = tmp_path / session_id
    for name in (
        "features.parquet",
        "events.json",
        "baseline.json",
        "analysis.json",
        "manifest.json",
    ):
        assert (d / name).is_file(), name
    analysis = json.loads((d / "analysis.json").read_text())
    assert analysis["mode"] == "live" and analysis["frames_analyzed"] == 90
    assert analysis["source"] == "test"
    assert fake.closed
    assert got_events or json.loads((d / "events.json").read_text())["events"]


def test_live_ws_rejects_bad_frame_and_ignores_garbage(tmp_path: Path) -> None:
    cfg = LightmanConfig(models=ModelsConfig(allow_download=False))
    app = create_app(tmp_path, cfg, landmarker_factory=lambda _c, _r: FakeLandmarker())
    client = TestClient(app)
    with client.websocket_connect("/api/live") as ws:
        ws.send_bytes(_frame_msg(0, _jpeg()))  # before start: ignored
        ws.send_text(json.dumps({"type": "start", "au": False, "audio": False}))
        assert ws.receive_json()["type"] == "ready"
        ws.send_bytes(_frame_msg(0, b"not a jpeg"))
        err = ws.receive_json()
        assert err["type"] == "error" and "undecodable" in err["detail"]
        ws.send_bytes(b"\x01\x00")  # too short: ignored
        ws.send_bytes(_frame_msg(1000, _jpeg()))
        assert ws.receive_json()["type"] == "frame"
        ws.send_text(json.dumps({"type": "stop"}))
        m = ws.receive_json()
        while m["type"] != "session":
            m = ws.receive_json()
