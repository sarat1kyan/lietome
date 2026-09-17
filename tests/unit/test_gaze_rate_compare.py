import numpy as np

from lightman.events.gaze import StreamingGazeAway, detect_gaze_away
from lightman.features.rppg import StreamingPulse
from lightman.schema.events import EvidenceLevel


def _gaze(n: int, fps: float, away: tuple[float, float], glance: tuple[float, float]):
    t = (np.arange(n) * 1e6 / fps).astype(np.int64)
    s = t / 1e6
    h = np.zeros(n)
    v = np.zeros(n)
    yaw = np.zeros(n)
    m = (s >= away[0]) & (s < away[1])
    h[m] = 0.6  # eyes to the subject's left for a while
    g = (s >= glance[0]) & (s < glance[1])
    yaw[g] = 30.0  # short head turn: under the minimum duration
    return t, h, v, yaw


def test_gaze_away_offline_and_streaming_agree() -> None:
    t, h, v, yaw = _gaze(300, 15.0, away=(4.0, 6.5), glance=(12.0, 12.4))
    q = np.ones(t.size)
    ev = detect_gaze_away(
        t_us=t, quality=q, gaze_h=h, gaze_v=v, yaw_deg=yaw,
        subject_id="s", extractor_id="x", baseline_quality=1.0, id_start=0,
    )  # fmt: skip
    assert len(ev) == 1, [e.label for e in ev]
    e = ev[0]
    assert e.level is EvidenceLevel.OBSERVATION and e.tags == ["gaze", "left"]
    assert 3_900_000 <= e.start_us <= 4_100_000 and 6_400_000 <= e.end_us <= 6_700_000
    assert "2.5 s" in e.label or "2.4 s" in e.label or "2.6 s" in e.label
    st = StreamingGazeAway(
        subject_id="s", extractor_id="x", baseline_quality=1.0, id_start=0, frame_period_us=66_667
    )
    live = []
    for i in range(t.size):
        live += st.update(int(t[i]), 1.0, float(h[i]), float(v[i]), float(yaw[i]))
    live += st.flush(int(t[-1]))
    assert len(live) == 1 and abs(live[0].start_us - e.start_us) <= 70_000
    assert st.active_since_us is None


def test_gaze_away_head_turn_counts_and_low_quality_breaks_run() -> None:
    t, h, v, yaw = _gaze(150, 15.0, away=(0.0, 0.0), glance=(2.0, 4.0))
    q = np.ones(t.size)
    ev = detect_gaze_away(
        t_us=t, quality=q, gaze_h=h, gaze_v=v, yaw_deg=yaw,
        subject_id="s", extractor_id="x", baseline_quality=1.0, id_start=0,
    )  # fmt: skip
    assert len(ev) == 1 and "left" in ev[0].label
    q[40:50] = 0.1  # tracker lost the face in the middle: two halves under 1 s each
    ev2 = detect_gaze_away(
        t_us=t, quality=q, gaze_h=h, gaze_v=v, yaw_deg=yaw,
        subject_id="s", extractor_id="x", baseline_quality=1.0, id_start=0,
    )  # fmt: skip
    assert ev2 == []  # both halves (frames 30-39 and 50-59) are under 1 s


def test_pulse_wave_shape_and_normalization() -> None:
    fps = 13.0
    n = int(fps * 12)
    t = (np.arange(n) * 1e6 / fps).astype(np.int64)
    ph = 2 * np.pi * 1.2 * t / 1e6
    sp = StreamingPulse()
    for i in range(n):
        sp.push(
            int(t[i]),
            (150 + 0.2 * np.sin(ph[i]), 110 + 0.6 * np.sin(ph[i]), 95 + 0.3 * np.sin(ph[i])),
            1.0,
        )
    w = sp.wave()
    assert w is not None and len(w) == 45
    assert max(abs(x) for x in w) == 1.0
    assert sp.wave(seconds=0.2) is None  # too few samples


def test_speech_rate_proxy_on_amplitude_modulated_tone() -> None:
    from lightman.config import BaselineConfig, LightmanConfig
    from lightman.live.audio_stream import StreamingAudioAnalyzer
    from tests.unit.test_audio_stream import RATE, _FakeVAD

    cfg = LightmanConfig(baseline=BaselineConfig(window_s=2.0, min_samples=10, good_samples=30))
    an = StreamingAudioAnalyzer(cfg, _FakeVAD(), subject_id="s")  # type: ignore[arg-type]
    dur = 6.0
    tt = np.arange(int(RATE * dur)) / RATE
    # 4 "syllables" per second: amplitude envelope at 4 Hz on a 150 Hz tone
    env = 0.55 + 0.45 * np.sin(2 * np.pi * 4.0 * tt)
    x = (0.3 * env * np.sin(2 * np.pi * 150.0 * tt)).astype(np.float32)
    rates = []
    chunk = 2048
    for i in range(0, x.size - chunk + 1, chunk):
        res = an.push(x[i : i + chunk], int(i * 1_000_000 / RATE))
        rates.extend(r.rate_syl_s for r in res if r.rate_syl_s is not None)
    assert rates and 3.0 <= float(np.median(rates)) <= 5.0, np.median(rates)
    assert len(an.hops[0]) == 6
