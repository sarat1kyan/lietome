"""Shared fixtures. Synthetic media is generated with PyAV so tests need no external files
other than the small Apache-2.0 portrait image shipped in tests/fixtures."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import av
import numpy as np
import pytest

FIXTURES = Path(__file__).parent / "fixtures"
PORTRAIT = FIXTURES / "portrait_mediapipe_apache2.jpg"


def write_video(
    path: Path,
    frames: list[np.ndarray],
    *,
    fps: int = 30,
    codec: str = "libx264",
    pix_fmt: str = "yuv420p",
    with_audio: bool = False,
    rotation: int = 0,
    pts_list: list[int] | None = None,
) -> Path:
    """Encode uint8 RGB frames to ``path``. ``pts_list`` (in 1/fps units) makes VFR videos."""
    h, w = frames[0].shape[:2]
    with av.open(str(path), mode="w") as container:
        vs = container.add_stream(codec, rate=fps)
        vs.width, vs.height, vs.pix_fmt = w, h, pix_fmt
        vs.time_base = Fraction(1, fps)
        if rotation:
            vs.set_display_rotation(rotation)  # type: ignore[attr-defined]
        astream = None
        if with_audio:
            astream = container.add_stream("aac", rate=48000)
            astream.layout = "mono"  # type: ignore[assignment]
        for i, rgb in enumerate(frames):
            frame = av.VideoFrame.from_ndarray(rgb, format="rgb24")
            frame.pts = pts_list[i] if pts_list else i
            frame.time_base = Fraction(1, fps)
            for packet in vs.encode(frame):
                container.mux(packet)
        for packet in vs.encode():
            container.mux(packet)
        if astream is not None:
            n_samples = int(48000 * len(frames) / fps)
            samples = (0.05 * np.sin(np.arange(n_samples) * 2 * np.pi * 220 / 48000)).astype(
                np.float32
            )
            aframe = av.AudioFrame.from_ndarray(
                samples.reshape(1, -1), format="fltp", layout="mono"
            )
            aframe.sample_rate = 48000
            aframe.pts = 0
            for packet in astream.encode(aframe):
                container.mux(packet)
            for packet in astream.encode():
                container.mux(packet)
    return path


def noise_frames(n: int, w: int = 96, h: int = 64, seed: int = 0) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    return [rng.integers(0, 255, (h, w, 3), dtype=np.uint8) for _ in range(n)]


def ken_burns_frames(
    image_path: Path, n: int, out_w: int = 480, out_h: int = 360
) -> list[np.ndarray]:
    """Slow pan/zoom over a portrait so the face moves a little frame to frame."""
    import cv2

    img = cv2.cvtColor(cv2.imread(str(image_path)), cv2.COLOR_BGR2RGB)
    ih, iw = img.shape[:2]
    frames = []
    for i in range(n):
        f = i / max(1, n - 1)
        zoom = 1.0 + 0.15 * f
        cw, ch = int(iw / zoom), int(ih / zoom)
        x0 = int((iw - cw) * (0.5 + 0.3 * np.sin(2 * np.pi * f)) / 1.0 * 0.5)
        y0 = int((ih - ch) * 0.3)
        crop = img[y0 : y0 + ch, x0 : x0 + cw]
        frames.append(cv2.resize(crop, (out_w, out_h), interpolation=cv2.INTER_AREA))
    return frames


@pytest.fixture(scope="session")
def noise_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    d = tmp_path_factory.mktemp("media")
    return write_video(d / "noise.mp4", noise_frames(30), fps=30)


@pytest.fixture(scope="session")
def noise_video_with_audio(tmp_path_factory: pytest.TempPathFactory) -> Path:
    d = tmp_path_factory.mktemp("media")
    return write_video(d / "noise_audio.mp4", noise_frames(30), fps=30, with_audio=True)


@pytest.fixture(scope="session")
def portrait_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    d = tmp_path_factory.mktemp("media")
    return write_video(d / "portrait.mp4", ken_burns_frames(PORTRAIT, 90), fps=30)


@pytest.fixture(scope="session")
def model_cached() -> bool:
    from lightman.models import ModelRegistry

    return ModelRegistry(allow_download=False).is_cached("mediapipe/face_landmarker")


requires_model = pytest.mark.model
