"""Real-model tests. Skipped unless the face_landmarker model is already cached
(run `lightman models download mediapipe/face_landmarker` first). Marked `model`."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from lightman.config import BaselineConfig, LightmanConfig
from lightman.models import ModelRegistry
from lightman.pipeline import analyze_video
from tests.conftest import PORTRAIT, ken_burns_frames

pytestmark = pytest.mark.model


@pytest.fixture(scope="module")
def landmarker():
    reg = ModelRegistry(allow_download=False)
    if not reg.is_cached("mediapipe/face_landmarker"):
        pytest.skip("face_landmarker model not cached")
    from lightman.face.mediapipe_backend import MediaPipeFaceLandmarker

    lm = MediaPipeFaceLandmarker(reg.verify("mediapipe/face_landmarker"))
    yield lm
    lm.close()


def test_detects_face_on_portrait(landmarker) -> None:
    frame = ken_burns_frames(PORTRAIT, 1)[0]
    faces = landmarker.process(frame, 0)
    assert len(faces) == 1
    f = faces[0]
    assert f.landmarks.shape == (478, 3)
    assert len(f.blendshapes) == 52
    assert f.transform is not None and f.transform.shape == (4, 4)
    x0, y0, x1, y1 = f.bbox_normalized()
    assert 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1
    assert all(0.0 <= v <= 1.0 for v in f.blendshapes.values())


def test_no_face_on_noise(landmarker) -> None:
    rng = np.random.default_rng(0)
    frame = rng.integers(0, 255, (240, 320, 3), dtype=np.uint8)
    assert landmarker.process(frame, 1_000_000) == []


def test_full_pipeline_on_portrait_video(
    portrait_video: Path, tmp_path: Path, model_cached: bool
) -> None:
    if not model_cached:
        pytest.skip("face_landmarker model not cached")
    cfg = LightmanConfig(baseline=BaselineConfig(window_s=1.0, min_samples=10, good_samples=30))
    result = analyze_video(portrait_video, tmp_path / "out", cfg)
    q = result.manifest.quality
    assert q.frames_decoded == 90
    assert q.face_coverage > 0.95
    assert q.mean_face_quality is not None and q.mean_face_quality > 0.5
    assert result.summary["inference_ms_per_frame"]["p50"] is not None
