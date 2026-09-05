import numpy as np
import pytest

from lightman.audio.features import (
    HOP,
    RATE,
    audio_quality,
    compute_frame_features,
    compute_segment_features,
    hz_to_semitones,
    rms_db,
    syllable_nuclei_count,
)
from lightman.audio.vad import CHUNK, CHUNK_US, SpeechSegment, segments_from_probabilities


def _tone(f0: float, seconds: float, amp: float = 0.3) -> np.ndarray:
    t = np.arange(int(RATE * seconds)) / RATE
    return (amp * np.sin(2 * np.pi * f0 * t)).astype(np.float32)


def test_rms_db_of_known_amplitude() -> None:
    x = _tone(200.0, 1.0, amp=0.5)  # RMS = 0.5/sqrt(2) -> -9.03 dB
    e = rms_db(x)
    assert e.size == 1 + (x.size - 1) // HOP
    assert np.median(e[5:-5]) == pytest.approx(-9.03, abs=0.2)
    assert rms_db(np.zeros(RATE, dtype=np.float32)).max() == -80.0


def test_segments_from_probabilities_merges_and_filters() -> None:
    probs = np.zeros(200)
    probs[10:40] = 0.9  # 30 chunks = 960 ms
    probs[43:60] = 0.9  # gap 3 chunks = 96 ms -> merged
    probs[100:103] = 0.9  # 96 ms -> below min_speech, dropped
    segs = segments_from_probabilities(
        probs, origin_us=0, min_speech_ms=250, min_silence_ms=300, pad_ms=0
    )
    assert len(segs) == 1
    assert segs[0].start_us == 10 * CHUNK_US and segs[0].end_us == 60 * CHUNK_US
    assert segs[0].mean_prob == pytest.approx(0.9 * 47 / 50, abs=0.02)


def test_frame_features_recover_f0_and_align_speech_prob() -> None:
    x = _tone(150.0, 2.0)
    probs = np.ones(x.size // CHUNK) * 0.9
    ff = compute_frame_features(x, origin_us=5_000_000, speech_probs=probs, chunk_us=CHUNK_US)
    assert ff.t_us[0] == 5_000_000
    assert np.diff(ff.t_us).min() == HOP * 1_000_000 // RATE
    f0 = ff.f0_hz[10:-10]
    assert np.nanmedian(f0) == pytest.approx(150.0, abs=1.5)
    assert ff.speech_prob.min() == pytest.approx(0.9)


def test_semitones_and_segment_stats() -> None:
    assert hz_to_semitones(np.array([200.0]), 100.0)[0] == pytest.approx(12.0)
    x = np.concatenate([_tone(120.0, 1.0), np.zeros(RATE // 2, np.float32), _tone(180.0, 1.0)])
    probs = np.zeros(x.size // CHUNK)
    probs[: RATE // CHUNK] = 0.9
    probs[(RATE + RATE // 2) // CHUNK :] = 0.9
    ff = compute_frame_features(x, origin_us=0, speech_probs=probs, chunk_us=CHUNK_US)
    segs = segments_from_probabilities(probs, origin_us=0, pad_ms=0)
    assert len(segs) == 2
    sf = compute_segment_features(ff, segs)
    assert sf[0].pause_before_ms is None
    assert sf[1].pause_before_ms == pytest.approx(500, abs=70)
    assert sf[0].f0_median_hz == pytest.approx(120, abs=2) and sf[1].f0_median_hz == pytest.approx(
        180, abs=2
    )
    assert sf[0].jitter_local_approx < 0.01  # steady tone
    assert sf[0].voiced_fraction > 0.8


def test_syllable_nuclei_count_on_amplitude_modulated_tone() -> None:
    # 4 Hz amplitude modulation over 2 s -> ~8 energy peaks
    t = np.arange(RATE * 2) / RATE
    x = (0.3 * (0.55 + 0.45 * np.sin(2 * np.pi * 4 * t)) * np.sin(2 * np.pi * 140 * t)).astype(
        np.float32
    )
    n = syllable_nuclei_count(rms_db(x))
    assert 6 <= n <= 9


def test_audio_quality_snr_and_clipping() -> None:
    rng = np.random.default_rng(0)
    n_speech_chunks = 32
    t = np.arange(n_speech_chunks * CHUNK) / RATE
    speech = (0.5 * np.sin(2 * np.pi * 150 * t)).astype(np.float32)  # power 0.125
    noise = rng.normal(0, 0.005, n_speech_chunks * CHUNK).astype(np.float32)  # power 2.5e-5
    x = np.concatenate([speech, noise])
    probs = (np.arange(2 * n_speech_chunks) < n_speech_chunks).astype(float)
    q = audio_quality(x, probs, CHUNK)
    assert q["snr_db"] == pytest.approx(37.0, abs=1.0)
    assert q["clipping_fraction"] == 0.0
    assert q["speech_fraction"] == pytest.approx(0.5)
    clipped = np.ones(RATE, np.float32)
    assert audio_quality(clipped, np.ones(RATE // CHUNK), CHUNK)["clipping_fraction"] == 1.0


def test_segment_features_handle_unvoiced_segment() -> None:
    seg = SpeechSegment(start_us=0, end_us=500_000, mean_prob=0.8)
    x = np.random.default_rng(1).normal(0, 0.05, RATE).astype(np.float32)
    ff = compute_frame_features(
        x, origin_us=0, speech_probs=np.ones(x.size // CHUNK), chunk_us=CHUNK_US
    )
    sf = compute_segment_features(ff, [seg])[0]
    assert sf.duration_ms == 500
    assert np.isfinite(sf.energy_mean_db)
