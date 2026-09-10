import numpy as np

from lightman.events.gestures import StreamingHeadGestures, detect_head_gestures
from lightman.features.rppg import (
    StreamingPulse,
    estimate_pulse,
    pulse_events,
    skin_means,
)
from lightman.interpretation.novelty import AUNoveltyDetector, detect_au_novelty
from lightman.schema.events import EvidenceLevel


def _color_trace(bpm: float, seconds: float, fps: float, amp: float = 0.6):
    n = int(seconds * fps)
    t_us = (np.arange(n) * 1e6 / fps).astype(np.int64)
    ph = 2 * np.pi * (bpm / 60.0) * t_us / 1e6
    rng = np.random.default_rng(1)
    # pulse mostly in green, some in red/blue, plus drift and noise
    drift = 2.0 * np.sin(2 * np.pi * 0.05 * t_us / 1e6)
    r = 150 + 0.3 * amp * np.sin(ph) + drift + rng.normal(0, 0.3, n)
    g = 110 + 1.0 * amp * np.sin(ph) + drift + rng.normal(0, 0.3, n)
    b = 95 + 0.5 * amp * np.sin(ph) + drift + rng.normal(0, 0.3, n)
    return t_us, r, g, b


def test_pulse_estimate_recovers_synthetic_rate_and_flags_change() -> None:
    fps = 13.0
    t1, r1, g1, b1 = _color_trace(66.0, 60.0, fps)
    t2, r2, g2, b2 = _color_trace(96.0, 30.0, fps)
    t = np.concatenate([t1, t2 + t1[-1] + int(1e6 / fps)])
    r, g, b = np.concatenate([r1, r2]), np.concatenate([g1, g2]), np.concatenate([b1, b2])
    q = np.ones(t.size)
    est = estimate_pulse(t, r, g, b, q)
    assert len(est) > 60
    early = [e.bpm for e in est if e.t_us <= 40_000_000]
    late = [e.bpm for e in est if e.t_us >= 75_000_000]
    assert abs(np.median(early) - 66.0) <= 3.0
    assert abs(np.median(late) - 96.0) <= 3.0
    assert np.median([e.snr_db for e in est]) > 3.0
    events, summary = pulse_events(
        est, subject_id="s", extractor_id="x", baseline_quality=1.0, id_start=0
    )
    assert summary["reference_bpm"] is not None and abs(summary["reference_bpm"] - 66) <= 3
    assert len(events) == 1 and events[0].level is EvidenceLevel.OBSERVATION
    assert "up" in events[0].label and events[0].start_us >= 62_000_000


def test_pulse_noise_has_low_snr_and_no_events() -> None:
    rng = np.random.default_rng(3)
    n = 13 * 60
    t = (np.arange(n) * 1e6 / 13).astype(np.int64)
    r, g, b = (150 + rng.normal(0, 2, n), 110 + rng.normal(0, 2, n), 95 + rng.normal(0, 2, n))
    est = estimate_pulse(t, r, g, b, np.ones(n))
    assert est and np.median([e.snr_db for e in est]) < 3.0
    events, summary = pulse_events(
        est, subject_id="s", extractor_id="x", baseline_quality=1.0, id_start=0
    )
    assert events == [] and (summary["usable_fraction"] or 0) < 0.5


def test_streaming_pulse_matches_offline_rate() -> None:
    t, r, g, b = _color_trace(72.0, 30.0, 13.0)
    sp = StreamingPulse()
    for i in range(t.size):
        sp.push(int(t[i]), (float(r[i]), float(g[i]), float(b[i])), 1.0)
    assert sp.latest is not None and abs(sp.latest.bpm - 72.0) <= 3.0
    assert len(sp.estimates) >= 15


def test_skin_means_uses_forehead_and_cheeks() -> None:
    rgb = np.zeros((100, 100, 3), dtype=np.uint8)
    rgb[..., 0] = 200
    lm = np.zeros((478, 3), dtype=np.float32)
    lm[:, 0] = 0.5
    lm[:, 1] = 0.5
    lm[10] = (0.5, 0.1, 0)  # forehead top
    lm[105] = (0.4, 0.3, 0)
    lm[334] = (0.6, 0.3, 0)
    lm[70] = (0.3, 0.3, 0)
    lm[300] = (0.7, 0.3, 0)
    lm[50] = (0.35, 0.6, 0)
    lm[280] = (0.65, 0.6, 0)
    lm[234] = (0.2, 0.5, 0)
    lm[454] = (0.8, 0.5, 0)
    r, g, b = skin_means(rgb, lm, 100, 100)
    assert (r, g, b) == (200.0, 0.0, 0.0)


def _head(n: int, fps: float, nod_at: tuple[float, float], shake_at: tuple[float, float]):
    t = (np.arange(n) * 1e6 / fps).astype(np.int64)
    s = t / 1e6
    pitch = np.zeros(n)
    yaw = np.zeros(n)
    m = (s >= nod_at[0]) & (s < nod_at[1])
    pitch[m] = 5.0 * np.sin(2 * np.pi * 2.0 * (s[m] - nod_at[0]))  # 2 Hz nod, 10 deg swing
    m2 = (s >= shake_at[0]) & (s < shake_at[1])
    yaw[m2] = 6.0 * np.sin(2 * np.pi * 1.5 * (s[m2] - shake_at[0]))
    return t, yaw, pitch


def test_head_gestures_offline_and_streaming_agree() -> None:
    t, yaw, pitch = _head(300, 15.0, nod_at=(3.0, 4.5), shake_at=(10.0, 12.0))
    q = np.ones(t.size)
    ev = detect_head_gestures(
        t_us=t, quality=q, yaw_deg=yaw, pitch_deg=pitch,
        subject_id="s", extractor_id="x", baseline_quality=1.0, id_start=0,
    )  # fmt: skip
    kinds = [e.tags[1] for e in ev]
    assert kinds == ["nod", "shake"], [e.label for e in ev]
    nod, shake = ev
    assert 2_900_000 <= nod.start_us <= 3_600_000 and nod.end_us <= 4_700_000
    assert 9_900_000 <= shake.start_us <= 10_700_000
    assert nod.level is EvidenceLevel.OBSERVATION and "cycles" in nod.label
    st = StreamingHeadGestures(subject_id="s", extractor_id="x", baseline_quality=1.0, id_start=0)
    live = []
    for i in range(t.size):
        live += st.update(int(t[i]), 1.0, float(yaw[i]), float(pitch[i]))
    assert [e.tags[1] for e in live] == ["nod", "shake"], [e.label for e in live]


def test_still_head_and_slow_drift_produce_no_gesture() -> None:
    n = 200
    t = (np.arange(n) * 1e6 / 15).astype(np.int64)
    drift = 8.0 * np.sin(2 * np.pi * 0.1 * t / 1e6)  # 10 s period: posture change, not a nod
    ev = detect_head_gestures(
        t_us=t, quality=np.ones(n), yaw_deg=drift, pitch_deg=drift * 0 + 0.2,
        subject_id="s", extractor_id="x", baseline_quality=1.0, id_start=0,
    )  # fmt: skip
    assert ev == []


def test_au_novelty_reports_new_combination_once() -> None:
    det = AUNoveltyDetector(subject_id="s", extractor_id="x", id_start=0, min_ms=300)
    base = {"au.AU1": 0.1, "au.AU4": 0.1, "au.AU7": 0.1, "au.AU23": 0.1, "au.AU12": 0.1}
    smile = {**base, "au.AU12": 0.9, "au.AU6": 0.8}
    for i in range(20):
        det.update(i * 66_000, 1.0, smile if i % 2 else base)
    det.finish_learning(0.9)
    out = []
    for i in range(20, 60):
        out += det.update(i * 66_000, 1.0, smile)  # familiar
    assert out == []
    tense = {**base, "au.AU4": 0.8, "au.AU7": 0.7, "au.AU23": 0.9}
    for i in range(60, 70):
        out += det.update(i * 66_000, 1.0, tense)
    assert len(out) == 1 and out[0].label == "new AU pairing: AU4+AU7+AU23"
    assert out[0].level is EvidenceLevel.INTERPRETATION
    for i in range(70, 90):
        out += det.update(i * 66_000, 1.0, tense)
    assert len(out) == 1  # reported once
    # two frames only: too short
    flash = {**base, "au.AU9": 0.9, "au.AU10": 0.9}
    for i in range(90, 93):
        out += det.update(i * 66_000, 1.0, flash if i < 92 else base)
    assert len(out) == 1


def test_detect_au_novelty_offline_wrapper() -> None:
    n = 100
    t = (np.arange(n) * 66_000).astype(np.int64)
    sig = {c: np.full(n, 0.1) for c in ("au.AU4", "au.AU7", "au.AU23", "au.AU12")}
    sig["au.AU4"][60:] = 0.9
    sig["au.AU7"][60:] = 0.9
    ev = detect_au_novelty(
        t_us=t, quality=np.ones(n), signals=sig, calibration_end_us=int(t[40]),
        subject_id="s", extractor_id="x", baseline_quality=1.0, id_start=0,
    )  # fmt: skip
    assert len(ev) == 1 and ev[0].tags == ["novelty", "AU4", "AU7"]
    assert "AU4 with AU7" in ev[0].description
