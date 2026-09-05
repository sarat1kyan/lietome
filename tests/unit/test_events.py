import numpy as np

from lightman.baseline.robust import compute_leading_window_baseline
from lightman.config import BaselineConfig, EventsConfig
from lightman.events.blinks import detect_blinks
from lightman.events.deviation import cluster_cooccurring, detect_deviation_events
from lightman.events.segments import hysteresis_segments, merge_close_segments
from lightman.schema.events import EvidenceLevel


def test_hysteresis_open_close() -> None:
    score = np.array([0, 1, 3.5, 2.5, 2.1, 1.0, 0, 3.2, 3.3, 0.5])
    ok = np.ones(10, dtype=bool)
    segs = hysteresis_segments(score, ok, enter=3.0, exit_=2.0)
    assert [(s.start_idx, s.end_idx) for s in segs] == [(2, 4), (7, 8)]
    assert segs[0].peak_idx == 2 and segs[1].peak_abs == 3.3


def test_low_quality_frames_close_and_never_open() -> None:
    score = np.array([5.0, 5.0, 5.0, 5.0])
    ok = np.array([False, True, False, True])
    segs = hysteresis_segments(score, ok, enter=3.0, exit_=2.0)
    assert [(s.start_idx, s.end_idx) for s in segs] == [(1, 1), (3, 3)]


def test_merge_close_segments() -> None:
    t = np.arange(10) * 100_000  # 100 ms per frame
    segs = hysteresis_segments(
        np.array([4, 4, 0, 0, 4, 4, 0, 0, 0, 4.0]), np.ones(10, bool), enter=3, exit_=2
    )
    merged = merge_close_segments(segs, t, gap_us=300_000)  # 100ms->400ms gap = 300ms
    assert [(s.start_idx, s.end_idx) for s in merged] == [(0, 5), (9, 9)]


def _series(n: int = 900, fps: int = 30):
    t_us = (np.arange(n) * (1_000_000 // fps)).astype(np.int64)
    quality = np.ones(n)
    rng = np.random.default_rng(3)
    return t_us, quality, rng


def test_deviation_event_detected_with_contribution() -> None:
    t_us, quality, rng = _series()
    brow = rng.normal(0.05, 0.01, t_us.size)
    brow[600:620] = 0.6  # ~0.67 s excursion
    signals = {"blendshape.browDownLeft": brow}
    baseline = compute_leading_window_baseline(t_us, quality, signals, BaselineConfig(window_s=10))
    cfg = EventsConfig(signals=["blendshape.browDownLeft"])
    events = detect_deviation_events(
        t_us=t_us,
        quality=quality,
        signals=signals,
        baseline=baseline,
        cfg=cfg,
        subject_id="s",
        extractor_id="x",
    )
    assert len(events) == 1
    e = events[0]
    assert e.level is EvidenceLevel.OBSERVATION
    assert e.event_type == "baseline_deviation"
    assert 19_900_000 <= e.start_us <= 20_100_000
    assert e.contributions[0].direction == "increase"
    assert e.contributions[0].peak_deviation > 3
    assert "AU4" in e.label and "(proxy)" in e.label


def test_short_excursion_below_min_duration_is_ignored() -> None:
    t_us, quality, rng = _series()
    sig = rng.normal(0.05, 0.01, t_us.size)
    sig[600] = 0.9  # single frame (33 ms) < 120 ms
    signals = {"blendshape.jawOpen": sig}
    baseline = compute_leading_window_baseline(t_us, quality, signals, BaselineConfig(window_s=10))
    events = detect_deviation_events(
        t_us=t_us,
        quality=quality,
        signals=signals,
        baseline=baseline,
        cfg=EventsConfig(signals=["blendshape.jawOpen"]),
        subject_id="s",
        extractor_id="x",
    )
    assert events == []


def test_cluster_requires_two_distinct_signals() -> None:
    t_us, quality, rng = _series()
    a = rng.normal(0.05, 0.01, t_us.size)
    b = rng.normal(0.05, 0.01, t_us.size)
    a[600:630] = 0.7
    b[610:640] = 0.7
    signals = {"blendshape.browDownLeft": a, "blendshape.mouthPressLeft": b}
    baseline = compute_leading_window_baseline(t_us, quality, signals, BaselineConfig(window_s=10))
    cfg = EventsConfig(signals=list(signals))
    dev = detect_deviation_events(
        t_us=t_us,
        quality=quality,
        signals=signals,
        baseline=baseline,
        cfg=cfg,
        subject_id="s",
        extractor_id="x",
    )
    assert len(dev) == 2
    clusters = cluster_cooccurring(dev, subject_id="s", extractor_id="x", id_start=10)
    assert len(clusters) == 1
    c = clusters[0]
    assert c.level is EvidenceLevel.INTERPRETATION
    assert c.event_type == "multi_signal_deviation"
    assert len(c.contributions) == 2
    assert c.start_us == dev[0].start_us and c.end_us == max(d.end_us for d in dev)
    assert "psychological" in c.description  # explicit non-claim


def test_blink_detection_relative_threshold_and_exclusion() -> None:
    t_us, quality, rng = _series()
    ear = rng.normal(0.30, 0.005, t_us.size)
    ear[300:305] = 0.05  # 5 frames = 167 ms blink
    ear[700:730] = 0.05  # 1 s closure
    signals = {"eye.aspect_ratio_mean": ear}
    baseline = compute_leading_window_baseline(t_us, quality, signals, BaselineConfig(window_s=10))
    cfg = EventsConfig(signals=["eye.aspect_ratio_mean"])
    blinks = detect_blinks(
        t_us=t_us,
        quality=quality,
        ear=ear,
        baseline=baseline,
        cfg=cfg,
        subject_id="s",
        extractor_id="x",
    )
    types = [b.event_type for b in blinks]
    assert types == ["blink", "eye_closure"]
    assert all(b.level is EvidenceLevel.INTERPRETATION for b in blinks)
    dev = detect_deviation_events(
        t_us=t_us,
        quality=quality,
        signals=signals,
        baseline=baseline,
        cfg=cfg,
        subject_id="s",
        extractor_id="x",
        exclude_intervals=[(b.start_us, b.end_us) for b in blinks],
    )
    assert dev == []  # eye deviations fully covered by blink/closure events are suppressed
