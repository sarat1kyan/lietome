"""Media ingestion tests against synthetic PyAV-generated files (hostile-input focus)."""

from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np
import pytest

from lightman.core.errors import MediaError, SecurityLimitError, UnsupportedMediaError
from lightman.media import MediaLimits, check_file_limits, iter_video_frames, probe_media
from tests.conftest import noise_frames, write_video


def test_probe_basic(noise_video: Path) -> None:
    info = probe_media(noise_video)
    assert info.has_video and not info.has_audio
    v = info.video_streams[0]
    assert (v.width, v.height) == (96, 64)
    assert v.average_fps == pytest.approx(30.0)
    assert info.container_format.startswith("mov")
    assert len(info.sha256) == 64
    assert info.path_name == "noise.mp4"


def test_probe_with_audio(noise_video_with_audio: Path) -> None:
    info = probe_media(noise_video_with_audio)
    assert info.has_audio
    a = info.audio_streams[0]
    assert a.sample_rate == 48000 and a.channels == 1


def test_zero_length_file_rejected(tmp_path: Path) -> None:
    p = tmp_path / "empty.mp4"
    p.write_bytes(b"")
    with pytest.raises(SecurityLimitError, match="empty"):
        probe_media(p)


def test_missing_file_rejected(tmp_path: Path) -> None:
    with pytest.raises(SecurityLimitError, match="does not exist"):
        probe_media(tmp_path / "nope.mp4")


def test_directory_rejected(tmp_path: Path) -> None:
    with pytest.raises(SecurityLimitError, match="regular file"):
        check_file_limits(tmp_path, MediaLimits())


def test_corrupt_file_rejected(tmp_path: Path) -> None:
    p = tmp_path / "garbage.mp4"
    p.write_bytes(np.random.default_rng(0).bytes(4096))
    with pytest.raises(MediaError):
        probe_media(p)


def test_truncated_file_decodes_partially_or_errors(noise_video: Path, tmp_path: Path) -> None:
    data = noise_video.read_bytes()
    p = tmp_path / "trunc.mp4"
    p.write_bytes(data[: len(data) // 3])
    # Either the demuxer refuses or we get a MediaError mid-stream; never a crash/hang.
    try:
        frames = list(iter_video_frames(p))
    except MediaError:
        return
    assert len(frames) < 30


def test_file_size_limit(noise_video: Path) -> None:
    with pytest.raises(SecurityLimitError, match="above limit"):
        probe_media(noise_video, MediaLimits(max_file_bytes=10))


def test_resolution_limit_rejected_before_decode(noise_video: Path) -> None:
    with pytest.raises(SecurityLimitError, match="max pixels"):
        probe_media(noise_video, MediaLimits(max_pixels_per_frame=1000))


def test_duration_limit(noise_video: Path) -> None:
    with pytest.raises(SecurityLimitError, match="duration"):
        probe_media(noise_video, MediaLimits(max_duration_us=100))


def test_frame_cap_enforced(noise_video: Path) -> None:
    with pytest.raises(SecurityLimitError, match="frame count"):
        list(iter_video_frames(noise_video, limits=MediaLimits(max_frames=5)))


def test_max_frames_soft_stop(noise_video: Path) -> None:
    frames = list(iter_video_frames(noise_video, max_frames=5))
    assert len(frames) == 5


def test_decode_timestamps_monotonic_and_exact(noise_video: Path) -> None:
    frames = list(iter_video_frames(noise_video))
    assert len(frames) == 30
    ts = [f.t_us for f in frames]
    assert ts[0] == 0
    assert all(b > a for a, b in itertools.pairwise(ts))
    assert ts[1] == 33_333  # 1/30 s in us, exact from PTS
    assert frames[0].rgb.shape == (64, 96, 3) and frames[0].rgb.dtype == np.uint8
    assert not frames[0].timestamp_estimated


def test_time_based_subsampling(noise_video: Path) -> None:
    frames = list(iter_video_frames(noise_video, target_fps=10))
    assert 9 <= len(frames) <= 11
    gaps = np.diff([f.t_us for f in frames])
    assert gaps.min() >= 99_000


def test_variable_frame_rate_uses_pts(tmp_path: Path) -> None:
    # Frame i shown at irregular times: 0, 1, 2, 6, 7, 20 (in 1/30 s units)
    pts = [0, 1, 2, 6, 7, 20]
    p = write_video(tmp_path / "vfr.mp4", noise_frames(len(pts)), fps=30, pts_list=pts)
    frames = list(iter_video_frames(p))
    got = [f.t_us for f in frames]
    expect = [int(x * 1_000_000 / 30) for x in pts]
    assert got == expect


def test_rotation_metadata_applied(tmp_path: Path) -> None:
    p = write_video(tmp_path / "rot.mp4", noise_frames(5, w=96, h=64), fps=30, rotation=90)
    info = probe_media(p)
    frames = list(iter_video_frames(p))
    assert frames[0].rotation_deg in (90, -90, 270)
    assert frames[0].rgb.shape[:2] == (96, 64)  # portrait after rotation
    assert info.video_streams[0].display_size in ((64, 96), (96, 64))


def test_audio_only_file_unsupported(tmp_path: Path) -> None:
    import av

    p = tmp_path / "audio.m4a"
    with av.open(str(p), "w") as c:
        s = c.add_stream("aac", rate=48000)
        s.layout = "mono"  # type: ignore[assignment]
        samples = np.zeros((1, 48000), dtype=np.float32)
        fr = av.AudioFrame.from_ndarray(samples, format="fltp", layout="mono")
        fr.sample_rate = 48000
        fr.pts = 0
        for pk in s.encode(fr):
            c.mux(pk)
        for pk in s.encode():
            c.mux(pk)
    info = probe_media(p)
    assert info.has_audio and not info.has_video
    with pytest.raises(UnsupportedMediaError):
        list(iter_video_frames(p))
