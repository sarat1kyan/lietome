import numpy as np

from lightman.events.stillness import StreamingStillness, detect_stillness, stillness_threshold
from lightman.interpretation.expressions import (
    StreamingExpressionDetector,
    detect_expression_patterns,
    pattern_scores,
)
from lightman.schema.events import EvidenceLevel


def test_stillness_threshold_and_episodes_offline_and_streaming() -> None:
    assert stillness_threshold(8.0) == 2.8 and stillness_threshold(30.0) == 3.0
    assert stillness_threshold(1.0) == 1.0 and stillness_threshold(float("nan")) == 2.0
    n = 300
    t = (np.arange(n) * 100_000).astype(np.int64)  # 10 fps, 30 s
    speed = np.full(n, 12.0)
    speed[100:150] = 0.8  # 5 s still
    speed[200:215] = 0.5  # 1.5 s: too short
    ev = detect_stillness(
        t_us=t, quality=np.ones(n), speed_deg_s=speed, center_speed=12.0, start_us=5_000_000,
        subject_id="s", extractor_id="x", baseline_quality=1.0, id_start=0,
    )  # fmt: skip
    assert len(ev) == 1 and ev[0].level is EvidenceLevel.OBSERVATION
    assert ev[0].start_us == 10_000_000 and 14_900_000 <= ev[0].end_us <= 15_100_000
    assert ev[0].label.startswith("stillness: 5.")
    st = StreamingStillness(
        center_speed=12.0, subject_id="s", extractor_id="x", baseline_quality=1.0,
        id_start=0, frame_period_us=100_000,
    )  # fmt: skip
    live = []
    for i in range(n):
        live += st.update(int(t[i]), 1.0, float(speed[i]))
    assert len(live) == 1 and live[0].start_us == ev[0].start_us
    # a still run that is not over yet is reported by the counter and flushed at the end
    st2 = StreamingStillness(
        center_speed=12.0, subject_id="s", extractor_id="x", baseline_quality=1.0,
        id_start=0, frame_period_us=100_000,
    )  # fmt: skip
    for i in range(40):
        st2.update(i * 100_000, 1.0, 0.5)
    assert st2.active_since_us == 0
    assert len(st2.flush(3_900_000)) == 1


def test_live_speech_pause_events() -> None:
    from lightman.audio.features import RATE
    from lightman.config import AudioConfig, BaselineConfig, LightmanConfig
    from lightman.live.audio_stream import StreamingAudioAnalyzer
    from tests.unit.test_audio_stream import _FakeVAD, _tone

    cfg = LightmanConfig(
        baseline=BaselineConfig(window_s=2.0, min_samples=10, good_samples=30),
        audio=AudioConfig(long_pause_ms=1000),
    )

    class _EnergyVAD(_FakeVAD):
        """Speech probability follows the chunk energy: silence is not speech."""

        class _S:
            def run(self, _out, feeds):
                x = np.asarray(feeds["input"], dtype=np.float32)
                return np.array(
                    [[0.95 if np.abs(x).mean() > 1e-4 else 0.02]], dtype=np.float32
                ), feeds["state"]

        _session = _S()

    an = StreamingAudioAnalyzer(cfg, _EnergyVAD(), subject_id="s")  # type: ignore[arg-type]
    # 4 s tone, 1.6 s silence, 2 s tone
    x = np.concatenate(
        [_tone(150.0, 4.0), np.zeros(int(1.6 * RATE), dtype=np.float32), _tone(150.0, 2.0)]
    )
    chunk = 2048
    events = []
    for i in range(0, x.size - chunk + 1, chunk):
        for r in an.push(x[i : i + chunk], int(i * 1_000_000 / RATE)):
            events += r.new_events
    pauses = [e for e in events if e.event_type == "speech_pause"]
    assert len(pauses) == 1, [e.label for e in events]
    assert pauses[0].source == "audio" and 3_800_000 <= pauses[0].start_us <= 4_200_000
    assert "1.5 s" in pauses[0].label or "1.6 s" in pauses[0].label or "1.7 s" in pauses[0].label


def test_lip_bite_and_microexpression_candidate_tier() -> None:
    n = 40
    aus = [
        "AU1",
        "AU2",
        "AU4",
        "AU5",
        "AU6",
        "AU7",
        "AU9",
        "AU10",
        "AU12",
        "AU15",
        "AU20",
        "AU23",
        "AU24",
        "AU25",
        "AU26",
        "AU32",
    ]
    sig = {f"au.{a}": np.full(n, 0.1) for a in aus}
    sig["au.AU32"][5:9] = 0.9
    sc = pattern_scores(sig, n)
    assert sc["lip bite"][6] >= 0.55 and sc["lip bite"][20] < 0.55
    t = (np.arange(n) * 66_667).astype(np.int64)  # 15 fps
    # fear pattern: sudden onset (peak on the first frame), 4 frames = 267 ms -> candidate
    for a in ("AU1", "AU2", "AU4", "AU5", "AU7", "AU20", "AU26"):
        sig[f"au.{a}"][20:24] = 0.9
    # a slow-onset brief pattern: ramps over 4 frames
    for k, v in enumerate((0.6, 0.7, 0.8, 0.9, 0.9, 0.9)):
        sig["au.AU9"][30 + k] = v
        sig["au.AU15"][30 + k] = v
    ev = detect_expression_patterns(
        t_us=t,
        quality=np.ones(n),
        signals=sig,
        subject_id="s",
        extractor_id="x",
        baseline_quality=1.0,
    )
    fear = next(e for e in ev if "fear" in e.tags)
    assert "fast_onset" in fear.tags and fear.label.startswith("microexpression candidate")
    disgust = next(e for e in ev if "disgust" in e.tags)
    assert "brief" in disgust.tags and "fast_onset" not in disgust.tags
    st = StreamingExpressionDetector(
        subject_id="s", extractor_id="x", baseline_quality=1.0, frame_period_us=66_667
    )
    live = []
    for i in range(n):
        live += st.update(int(t[i]), 1.0, {k: float(v[i]) for k, v in sig.items()})
    live += st.flush(int(t[-1]))
    lf = next(e for e in live if "fear" in e.tags)
    assert "fast_onset" in lf.tags
