import math

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from lightman.api.security import TokenMiddleware, ensure_self_signed_cert, new_token, tls_dir
from lightman.events.blinkrate import blink_rate_events
from lightman.features.derived import (
    asymmetry_from_blendshapes,
    frame_quality_terms,
    gaze_from_blendshapes,
    head_speed_deg_s,
    image_quality_factor,
)
from lightman.report.narrative import build_narrative
from lightman.schema.events import Event, EvidenceLevel


def test_gaze_and_asymmetry_proxies() -> None:
    bs = {
        "eyeLookOutLeft": 0.8,
        "eyeLookInLeft": 0.0,
        "eyeLookInRight": 0.8,
        "eyeLookOutRight": 0.0,
        "eyeLookUpLeft": 0.1,
        "eyeLookUpRight": 0.1,
        "eyeLookDownLeft": 0.6,
        "eyeLookDownRight": 0.6,
        "browDownLeft": 0.5,
        "browDownRight": 0.1,
        "mouthSmileLeft": 0.2,
        "mouthSmileRight": 0.6,
    }
    h, v = gaze_from_blendshapes(bs)
    assert h == pytest.approx(0.8) and v == pytest.approx(-0.5)  # subject's left, down
    b, s = asymmetry_from_blendshapes(bs)
    assert b == pytest.approx(0.4) and s == pytest.approx(-0.4)


def test_head_speed_and_quality_terms() -> None:
    assert math.isnan(head_speed_deg_s(None, (0, 0, 0), 33_333))
    assert head_speed_deg_s((0, 0, 0), (3, 4, 0), 1_000_000) == 5.0
    rng = np.random.default_rng(0)
    sharp = rng.integers(0, 255, (240, 320, 3), dtype=np.uint8)
    blur, luma = frame_quality_terms(sharp, (40, 40, 200, 200))
    assert blur > 60 and 100 < luma < 155
    dark = np.zeros((240, 320, 3), dtype=np.uint8)
    blur_d, luma_d = frame_quality_terms(dark, (40, 40, 200, 200))
    assert blur_d == 0 and luma_d == 0
    assert image_quality_factor(blur, luma) == 1.0
    assert image_quality_factor(blur_d, luma_d) == 0.0
    assert image_quality_factor(math.nan, math.nan) == 1.0
    assert math.isnan(frame_quality_terms(dark, (0, 0, 4, 4))[0])


def test_blink_rate_events_detect_sustained_change() -> None:
    ref = [int(t * 1e6) for t in np.arange(40, 100, 4.0)]  # 15/min
    fast = [int(t * 1e6) for t in np.arange(100, 190, 4.0 / 3.0)]  # 45/min
    ev = blink_rate_events(
        ref + fast,
        start_us=40_000_000,
        end_us=190_000_000,
        subject_id="s",
        extractor_id="x",
        baseline_quality=0.8,
        id_start=0,
    )
    assert len(ev) == 1
    e = ev[0]
    assert e.event_type == "blink_rate_change" and e.level is EvidenceLevel.INTERPRETATION
    assert "elevated" in e.label and e.contributions[0].direction == "increase"
    assert e.start_us >= 100_000_000 - 30_000_000
    steady = ref + [int(t * 1e6) for t in np.arange(100, 190, 4.0)]
    assert (
        blink_rate_events(
            steady,
            start_us=40_000_000,
            end_us=190_000_000,
            subject_id="s",
            extractor_id="x",
            baseline_quality=0.8,
            id_start=0,
        )
        == []
    )


def test_narrative_mentions_key_facts_and_disclaimer() -> None:
    events = [
        Event(
            event_id="ev_1",
            subject_id="s",
            source="video",
            event_type="blink",
            level=EvidenceLevel.INTERPRETATION,
            start_us=50_000_000,
            end_us=50_200_000,
            label="blink",
            severity=0,
            confidence=1,
            quality=1,
            baseline_quality=0.8,
            extractor_id="x",
        ),
    ]
    lines = build_narrative(
        duration_us=120_000_000,
        quality={"face_coverage": 0.98, "mean_face_quality": 0.9},
        baseline={"quality": 0.8, "frames_used": 500, "window_end_us": 40_000_000},
        state_baselines={"silent": {"frames_used": 200}, "speaking": {"frames_used": 300}},
        events=events,
        audio={"speech_fraction": 0.6, "snr_db": 20.0, "speech_segments": 4},
        mode="live",
    )
    text = " ".join(lines)
    assert "98%" in text and "silent 200" in text and "1 blinks" in text and "60%" in text
    assert "No signal left its baseline" in text
    assert "truthfulness" in text


def test_token_middleware_and_cert(tmp_path, monkeypatch) -> None:
    app = FastAPI()
    tok = new_token()
    app.add_middleware(TokenMiddleware, token=tok)

    @app.get("/x")
    def x() -> dict[str, str]:
        return {"ok": "1"}

    c = TestClient(app)
    assert c.get("/x").status_code == 401
    assert c.get("/x", headers={"x-lightman-token": "wrong"}).status_code == 401
    r = c.get("/x", params={"token": tok}, follow_redirects=False)
    assert r.status_code == 303 and "lightman_token" in r.cookies
    assert c.get("/x").status_code == 200  # cookie kept by the client
    monkeypatch.setattr("lightman.api.security.user_config_dir", lambda *_a, **_k: str(tmp_path))
    cert, key = ensure_self_signed_cert(["192.168.1.10", "myhost"])
    assert cert.is_file() and key.is_file() and tls_dir() == tmp_path / "tls"
    assert cert.read_bytes().startswith(b"-----BEGIN CERTIFICATE-----")
    assert (cert, key) == ensure_self_signed_cert(["192.168.1.10"])  # reused, not regenerated
