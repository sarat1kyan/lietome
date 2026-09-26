"""Per-frame upper-body features, normalized by the face so they do not depend on distance.

* body.shoulder_y: mean shoulder height below the face center, in face heights. A shrug makes
  it smaller.
* body.shoulder_tilt_deg: shoulder line angle.
* body.hand_speed: fastest visible wrist, in face widths per second (the illustrator proxy:
  hand gestures that accompany speech, d = -0.14 for liars in DePaulo et al. 2003).
* body.hand_face: distance from the nearest visible hand point to the face box, in face widths
  (0 inside the box). Self-touch episodes come from it.
* body.visible: minimum shoulder visibility.
"""

from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt

from lightman.body.pose import HAND_POINTS, L_SHOULDER, L_WRIST, R_SHOULDER, R_WRIST

BODY_COLUMNS: tuple[str, ...] = (
    "body.shoulder_y",
    "body.shoulder_tilt_deg",
    "body.hand_speed",
    "body.hand_face",
    "body.visible",
)
VIS_MIN = 0.5


class BodyFeatures:
    """Stateful: hand speed needs the previous frame."""

    def __init__(self) -> None:
        self._prev: dict[int, tuple[float, float]] = {}
        self._prev_t: int | None = None

    def compute(
        self,
        lm: npt.NDArray[np.floating] | None,
        face_bbox: tuple[float, float, float, float] | None,
        t_us: int,
        aspect: float,
    ) -> dict[str, float]:
        """``aspect`` = width / height of the frame (landmarks are normalized per axis)."""
        nan = math.nan
        out = dict.fromkeys(BODY_COLUMNS, nan)
        if lm is None or face_bbox is None:
            self._prev.clear()
            self._prev_t = None
            return out
        x0, y0, x1, y1 = face_bbox
        fw = max(1e-6, (x1 - x0) * aspect)  # face width in height-normalized units
        fh = max(1e-6, y1 - y0)
        fcx, fcy = (x0 + x1) / 2, (y0 + y1) / 2
        ls, rs = lm[L_SHOULDER], lm[R_SHOULDER]
        vis = float(min(ls[3], rs[3]))
        out["body.visible"] = vis
        if vis >= VIS_MIN:
            out["body.shoulder_y"] = float(((ls[1] + rs[1]) / 2 - fcy) / fh)
            dx = (rs[0] - ls[0]) * aspect
            dy = rs[1] - ls[1]
            ang = math.degrees(math.atan2(dy, dx))
            if ang > 90:
                ang -= 180
            elif ang < -90:
                ang += 180
            out["body.shoulder_tilt_deg"] = float(ang)
        # hand speed
        dt = (t_us - self._prev_t) / 1e6 if self._prev_t is not None else 0.0
        speeds = []
        cur: dict[int, tuple[float, float]] = {}
        for idx in (L_WRIST, R_WRIST):
            if lm[idx][3] < VIS_MIN:
                continue
            p = (float(lm[idx][0]) * aspect, float(lm[idx][1]))
            cur[idx] = p
            q = self._prev.get(idx)
            if q is not None and dt > 0:
                speeds.append(math.hypot(p[0] - q[0], p[1] - q[1]) / fw / dt)
        self._prev, self._prev_t = cur, t_us
        if speeds:
            out["body.hand_speed"] = float(max(speeds))
        # hand to face
        dists = []
        for idx in HAND_POINTS:
            if lm[idx][3] < VIS_MIN:
                continue
            px, py = float(lm[idx][0]), float(lm[idx][1])
            ddx = max(x0 - px, 0.0, px - x1) * aspect
            ddy = max(y0 - py, 0.0, py - y1)
            dists.append(math.hypot(ddx, ddy) / fw)
        if dists:
            out["body.hand_face"] = float(min(dists))
        del fcx
        return out


def body_points(lm: npt.NDArray[np.floating] | None) -> dict[str, list[list[float]]] | None:
    """Shoulder, elbow and wrist points for the HUD (visible ones only)."""
    if lm is None:
        return None
    pts: dict[str, list[list[float]]] = {}
    for name, idxs in (("shoulders", (11, 12)), ("elbows", (13, 14)), ("wrists", (15, 16))):
        pts[name] = [
            [round(float(lm[i][0]), 4), round(float(lm[i][1]), 4)]
            for i in idxs
            if lm[i][3] >= VIS_MIN
        ]
    return pts
