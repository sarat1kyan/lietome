"""Head pose (Tait-Bryan angles + translation) from a 4x4 face transformation matrix.

MediaPipe's matrix maps the canonical face model into camera space. We decompose its
rotation block with the standard *x-y-z* (pitch-yaw-roll) recipe. Angle sign conventions
are documented in docs/architecture.md and verified empirically in tests where possible
(roll is verifiable from synthetic rotations; yaw/pitch signs are checked on real footage
and recorded in project-state).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True, slots=True)
class HeadPose:
    yaw_deg: float
    pitch_deg: float
    roll_deg: float
    tx: float
    ty: float
    tz: float


def head_pose_from_matrix(m: npt.NDArray[np.floating]) -> HeadPose:
    if m.shape != (4, 4):
        raise ValueError(f"expected 4x4 transform, got {m.shape}")
    r = np.asarray(m[:3, :3], dtype=np.float64)
    # Re-orthonormalize defensively: regression outputs are not perfectly orthogonal.
    u, _, vt = np.linalg.svd(r)
    r = u @ vt
    if np.linalg.det(r) < 0:
        u[:, -1] *= -1
        r = u @ vt
    sy = math.hypot(r[0, 0], r[1, 0])
    if sy > 1e-6:
        pitch = math.atan2(r[2, 1], r[2, 2])
        yaw = math.atan2(-r[2, 0], sy)
        roll = math.atan2(r[1, 0], r[0, 0])
    else:  # gimbal lock: yaw ~ +-90 deg
        pitch = math.atan2(-r[1, 2], r[1, 1])
        yaw = math.atan2(-r[2, 0], sy)
        roll = 0.0
    return HeadPose(
        yaw_deg=math.degrees(yaw),
        pitch_deg=math.degrees(pitch),
        roll_deg=math.degrees(roll),
        tx=float(m[0, 3]),
        ty=float(m[1, 3]),
        tz=float(m[2, 3]),
    )


def rotation_matrix(yaw_deg: float, pitch_deg: float, roll_deg: float) -> npt.NDArray[np.float64]:
    """Inverse of :func:`head_pose_from_matrix` for the rotation block (used in tests)."""
    cy, sy = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    cp, sp = math.cos(math.radians(pitch_deg)), math.sin(math.radians(pitch_deg))
    cr, sr = math.cos(math.radians(roll_deg)), math.sin(math.radians(roll_deg))
    rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rz = np.array([[cr, -sr, 0], [sr, cr, 0], [0, 0, 1]])
    out: npt.NDArray[np.float64] = rz @ ry @ rx
    return out
