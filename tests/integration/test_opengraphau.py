"""Real OpenGraphAU ONNX model. Skipped unless cached (lightman models download ...)."""

from __future__ import annotations

import numpy as np
import pytest

from lightman.models import ModelRegistry
from tests.conftest import PORTRAIT, ken_burns_frames

pytestmark = pytest.mark.model


@pytest.mark.parametrize(
    ("model_id", "au25_min"),
    [("opengraphau/resnet50_s2", 0.5), ("opengraphau/resnet18_s2", 0.3)],
)
def test_smile_portrait_activates_au12_au25(model_id: str, au25_min: float) -> None:
    reg = ModelRegistry(allow_download=False)
    if not reg.is_cached(model_id) or not reg.is_cached("mediapipe/face_landmarker"):
        pytest.skip("models not cached")
    from lightman.face.mediapipe_backend import MediaPipeFaceLandmarker
    from lightman.face.opengraphau_onnx import OpenGraphAUOnnx

    frame = ken_burns_frames(PORTRAIT, 1)[0]
    h, w = frame.shape[:2]
    lm = MediaPipeFaceLandmarker(reg.verify("mediapipe/face_landmarker"))
    face = lm.process(frame, 0)[0]
    lm.close()
    x0, y0, x1, y1 = face.bbox_normalized()
    det = OpenGraphAUOnnx(reg.verify(model_id), model_id=model_id, prefer_gpu=False)
    probs = det.process(frame, (x0 * w, y0 * h, x1 * w, y1 * h))
    det.close()
    au = dict(zip(det.au_names, probs.tolist(), strict=True))
    assert probs.shape == (41,) and np.all((probs >= 0) & (probs <= 1))
    # The fixture is a broad smile with parted lips: lip corner puller and lips part must fire.
    assert au["AU12"] > 0.5, au
    assert au["AU25"] > au25_min, au  # resnet18 is less confident on the 360p fixture
    assert au["AU15"] < 0.3, au  # lip corner depressor absent
