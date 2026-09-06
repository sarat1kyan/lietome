import numpy as np

from lightman.baseline.robust import (
    STATE_ALL,
    STATE_SILENT,
    STATE_SPEAKING,
    compute_state_baselines,
    per_frame_center_scale,
    robust_z,
)
from lightman.config import BaselineConfig, EventsConfig
from lightman.events.deviation import detect_deviation_events
from lightman.features.smoothing import StreamingMedian, median_smooth
from lightman.live.streaming import StreamingBaseline, StreamingDeviationDetector


def _speech_series(n: int = 1800, fps: int = 30):
    """Silent first half of the window, speaking second half; jawOpen ~0 when silent, ~0.4
    while speaking. After the window the subject keeps talking."""
    t_us = (np.arange(n) * (1_000_000 // fps)).astype(np.int64)
    rng = np.random.default_rng(5)
    speaking = np.zeros(n, dtype=bool)
    speaking[450:900] = True  # 15-30 s
    speaking[900:] = True
    jaw = np.where(speaking, rng.normal(0.4, 0.08, n), np.abs(rng.normal(0.0, 0.01, n)))
    return t_us, speaking, jaw


def test_state_baselines_exist_when_window_has_both_states() -> None:
    t_us, speaking, jaw = _speech_series()
    cfg = BaselineConfig(window_s=30, min_samples=60)
    sb = compute_state_baselines(
        t_us, np.ones(t_us.size), {"blendshape.jawOpen": jaw}, cfg, speaking
    )
    assert set(sb) == {STATE_ALL, STATE_SILENT, STATE_SPEAKING}
    assert sb[STATE_SPEAKING].signals["blendshape.jawOpen"].center > 0.3
    assert sb[STATE_SILENT].signals["blendshape.jawOpen"].center < 0.05
    frame_state = np.where(speaking, STATE_SPEAKING, STATE_SILENT).astype(str)
    center, scale, _ = per_frame_center_scale("blendshape.jawOpen", sb, frame_state)
    assert center[0] < 0.05 and center[-1] > 0.3 and scale.min() > 0
    z = robust_z(jaw, center, scale)
    assert np.nanmax(np.abs(z[900:])) < 6  # speaking scored against speaking baseline


def test_speaking_after_silent_calibration_is_not_a_deviation_with_state_baselines() -> None:
    t_us, speaking, jaw = _speech_series()
    cfg = BaselineConfig(window_s=30, min_samples=60)
    signals = {"blendshape.jawOpen": jaw}
    sb = compute_state_baselines(t_us, np.ones(t_us.size), signals, cfg, speaking)
    frame_state = np.where(speaking, STATE_SPEAKING, STATE_SILENT).astype(str)
    ecfg = EventsConfig(signals=["blendshape.jawOpen"])
    with_states = detect_deviation_events(
        t_us=t_us,
        quality=np.ones(t_us.size),
        signals=signals,
        baseline=sb[STATE_ALL],
        cfg=ecfg,
        subject_id="s",
        extractor_id="x",
        state_baselines=sb,
        frame_state=frame_state,
    )
    without = detect_deviation_events(
        t_us=t_us,
        quality=np.ones(t_us.size),
        signals=signals,
        baseline=sb[STATE_SILENT],
        cfg=ecfg,
        subject_id="s",
        extractor_id="x",
    )
    assert len(without) >= 1  # silent-only baseline calls all speech a deviation
    assert len(with_states) == 0
    assert set(sb) == {STATE_ALL, STATE_SILENT, STATE_SPEAKING}


def test_streaming_state_baseline_matches_offline_and_detector_uses_state() -> None:
    t_us, speaking, jaw = _speech_series()
    cfg = BaselineConfig(window_s=30, min_samples=60)
    sb_off = compute_state_baselines(
        t_us, np.ones(t_us.size), {"blendshape.jawOpen": jaw}, cfg, speaking
    )
    sb = StreamingBaseline(cfg, ["blendshape.jawOpen"])
    i = 0
    while not sb.ready:
        sb.update(int(t_us[i]), 1.0, {"blendshape.jawOpen": jaw[i]}, speaking=bool(speaking[i]))
        i += 1
    assert set(sb.state_snapshots) == {STATE_SILENT, STATE_SPEAKING}
    for st in (STATE_SILENT, STATE_SPEAKING):
        assert (
            sb.state_snapshots[st].signals["blendshape.jawOpen"].center
            == sb_off[st].signals["blendshape.jawOpen"].center
        )
    assert sb.snapshot is not None
    det = StreamingDeviationDetector(
        EventsConfig(signals=["blendshape.jawOpen"]),
        sb.snapshot,
        subject_id="s",
        extractor_id="x",
        frame_period_us=33_333,
        state_baselines=sb.state_snapshots,
    )
    events = []
    for k in range(i, t_us.size):
        events += det.update(
            int(t_us[k]), 1.0, {"blendshape.jawOpen": jaw[k]}, state=STATE_SPEAKING
        )
    events += det.flush()
    assert events == []


def test_median_smooth_removes_single_frame_spikes() -> None:
    x = np.full(50, 0.2)
    x[20] = 0.9
    x[30] = np.nan
    y = median_smooth(x, 5)
    assert y[20] == 0.2 and np.isnan(y[30]) and y[0] == 0.2 and y[-1] == 0.2
    sm = StreamingMedian(5)
    out = [sm.push(v) for v in [0.2, 0.2, 0.9, 0.2, 0.2]]
    assert out[2] == 0.2 and out[-1] == 0.2
