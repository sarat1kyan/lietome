import math

import numpy as np
import pytest

from lightman.features.eyes import LEFT_EYE_EAR, RIGHT_EYE_EAR, eye_aspect_ratios


def _landmarks_with_eye(indices: tuple[int, ...], openness: float) -> np.ndarray:
    lm = np.zeros((478, 3), dtype=np.float32)
    outer, up1, up2, inner, low2, low1 = indices
    lm[outer] = (0.30, 0.50, 0)
    lm[inner] = (0.40, 0.50, 0)
    lm[up1] = (0.33, 0.50 - openness / 2, 0)
    lm[up2] = (0.37, 0.50 - openness / 2, 0)
    lm[low1] = (0.33, 0.50 + openness / 2, 0)
    lm[low2] = (0.37, 0.50 + openness / 2, 0)
    return lm


def test_ear_open_vs_closed() -> None:
    lm = _landmarks_with_eye(RIGHT_EYE_EAR, 0.03)
    for i, v in zip(
        LEFT_EYE_EAR, _landmarks_with_eye(LEFT_EYE_EAR, 0.0)[list(LEFT_EYE_EAR)], strict=True
    ):
        lm[i] = v
    r, left = eye_aspect_ratios(lm, 100, 100)
    # width 10px, two vertical gaps of 3px each -> (3+3)/(2*10) = 0.3
    assert r == pytest.approx(0.3, abs=1e-5)
    assert left == 0.0


def test_pixel_space_not_normalized_space() -> None:
    lm = _landmarks_with_eye(RIGHT_EYE_EAR, 0.03)
    r_square, _ = eye_aspect_ratios(lm, 100, 100)
    r_wide, _ = eye_aspect_ratios(lm, 200, 100)  # same normalized coords, wider image
    assert r_wide == r_square / 2


def test_too_few_landmarks_gives_nan() -> None:
    r, left = eye_aspect_ratios(np.zeros((68, 3)), 100, 100)
    assert math.isnan(r) and math.isnan(left)
