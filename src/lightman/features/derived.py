"""Derived per-frame signals from a face observation.

* gaze proxy: MediaPipe iris-related blendshapes (eyeLookIn/Out/Up/Down) combined into a
  horizontal and a vertical coefficient in [-1, 1]. Positive horizontal = gaze toward the
  subject's left; positive vertical = up. A proxy, not a calibrated gaze estimate.
* asymmetry: left minus right for brow lowering and smile; unilateral expressions and camera
  angle both show up here, so it is only meaningful as a change from baseline.
* head speed: angular speed of the head pose in deg/s from consecutive frames.
* frame quality terms: blur (variance of the Laplacian on the face crop) and mean luminance.
"""

from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt


def gaze_from_blendshapes(bs: dict[str, float]) -> tuple[float, float]:
    g = bs.get
    horizontal = 0.5 * (
        (g("eyeLookOutLeft", 0.0) - g("eyeLookInLeft", 0.0))
        + (g("eyeLookInRight", 0.0) - g("eyeLookOutRight", 0.0))
    )
    vertical = 0.5 * (
        (g("eyeLookUpLeft", 0.0) + g("eyeLookUpRight", 0.0))
        - (g("eyeLookDownLeft", 0.0) + g("eyeLookDownRight", 0.0))
    )
    return float(horizontal), float(vertical)


def asymmetry_from_blendshapes(bs: dict[str, float]) -> tuple[float, float]:
    g = bs.get
    brow = g("browDownLeft", 0.0) - g("browDownRight", 0.0)
    smile = g("mouthSmileLeft", 0.0) - g("mouthSmileRight", 0.0)
    return float(brow), float(smile)


def head_speed_deg_s(
    prev: tuple[float, float, float] | None, cur: tuple[float, float, float], dt_us: int
) -> float:
    if prev is None or dt_us <= 0:
        return math.nan
    d = math.sqrt(sum((c - p) ** 2 for c, p in zip(cur, prev, strict=True)))
    return d / (dt_us / 1e6)


def frame_quality_terms(
    rgb: npt.NDArray[np.uint8], bbox_px: tuple[float, float, float, float]
) -> tuple[float, float]:
    """(blur, luma) on the face crop: blur = variance of the Laplacian of a 128 px grayscale
    crop (higher is sharper), luma = mean gray level 0-255."""
    import cv2

    h, w = rgb.shape[:2]
    x0, y0, x1, y1 = (int(max(0, bbox_px[0])), int(max(0, bbox_px[1])),
                      int(min(w, bbox_px[2])), int(min(h, bbox_px[3])))  # fmt: skip
    if x1 - x0 < 8 or y1 - y0 < 8:
        return math.nan, math.nan
    crop = rgb[y0:y1, x0:x1]
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    scale = 128.0 / max(gray.shape)
    if scale < 1:
        size = (max(1, int(gray.shape[1] * scale)), max(1, int(gray.shape[0] * scale)))
        gray = cv2.resize(gray, size)
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    return float(lap.var()), float(gray.mean())


BLUR_FULL_CREDIT = 60.0  # Laplacian variance at which sharpness no longer limits quality
BLUR_ZERO_CREDIT = 5.0
LUMA_LOW_FULL = 60.0  # mean gray below which the face is too dark for reliable landmarks
LUMA_LOW_ZERO = 15.0
LUMA_HIGH_FULL = 215.0
LUMA_HIGH_ZERO = 250.0


def image_quality_factor(blur: float, luma: float) -> float:
    """Multiplier in [0, 1] from sharpness and exposure; NaN inputs give 1 (unknown, not bad)."""
    f = 1.0
    if math.isfinite(blur):
        if blur <= BLUR_ZERO_CREDIT:
            f *= 0.0
        elif blur < BLUR_FULL_CREDIT:
            f *= (blur - BLUR_ZERO_CREDIT) / (BLUR_FULL_CREDIT - BLUR_ZERO_CREDIT)
    if math.isfinite(luma):
        if luma <= LUMA_LOW_ZERO or luma >= LUMA_HIGH_ZERO:
            f *= 0.0
        elif luma < LUMA_LOW_FULL:
            f *= (luma - LUMA_LOW_ZERO) / (LUMA_LOW_FULL - LUMA_LOW_ZERO)
        elif luma > LUMA_HIGH_FULL:
            f *= (LUMA_HIGH_ZERO - luma) / (LUMA_HIGH_ZERO - LUMA_HIGH_FULL)
    return max(0.0, min(1.0, f))
