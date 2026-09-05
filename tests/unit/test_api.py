"""API tests against a session directory produced by the fake-backend pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lightman.api.app import create_app
from lightman.config import BaselineConfig, LightmanConfig, ModelsConfig
from lightman.pipeline import analyze_video
from tests.conftest import noise_frames, write_video
from tests.unit.test_pipeline_fake import FakeLandmarker


@pytest.fixture(scope="module")
def session_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("sessions")
    video = write_video(root / "v.mp4", noise_frames(90, w=160, h=120), fps=30)
    cfg = LightmanConfig(
        baseline=BaselineConfig(window_s=1.0, min_samples=10, good_samples=30),
        models=ModelsConfig(allow_download=False),
    ).model_copy(update={"au": LightmanConfig().au.model_copy(update={"enabled": False})})
    analyze_video(video, root / "out", cfg, landmarker_factory=lambda _c, _r: FakeLandmarker())
    return root / "out"


@pytest.fixture(scope="module")
def client(session_root: Path) -> TestClient:
    return TestClient(create_app(session_root))


def test_health_and_list(client: TestClient) -> None:
    assert client.get("/api/health").json()["status"] == "ok"
    sessions = client.get("/api/sessions").json()
    assert len(sessions) == 1
    s = sessions[0]
    assert s["events"] > 0 and s["face_coverage"] > 0.9 and s["has_media"] is False
    assert s["media_name"] == "v.mp4"


def test_session_detail_events_features(client: TestClient) -> None:
    sid = client.get("/api/sessions").json()[0]["session_id"]
    d = client.get(f"/api/sessions/{sid}").json()
    assert d["manifest"]["session_id"] == sid and d["baseline"]["signals"]
    ev = client.get(f"/api/sessions/{sid}/events").json()["events"]
    assert ev and all(e["level"] != "speculation" for e in ev)
    f = client.get(
        f"/api/sessions/{sid}/features",
        params={"signals": "blendshape.browDownLeft,eye.aspect_ratio_mean,nope", "max_points": 20},
    ).json()
    assert len(f["t_us"]) == 20 and f["decimated"] and f["rows"] == 90
    assert set(f["signals"]) == {"blendshape.browDownLeft", "eye.aspect_ratio_mean", "quality"}
    thumb_ok = [e for e in ev if e["event_type"] != "blink"]
    r = client.get(f"/api/sessions/{sid}/thumbnails/{thumb_ok[0]['event_id']}")
    assert r.status_code in (200, 404)


def test_invalid_ids_are_rejected(client: TestClient) -> None:
    assert client.get("/api/sessions/../../etc").status_code in (404, 400)
    assert client.get("/api/sessions/20260101T000000Z-abcdef").status_code == 404
    sid = client.get("/api/sessions").json()[0]["session_id"]
    assert client.get(f"/api/sessions/{sid}/thumbnails/..%2Fmanifest.json").status_code == 404
    assert client.get(f"/api/sessions/{sid}/media").status_code == 404
    assert (
        client.get(f"/api/sessions/{sid}/features", params={"table": "secrets"}).status_code == 422
    )


def test_upload_rejects_empty_and_oversize(session_root: Path) -> None:
    cfg = LightmanConfig().model_copy(
        update={"limits": LightmanConfig().limits.model_copy(update={"max_file_bytes": 1000})}
    )
    c = TestClient(create_app(session_root, cfg))
    assert c.post("/api/analyze", files={"file": ("e.mp4", b"")}).status_code == 400
    assert c.post("/api/analyze", files={"file": ("big.mp4", b"x" * 5000)}).status_code == 413
    assert not list(session_root.glob(".upload-*"))


def test_upload_job_failure_is_reported(client: TestClient, session_root: Path) -> None:
    r = client.post("/api/analyze", files={"file": ("bad.mp4", b"not a video" * 100)})
    assert r.status_code == 202
    jid = r.json()["job_id"]
    import time

    for _ in range(100):
        j = client.get(f"/api/jobs/{jid}").json()
        if j["state"] in ("done", "failed"):
            break
        time.sleep(0.05)
    assert j["state"] == "failed" and "container" in j["error"]
    assert not list(session_root.glob(".upload-*"))
    assert client.get("/api/jobs/nope").status_code == 404
    assert client.get("/").status_code == 200  # UI index or the not-built notice
