"""Streaming detectors must agree with the offline ones on the same series (up to documented
differences), and the live runner must work end to end with a file source and fake models."""

from __future__ import annotations

import threading
from pathlib import Path

import numpy as np

from lightman.baseline.robust import compute_leading_window_baseline
from lightman.config import BaselineConfig, EventsConfig, LightmanConfig, ModelsConfig
from lightman.events.blinks import blink_threshold, detect_blinks
from lightman.events.deviation import detect_deviation_events
from lightman.live.runner import run_live
from lightman.live.sources import FileSource
from lightman.live.streaming import (
    StreamingBaseline,
    StreamingBlinkDetector,
    StreamingDeviationDetector,
)
from tests.conftest import noise_frames, write_video
from tests.unit.test_pipeline_fake import FakeLandmarker


def _series(n: int = 900, fps: int = 30):
    t_us = (np.arange(n) * (1_000_000 // fps)).astype(np.int64)
    rng = np.random.default_rng(7)
    brow = rng.normal(0.05, 0.01, n)
    brow[600:620] = 0.6
    brow[700:702] = 0.9  # too short for min_duration
    ear = rng.normal(0.30, 0.005, n)
    ear[400:405] = 0.05
    return t_us, brow, ear


def test_streaming_baseline_matches_offline() -> None:
    t_us, brow, ear = _series()
    quality = np.ones(t_us.size)
    cfg = BaselineConfig(window_s=10)
    offline = compute_leading_window_baseline(
        t_us, quality, {"blendshape.browDownLeft": brow, "eye.aspect_ratio_mean": ear}, cfg
    )
    sb = StreamingBaseline(cfg, ["blendshape.browDownLeft", "eye.aspect_ratio_mean"])
    for i in range(t_us.size):
        sb.update(
            int(t_us[i]), 1.0, {"blendshape.browDownLeft": brow[i], "eye.aspect_ratio_mean": ear[i]}
        )
        if sb.ready:
            break
    assert sb.ready and sb.snapshot is not None
    for name in offline.signals:
        assert sb.snapshot.signals[name].center == offline.signals[name].center
        assert sb.snapshot.signals[name].scale == offline.signals[name].scale
        assert sb.snapshot.signals[name].n == offline.signals[name].n
    assert sb.snapshot.quality == offline.quality


def test_streaming_deviation_and_blink_match_offline() -> None:
    t_us, brow, ear = _series()
    quality = np.ones(t_us.size)
    bcfg = BaselineConfig(window_s=10)
    ecfg = EventsConfig(signals=["blendshape.browDownLeft"])
    signals = {"blendshape.browDownLeft": brow, "eye.aspect_ratio_mean": ear}
    baseline = compute_leading_window_baseline(t_us, quality, signals, bcfg)
    off_dev = detect_deviation_events(
        t_us=t_us,
        quality=quality,
        signals=signals,
        baseline=baseline,
        cfg=ecfg,
        subject_id="s",
        extractor_id="x",
    )
    off_blinks = detect_blinks(
        t_us=t_us,
        quality=quality,
        ear=ear,
        baseline=baseline,
        cfg=ecfg,
        subject_id="s",
        extractor_id="x",
    )
    dev = StreamingDeviationDetector(
        ecfg, baseline, subject_id="s", extractor_id="x", frame_period_us=33_333
    )
    blk = StreamingBlinkDetector(
        ecfg,
        blink_threshold(baseline, ecfg),
        baseline=baseline,
        subject_id="s",
        extractor_id="x",
        frame_period_us=33_333,
    )
    got_dev, got_blk = [], []
    for i in range(t_us.size):
        got_dev += dev.update(int(t_us[i]), 1.0, {"blendshape.browDownLeft": brow[i]})
        got_blk += blk.update(int(t_us[i]), 1.0, float(ear[i]))
    got_dev += dev.flush()
    assert len(got_dev) == len(off_dev) == 1
    assert got_dev[0].start_us == off_dev[0].start_us
    assert got_dev[0].peak_us == off_dev[0].peak_us
    assert abs(got_dev[0].end_us - off_dev[0].end_us) <= 33_333  # closing frame convention
    assert got_dev[0].contributions[0].peak_deviation == off_dev[0].contributions[0].peak_deviation
    assert len(got_blk) == len(off_blinks) == 1
    assert got_blk[0].start_us == off_blinks[0].start_us
    assert got_blk[0].event_type == "blink" and blk.blink_count == 1


def test_streaming_emits_provisional_event_for_long_open_run() -> None:
    t_us, brow, _ = _series()
    brow = brow.copy()
    brow[600:] = 0.6  # never closes
    baseline = compute_leading_window_baseline(
        t_us, np.ones(t_us.size), {"blendshape.browDownLeft": brow}, BaselineConfig(window_s=10)
    )
    dev = StreamingDeviationDetector(
        EventsConfig(signals=["blendshape.browDownLeft"]),
        baseline,
        subject_id="s",
        extractor_id="x",
        frame_period_us=33_333,
        emit_open_after_ms=1000,
    )
    got = []
    for i in range(t_us.size):
        got += dev.update(int(t_us[i]), 1.0, {"blendshape.browDownLeft": brow[i]})
    assert len(got) == 1 and "provisional" in got[0].tags
    assert abs(got[0].start_us - 20_000_000) < 40_000  # run starts at frame 600
    assert got[0].end_us - got[0].start_us >= 1_000_000
    assert dev.flush() == []  # already emitted while open


def test_run_live_with_file_source_and_fake_models(tmp_path: Path) -> None:
    video = write_video(tmp_path / "v.mp4", noise_frames(90, w=160, h=120), fps=30)
    cfg = LightmanConfig(
        baseline=BaselineConfig(window_s=1.0, min_samples=10, good_samples=30),
        models=ModelsConfig(allow_download=False),
    )
    fake = FakeLandmarker()
    seen: list = []
    session_dir = run_live(
        FileSource(video, realtime=False),
        cfg=cfg,
        out_dir=tmp_path / "out",
        landmarker=fake,
        sink=seen.append,
        stop_flag=threading.Event(),
    )
    assert fake.calls == 90
    for name in (
        "features.parquet",
        "events.json",
        "baseline.json",
        "analysis.json",
        "manifest.json",
        "report.html",
    ):
        assert (session_dir / name).is_file(), name
    types = {e.event_type for e in seen}
    assert "blink" in types and "baseline_deviation" in types
    import json

    stats = json.loads((session_dir / "analysis.json").read_text())
    assert (
        stats["mode"] == "live" and stats["frames_analyzed"] == 90 and stats["frames_dropped"] == 0
    )
    assert stats["ended_by"] == "source_end"
