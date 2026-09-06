import numpy as np

from lightman.baseline.adaptive import AdaptiveConfig
from lightman.baseline.robust import compute_leading_window_baseline
from lightman.config import BaselineConfig, EventsConfig
from lightman.events.deviation import detect_deviation_events
from lightman.live.streaming import StreamingDeviationDetector


def _series(n: int = 3600, fps: int = 30):
    """Narrow calibration (first 40 s), then a persistently wider but centered distribution."""
    t_us = (np.arange(n) * (1_000_000 // fps)).astype(np.int64)
    rng = np.random.default_rng(11)
    x = np.where(t_us <= 40_000_000, rng.normal(0.05, 0.02, n), rng.normal(0.08, 0.10, n))
    return t_us, np.clip(x, 0, 1)


def test_adaptive_reduces_events_from_a_wider_but_stable_distribution() -> None:
    t_us, x = _series()
    q = np.ones(t_us.size)
    sig = {"blendshape.browInnerUp": x}
    baseline = compute_leading_window_baseline(t_us, q, sig, BaselineConfig(window_s=40))
    cfg = EventsConfig(signals=["blendshape.browInnerUp"])
    fixed = detect_deviation_events(
        t_us=t_us,
        quality=q,
        signals=sig,
        baseline=baseline,
        cfg=cfg,
        subject_id="s",
        extractor_id="x",
    )
    adaptive = detect_deviation_events(
        t_us=t_us,
        quality=q,
        signals=sig,
        baseline=baseline,
        cfg=cfg,
        subject_id="s",
        extractor_id="x",
        adaptive=AdaptiveConfig(half_life_s=20.0),
    )
    assert len(fixed) > 20
    assert len(adaptive) < len(fixed) * 0.5
    # a genuine excursion far beyond the bounded scale still fires
    x2 = x.copy()
    x2[3000:3040] = 0.95
    ev = detect_deviation_events(
        t_us=t_us,
        quality=q,
        signals={"blendshape.browInnerUp": x2},
        baseline=baseline,
        cfg=cfg,
        subject_id="s",
        extractor_id="x",
        adaptive=AdaptiveConfig(half_life_s=20.0),
    )
    assert any(abs(e.start_us - 100_000_000) < 200_000 for e in ev)


def test_streaming_detector_uses_center_scale_provider() -> None:
    t_us, x = _series(600)
    baseline = compute_leading_window_baseline(
        t_us, np.ones(t_us.size), {"blendshape.browInnerUp": x}, BaselineConfig(window_s=10)
    )
    calls: list[str] = []

    def provider(state: str, name: str):
        calls.append(state)
        return 0.08, 0.10  # a widened baseline: values near 0.08 +- 0.3 are not events

    det = StreamingDeviationDetector(
        EventsConfig(signals=["blendshape.browInnerUp"]),
        baseline,
        subject_id="s",
        extractor_id="x",
        frame_period_us=33_333,
        center_scale=provider,
    )
    out = []
    for i in range(300, 600):
        out += det.update(int(t_us[i]), 1.0, {"blendshape.browInnerUp": 0.2}, state="speaking")
    out += det.flush()
    assert out == [] and calls and calls[0] == "speaking"
