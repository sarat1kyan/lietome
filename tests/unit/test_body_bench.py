import json
from pathlib import Path

import numpy as np
import pytest

from lightman.body.events import StreamingBodyEvents, detect_body_events
from lightman.body.features import BodyFeatures, body_points
from lightman.core import bench
from lightman.interpretation.cues import cue_profile


def _pose(shoulder_y: float = 0.8, wrist: tuple[float, float] = (0.2, 0.95)) -> np.ndarray:
    lm = np.zeros((33, 4), dtype=np.float32)
    lm[:, 3] = 1.0
    lm[11] = (0.35, shoulder_y, 0, 1)
    lm[12] = (0.65, shoulder_y, 0, 1)
    lm[13] = (0.3, 0.9, 0, 1)
    lm[14] = (0.7, 0.9, 0, 1)
    for i in (15, 17, 19, 21):
        lm[i] = (*wrist, 0, 1)
    for i in (16, 18, 20, 22):
        lm[i] = (0.8, 0.95, 0, 1)
    return lm


def test_body_features_normalize_by_the_face() -> None:
    bf = BodyFeatures()
    face = (0.4, 0.2, 0.6, 0.5)  # width 0.2, height 0.3, center y 0.35
    f0 = bf.compute(_pose(), face, 0, 1.0)
    assert f0["body.shoulder_y"] == pytest.approx((0.8 - 0.35) / 0.3)
    assert abs(f0["body.shoulder_tilt_deg"]) < 1e-6 and np.isnan(f0["body.hand_speed"])
    assert f0["body.hand_face"] > 1.0
    f1 = bf.compute(_pose(wrist=(0.5, 0.35)), face, 100_000, 1.0)  # hand moved onto the face
    assert f1["body.hand_face"] == 0.0 and f1["body.hand_speed"] > 5
    assert np.isnan(bf.compute(None, face, 200_000, 1.0)["body.shoulder_y"])
    pts = body_points(_pose())
    assert pts is not None and len(pts["shoulders"]) == 2 and len(pts["wrists"]) == 2


def test_self_touch_and_shrug_offline_and_streaming() -> None:
    n = 200
    t = (np.arange(n) * 100_000).astype(np.int64)
    hf = np.full(n, 1.2)
    hf[50:60] = 0.0  # 1 s on the face
    hf[80:82] = 0.0  # 0.2 s: too short
    sy = np.full(n, 1.5)
    sy[120:125] = 1.2  # shoulders up 0.3 face heights for 0.5 s
    kw = {"subject_id": "s", "extractor_id": "x", "baseline_quality": 1.0, "id_start": 0}
    ev = detect_body_events(
        t_us=t, hand_face=hf, shoulder_y=sy, shoulder_center=1.5, shoulder_scale=0.02,
        start_us=0, **kw,
    )  # fmt: skip
    assert [e.event_type for e in ev] == ["self_touch", "shrug"]
    assert ev[0].start_us == 5_000_000 and "1.0 s" in ev[0].label
    st = StreamingBodyEvents(
        shoulder_center=1.5, shoulder_scale=0.02, frame_period_us=100_000, **kw
    )
    live = []
    for i in range(n):
        live += st.update(int(t[i]), float(hf[i]), float(sy[i]))
    live += st.flush(int(t[-1]))
    assert [e.event_type for e in live] == ["self_touch", "shrug"]


def test_movement_cue_prefers_hand_speed() -> None:
    n = 300
    t = (np.arange(n) * 100_000).astype(np.int64)
    sig = {"head.speed_deg_s": np.full(n, 8.0), "body.hand_speed": np.full(n, 3.0)}
    sig["body.hand_speed"][100:250] = 0.5  # hands went still
    prof = cue_profile(
        window=(10_000_000, 25_000_000), t_us=t, signals=sig,
        baseline_center={"head.speed_deg_s": 8.0, "body.hand_speed": 3.0},
        baseline_scale={"head.speed_deg_s": 2.0, "body.hand_speed": 1.0},
        voice_f0_z=None, blink_times_us=[], reference_blink_rate=None,
        response_latency_ms=None, control_latency_ms=None,
    )  # fmt: skip
    mv = next(r for r in prof["cues"] if r["key"] == "movement")
    assert mv["present"] and mv["value"] < -2


def test_live_au_model_follows_the_benchmark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "bench.json"
    monkeypatch.setattr(bench, "bench_path", lambda: p)
    assert bench.live_au_model("auto") == bench.RESNET18  # no benchmark yet
    assert bench.live_au_model(bench.RESNET50) == bench.RESNET50  # explicit wins
    p.write_text(json.dumps({"models": {bench.RESNET50: {"p95_ms": 30.0}}}))
    assert bench.live_au_model("auto") == bench.RESNET50
    p.write_text(json.dumps({"models": {bench.RESNET50: {"p95_ms": 80.0}}}))
    assert bench.live_au_model("auto") == bench.RESNET18
    p.write_text("{broken")
    assert bench.live_au_model("auto") == bench.RESNET18
