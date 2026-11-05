import numpy as np

from lightman.practice.affect import StreamingAffect, affect_series, affect_summary, raw_affect
from lightman.practice.conversation import engagement, talk_time


def _aus(n: int) -> dict[str, np.ndarray]:
    return {f"au.AU{k}": np.full(n, 0.1) for k in (1, 2, 4, 5, 6, 9, 10, 12, 15, 20, 25, 26)}


def test_raw_affect_directions() -> None:
    n = 4
    base = _aus(n)
    smile = {**base, "au.AU12": np.full(n, 0.9), "au.AU6": np.full(n, 0.8)}
    frown = {**base, "au.AU4": np.full(n, 0.9), "au.AU15": np.full(n, 0.8)}
    wide = {**base, "au.AU5": np.full(n, 0.9), "au.AU26": np.full(n, 0.8)}
    v0, a0 = raw_affect(base, n)
    assert raw_affect(smile, n)[0][0] > v0[0] > raw_affect(frown, n)[0][0]
    assert raw_affect(wide, n)[1][0] > a0[0]
    bs = {
        "blendshape.mouthSmileLeft": np.full(n, 0.8),
        "blendshape.mouthSmileRight": np.full(n, 0.8),
    }
    v_bs, _ = raw_affect(bs, n)
    assert np.isfinite(v_bs).all() and v_bs[0] > 0.5


def test_affect_series_is_relative_to_calibration() -> None:
    n = 600
    t = (np.arange(n) * 100_000).astype(np.int64)  # 60 s
    rng = np.random.default_rng(0)
    vals = {k: v + rng.normal(0, 0.03, n) for k, v in _aus(n).items()}
    vals["au.AU12"][400:500] = 0.85  # smiling from 40 to 50 s
    vals["au.AU6"][400:500] = 0.7
    s = affect_series(t, vals, np.ones(n), calibration_end_us=30_000_000)
    assert abs(float(np.nanmean(s["valence"][100:250]))) < 0.2  # calibration level is zero
    assert float(np.nanmean(s["valence"][420:480])) > 0.6
    summ = affect_summary(t, s, 30_000_000)
    assert summ["valence_mean"] is not None and summ["positive_share"] > 0.25


def test_streaming_affect_matches_direction() -> None:
    sa = StreamingAffect()
    base = {f"au.AU{k}": 0.1 for k in (1, 2, 4, 5, 6, 9, 10, 12, 15, 20, 26)}
    rng = np.random.default_rng(1)
    for _ in range(50):
        sa.learn({k: v + float(rng.normal(0, 0.02)) for k, v in base.items()}, 1.0)
    sa.finish_learning()
    out = None
    for _ in range(20):
        out = sa.update({**base, "au.AU12": 0.9, "au.AU6": 0.8}, 1.0)
    assert out is not None and out[0] > 0.5
    assert sa.update(base, 0.1) is None  # low quality frames are skipped


def test_talk_time_splits_by_mouth_movement() -> None:
    n = 900
    t = (np.arange(n) * 100_000).astype(np.int64)  # 90 s
    rng = np.random.default_rng(2)
    jaw = np.full(n, 0.05) + rng.normal(0, 0.003, n)
    speaking = np.zeros(n, dtype=bool)
    speaking[100:400] = True  # 30 s of speech with the mouth moving: client
    jaw[100:400] = 0.05 + 0.2 * np.abs(np.sin(np.arange(300) * 1.3))
    speaking[500:700] = True  # 20 s of speech with a still mouth: practitioner
    res = talk_time(t, speaking, np.ones(n, dtype=bool), {"blendshape.jawOpen": jaw})
    assert res is not None
    assert 27 <= res["client_s"] <= 31 and 18 <= res["other_s"] <= 21
    assert 0.55 <= res["client_share"] <= 0.65
    assert res["client_turns"] == 1 and res["other_turns"] == 1
    assert talk_time(t, np.zeros(n, dtype=bool), np.ones(n, dtype=bool), {}) is None


def test_engagement_uses_the_resting_orientation() -> None:
    n = 300
    t = (np.arange(n) * 100_000).astype(np.int64)
    yaw = np.full(n, 12.0)  # camera off to the side: this person rests at 12 deg
    yaw[200:250] = 50.0  # really turned away for 5 s
    vals = {"head.yaw_deg": yaw, "gaze.horizontal": np.zeros(n), "gaze.vertical": np.zeros(n)}
    e = engagement(t, np.ones(n, dtype=bool), vals, {"head.yaw_deg": 12.0})
    assert abs(e["share"] - (250 / 300)) < 0.02
    assert e["windows"] and min(w["share"] for w in e["windows"]) < 0.6
    e0 = engagement(t, np.ones(n, dtype=bool), vals, {})
    assert e0["share"] > 0.8  # 12 deg is within 25 even without the center
