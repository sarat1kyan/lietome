import itertools

import numpy as np
import pytest

from lightman.core.errors import UnsupportedMediaError
from lightman.media.audio import TARGET_RATE, iter_audio_blocks, load_audio_mono


def test_load_audio_resamples_to_16k_mono(noise_video_with_audio) -> None:
    x, origin = load_audio_mono(noise_video_with_audio)
    assert x.dtype == np.float32 and x.ndim == 1
    assert abs(x.size / TARGET_RATE - 1.0) < 0.1  # 30 frames @ 30 fps = 1 s of audio
    assert origin == 0
    assert np.abs(x).max() <= 1.0


def test_blocks_are_time_ordered(noise_video_with_audio) -> None:
    blocks = list(iter_audio_blocks(noise_video_with_audio))
    assert blocks and all(b.rate == TARGET_RATE for b in blocks)
    ts = [b.container_t_us for b in blocks]
    assert all(b >= a for a, b in itertools.pairwise(ts))


def test_video_without_audio_raises(noise_video) -> None:
    with pytest.raises(UnsupportedMediaError):
        list(iter_audio_blocks(noise_video))
