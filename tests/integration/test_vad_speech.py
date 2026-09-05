"""Silero VAD on locally synthesized speech (macOS `say`). Skipped elsewhere or when the
model is not cached. Nothing is committed: the wav is generated per run."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from lightman.audio.features import compute_frame_features, compute_segment_features
from lightman.audio.vad import CHUNK_US, SileroVAD, segments_from_probabilities
from lightman.media.audio import load_audio_mono
from lightman.models import ModelRegistry

pytestmark = pytest.mark.model


def test_vad_and_pitch_on_synthesized_speech(tmp_path: Path) -> None:
    reg = ModelRegistry(allow_download=False)
    if not reg.is_cached("silero/vad_v6"):
        pytest.skip("vad model not cached")
    if shutil.which("say") is None:
        pytest.skip("macOS say not available")
    aiff = tmp_path / "s.aiff"
    subprocess.run(
        ["say", "-o", str(aiff), "One two three four five. Six seven eight nine ten."],
        check=True,
        timeout=60,
    )
    samples, _origin = load_audio_mono(aiff)
    assert samples.size > 16000
    vad = SileroVAD(reg.verify("silero/vad_v6"), model_id="silero/vad_v6")
    probs = vad.probabilities(samples)
    vad.close()
    assert (probs > 0.5).mean() > 0.4
    segs = segments_from_probabilities(probs, origin_us=0)
    assert 1 <= len(segs) <= 3
    ff = compute_frame_features(samples, origin_us=0, speech_probs=probs, chunk_us=CHUNK_US)
    sf = compute_segment_features(ff, segs)
    assert 70 < sf[0].f0_median_hz < 300  # human-like pitch range
    assert np.isfinite(sf[0].jitter_local_approx)
    assert sf[0].syllable_rate_hz > 1.0
