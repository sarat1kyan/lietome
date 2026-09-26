"""Regression tests for the issues found on the 17 September test sessions."""

import numpy as np

from lightman.api.security import is_local_client
from lightman.events.gaze import StreamingGazeAway, detect_gaze_away
from lightman.features.rppg import PulseEstimate, pulse_events, skin_rois
from lightman.interpretation.cues import deception_cue_index
from lightman.interpretation.expressions import (
    StreamingExpressionDetector,
    detect_expression_patterns,
    pattern_scores,
)


def test_gaze_away_is_measured_from_the_resting_gaze() -> None:
    n = 300
    t = (np.arange(n) * 100_000).astype(np.int64)
    h = np.full(n, 0.32)  # this person rests looking off the lens
    v = np.full(n, -0.1)
    yaw = np.zeros(n)
    h[150:190] = 0.95  # a real look away, relative to rest
    kw = {"subject_id": "s", "extractor_id": "x", "baseline_quality": 1.0, "id_start": 0}
    absolute = detect_gaze_away(t_us=t, quality=np.ones(n), gaze_h=h, gaze_v=v, yaw_deg=yaw, **kw)
    # absolute thresholds: the resting 0.33 keeps the episode open to the end of the recording
    assert len(absolute) == 1 and absolute[0].end_us - absolute[0].start_us > 10_000_000
    rel = detect_gaze_away(
        t_us=t, quality=np.ones(n), gaze_h=h, gaze_v=v, yaw_deg=yaw,
        center_h=0.32, center_v=-0.1, center_yaw=0.0, **kw,
    )  # fmt: skip
    assert len(rel) == 1 and 14_900_000 <= rel[0].start_us <= 15_100_000
    assert rel[0].end_us - rel[0].start_us < 5_000_000
    st = StreamingGazeAway(
        subject_id="s", extractor_id="x", baseline_quality=1.0, id_start=0,
        frame_period_us=100_000, center_h=0.32, center_v=-0.1,
    )  # fmt: skip
    live = []
    for i in range(n):
        live += st.update(int(t[i]), 1.0, float(h[i]), float(v[i]), 0.0)
    assert len(live) == 1


def _aus(n: int) -> dict[str, np.ndarray]:
    names = ["AU1", "AU2", "AU4", "AU5", "AU6", "AU7", "AU9", "AU10", "AU12", "AU15", "AU20",
             "AU23", "AU24", "AU25", "AU26", "AU32"]  # fmt: skip
    return {f"au.{a}": np.full(n, 0.1) for a in names}


def test_fast_onset_needs_a_rise_from_rest() -> None:
    n = 60
    t = (np.arange(n) * 66_667).astype(np.int64)
    sig = _aus(n)
    # A: from rest straight to peak -> candidate
    sig["au.AU9"][10:14] = 0.9
    sig["au.AU15"][10:14] = 0.9
    # B: already half-raised (0.45, above rest, below entry) for a second, then a brief peak
    sig["au.AU24"][30:45] = 0.45
    sig["au.AU24"][45:48] = 0.9
    ev = detect_expression_patterns(
        t_us=t, quality=np.ones(n), signals=sig, subject_id="s", extractor_id="x",
        baseline_quality=1.0,
    )  # fmt: skip
    disgust = next(e for e in ev if "disgust" in e.tags)
    press = next(e for e in ev if "lip press" in e.tags)
    assert "fast_onset" in disgust.tags
    assert "brief" in press.tags and "fast_onset" not in press.tags
    st = StreamingExpressionDetector(
        subject_id="s", extractor_id="x", baseline_quality=1.0, frame_period_us=66_667
    )
    live = []
    for i in range(n):
        live += st.update(int(t[i]), 1.0, {k: float(v[i]) for k, v in sig.items()})
    live += st.flush(int(t[-1]))
    assert "fast_onset" in next(e for e in live if "disgust" in e.tags).tags
    assert "fast_onset" not in next(e for e in live if "lip press" in e.tags).tags
    meter = st.meter()
    assert meter and {"name", "score", "enter"} <= set(meter[0])


def test_embarrassment_gaze_condition_is_relative_to_rest() -> None:
    n = 20
    sig = _aus(n)
    sig["au.AU12"][:] = 0.8
    sig["gaze.vertical"] = np.full(n, -0.34)  # resting gaze already low (camera above screen)
    assert pattern_scores(sig, n)["embarrassment"][5] > 0.5
    assert pattern_scores(sig, n, {"gaze.vertical": -0.34})["embarrassment"][5] == 0.0


def test_pulse_reference_requires_a_usable_window() -> None:
    noisy = [PulseEstimate(t_us=i * 1_000_000, bpm=48.0 + (i % 5), snr_db=-3.0) for i in range(80)]
    for i in (3, 9, 17, 25, 31, 40, 52, 60, 70):
        noisy[i] = PulseEstimate(t_us=noisy[i].t_us, bpm=48.0, snr_db=5.0)
    ev, summary = pulse_events(
        noisy, subject_id="s", extractor_id="x", baseline_quality=1.0, id_start=0
    )
    assert ev == [] and summary["reference_bpm"] is None
    assert summary["usable_fraction"] is not None and summary["usable_fraction"] < 0.25


def test_whole_session_index_is_discounted() -> None:
    cues = [
        {"key": "pitch", "name": "higher voice pitch", "value": 1.5, "present": True},
        {"key": "lip_press", "name": "pressed lips", "value": 1.5, "present": True},
        {"key": "tension", "name": "tension", "value": 1.5, "present": True},
    ]
    q = deception_cue_index({"window_us": [0, 60_000_000], "cues": cues})
    s = deception_cue_index({"window_us": [0, 60_000_000], "cues": cues, "whole_session": True})
    assert s["reliability"] < q["reliability"] and s["value"] < q["value"]


def test_local_clients_skip_the_token_unless_proxied() -> None:
    assert is_local_client("127.0.0.1", {}) and is_local_client("::1", {})
    assert not is_local_client("192.168.1.20", {})
    assert not is_local_client(None, {})
    assert not is_local_client("127.0.0.1", {"x-forwarded-for": "203.0.113.9"})


def test_skin_rois_are_normalized_boxes() -> None:
    lm = np.full((478, 2), 0.5, dtype=np.float32)
    lm[10] = (0.5, 0.2)
    lm[105] = (0.42, 0.33)
    lm[334] = (0.58, 0.33)
    lm[70] = (0.35, 0.3)
    lm[300] = (0.65, 0.3)
    lm[50] = (0.38, 0.6)
    lm[280] = (0.62, 0.6)
    lm[234] = (0.25, 0.5)
    lm[454] = (0.75, 0.5)
    boxes = skin_rois(lm)
    assert len(boxes) == 3
    assert all(0.0 <= v <= 1.0 for b in boxes for v in b)
    fx0, fy0, fx1, fy1 = boxes[0]
    assert fx0 < fx1 and fy0 < fy1


def test_live_analyzer_prefers_browser_skin_means() -> None:
    from lightman.config import BaselineConfig, LightmanConfig, ModelsConfig
    from lightman.live.analyzer import LiveAnalyzer
    from tests.unit.test_pipeline_fake import FakeLandmarker

    cfg = LightmanConfig(
        baseline=BaselineConfig(window_s=1.0, min_samples=10, good_samples=30),
        models=ModelsConfig(allow_download=False),
    )
    an = LiveAnalyzer(cfg, FakeLandmarker())  # type: ignore[arg-type]
    rgb = np.full((120, 160, 3), 90, dtype=np.uint8)
    an.client_skin[0] = (150.0, 110.0, 95.0)
    an.process_frame(rgb, 0)
    an.process_frame(rgb, 33_333)
    assert an.skin_from_client == 1 and an.skin_from_jpeg == 1
    cols = an.builder.to_numpy()
    assert (
        abs(float(cols["skin.r"][0]) - 150.0) < 1e-3 and abs(float(cols["skin.r"][1]) - 90.0) < 1e-3
    )


def test_phase_hint_stops_counting_as_speech_after_calibration() -> None:
    from lightman.config import BaselineConfig, LightmanConfig, ModelsConfig
    from lightman.live.analyzer import LiveAnalyzer
    from tests.unit.test_pipeline_fake import FakeLandmarker

    cfg = LightmanConfig(
        baseline=BaselineConfig(window_s=1.0, min_samples=10, good_samples=30),
        models=ModelsConfig(allow_download=False),
    )
    an = LiveAnalyzer(cfg, FakeLandmarker())  # type: ignore[arg-type]
    an.speaking_hint = True  # last calibration phase was "talk"; no microphone
    rgb = np.full((120, 160, 3), 90, dtype=np.uint8)
    for i in range(60):
        an.process_frame(rgb, i * 33_333)
    assert an.baseline.ready
    spk = an.builder.to_numpy()["speaking"]
    ready_at = int(np.argmax(spk == 0)) if not spk.all() else len(spk)
    assert ready_at < len(spk) and not spk[ready_at + 1 :].any()
