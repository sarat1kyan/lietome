import numpy as np
import pytest

from lightman.audio.features import RATE
from lightman.config import BaselineConfig, LightmanConfig
from lightman.live.audio_stream import StreamingAudioAnalyzer, _yin_f0


def _tone(f0: float, seconds: float, amp: float = 0.3, phase: float = 0.0) -> np.ndarray:
    t = np.arange(int(RATE * seconds)) / RATE
    return (amp * np.sin(2 * np.pi * f0 * t + phase)).astype(np.float32)


def test_yin_single_window_recovers_pitch_and_flags_noise() -> None:
    win = _tone(140.0, 1024 / RATE)
    f0, periodic = _yin_f0(win, 60.0, 400.0)
    assert periodic and f0 == pytest.approx(140.0, abs=1.5)
    noise = np.random.default_rng(0).normal(0, 0.1, 1024).astype(np.float32)
    _, periodic_noise = _yin_f0(noise, 60.0, 400.0)
    assert not periodic_noise


class _FakeVAD:
    """Always speech: exercises the analyzer without the ONNX model."""

    class _S:
        def run(self, _out, feeds):
            return np.array([[0.95]], dtype=np.float32), feeds["state"]

    _session = _S()

    class _P:
        extractor_id = "audio.fake"

    provenance = _P()


def test_streaming_audio_emits_hops_and_detects_pitch_jump() -> None:
    cfg = LightmanConfig(baseline=BaselineConfig(window_s=2.0, min_samples=10, good_samples=30))
    an = StreamingAudioAnalyzer(cfg, _FakeVAD(), subject_id="s")  # type: ignore[arg-type]
    results = []
    # 3 s at 150 Hz, then 2 s at 260 Hz (a large, sustained pitch rise)
    x = np.concatenate([_tone(150.0, 3.0), _tone(260.0, 2.0)])
    chunk = 2048
    for i in range(0, x.size - chunk + 1, chunk):
        results += an.push(x[i : i + chunk], int(i * 1_000_000 / RATE))
    assert len(results) > 200
    f0s = np.array([r.f0_hz for r in results[10:100]], dtype=float)
    assert np.nanmedian(f0s) == pytest.approx(150.0, abs=2.0)
    assert any(r.baseline_ready for r in results)
    events = [e for r in results for e in r.new_events] + an.finish()
    labels = [e.label for e in events]
    assert any("pitch" in lab and "increase" in lab for lab in labels), labels
    assert all(e.source == "audio" for e in events)
    assert all(e.start_us >= 3_000_000 - 200_000 for e in events)
