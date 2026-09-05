"""Eye openness via the Eye Aspect Ratio (EAR; Soukupova & Cech, 2016) on MediaPipe indices.

EAR is a purely geometric, interpretable measure: (vertical distances) / (horizontal width).
It is computed in *pixel* space so image aspect ratio does not bias it, and it is
person-specific enough that blink thresholds should be set relative to the subject's own
baseline rather than a universal constant (see events/blinks.py).
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

# 6-point EAR sets on the 468/478-point MediaPipe mesh: [outer, up1, up2, inner, low2, low1]
# "Right"/"left" are the subject's own right/left eye.
RIGHT_EYE_EAR: tuple[int, ...] = (33, 160, 158, 133, 153, 144)
LEFT_EYE_EAR: tuple[int, ...] = (362, 385, 387, 263, 373, 380)


def _ear(pts: npt.NDArray[np.floating]) -> float:
    p1, p2, p3, p4, p5, p6 = pts
    horiz = float(np.linalg.norm(p1 - p4))
    if horiz <= 1e-9:
        return float("nan")
    vert = float(np.linalg.norm(p2 - p6) + np.linalg.norm(p3 - p5))
    return vert / (2.0 * horiz)


def eye_aspect_ratios(
    landmarks: npt.NDArray[np.floating], width: int, height: int
) -> tuple[float, float]:
    """Return (right_ear, left_ear) using pixel coordinates."""
    if landmarks.shape[0] < 468:
        return float("nan"), float("nan")
    px = landmarks[:, :2] * np.array([width, height], dtype=np.float64)
    return _ear(px[list(RIGHT_EYE_EAR)]), _ear(px[list(LEFT_EYE_EAR)])
