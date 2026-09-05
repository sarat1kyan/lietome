import numpy as np
import pytest

from lightman.face.opengraphau_onnx import CROP_SIZE, preprocess_face, select_providers
from lightman.features.action_units import OPENGRAPHAU_NAMES, au_description


def test_names_and_descriptions() -> None:
    assert len(OPENGRAPHAU_NAMES) == 41
    assert len(set(OPENGRAPHAU_NAMES)) == 41
    assert au_description("AU12") == "lip corner puller"
    assert au_description("AUL4") == "left brow lowerer"
    assert au_description("AUR14") == "right dimpler"
    assert au_description("AU99") is None


def test_preprocess_shape_and_normalization() -> None:
    rgb = np.full((480, 640, 3), 255, dtype=np.uint8)
    x = preprocess_face(rgb, (200.0, 100.0, 400.0, 340.0))
    assert x.shape == (1, 3, CROP_SIZE, CROP_SIZE) and x.dtype == np.float32
    # white pixels -> (1 - mean) / std per channel
    expect = (1.0 - np.array([0.485, 0.456, 0.406])) / np.array([0.229, 0.224, 0.225])
    assert np.allclose(x[0, :, 112, 112], expect, atol=1e-5)


def test_preprocess_pads_when_box_leaves_frame() -> None:
    rgb = np.full((100, 100, 3), 200, dtype=np.uint8)
    x = preprocess_face(rgb, (60.0, 60.0, 100.0, 100.0))  # margin pushes crop past the edge
    assert np.isfinite(x).all()
    # bottom-right of the crop is padding (black) -> normalized value of 0
    corner = x[0, :, -1, -1]
    assert np.allclose(
        corner, (0 - np.array([0.485, 0.456, 0.406])) / np.array([0.229, 0.224, 0.225]), atol=1e-5
    )


def test_preprocess_rejects_tiny_box() -> None:
    with pytest.raises(ValueError, match="too small"):
        preprocess_face(np.zeros((10, 10, 3), dtype=np.uint8), (5.0, 5.0, 5.5, 5.5))


def test_providers_always_end_with_cpu() -> None:
    assert select_providers(prefer_gpu=False) == ["CPUExecutionProvider"]
    assert select_providers(prefer_gpu=True)[-1] == "CPUExecutionProvider"
