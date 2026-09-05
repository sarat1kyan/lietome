"""Per-frame face signal-quality heuristic in [0, 1].

Quality gates every downstream statistic: low-quality frames are excluded from baselines
and cannot open events. The heuristic is intentionally simple and documented; it will be
replaced by measured terms (blur, illumination, occlusion) in later phases.

Terms:
* size: face width in pixels relative to a comfortable minimum (120 px -> 1.0)
* pose: frontal-ness; full credit up to 20 deg yaw/pitch, none at 60 deg
"""

from __future__ import annotations

FACE_PX_FULL_CREDIT = 120.0
POSE_FULL_CREDIT_DEG = 20.0
POSE_ZERO_CREDIT_DEG = 60.0


def face_quality(face_width_px: float, yaw_deg: float | None, pitch_deg: float | None) -> float:
    size_term = max(0.0, min(1.0, face_width_px / FACE_PX_FULL_CREDIT))
    pose_term = 1.0
    if yaw_deg is not None and pitch_deg is not None:
        off = max(abs(yaw_deg), abs(pitch_deg))
        if off >= POSE_ZERO_CREDIT_DEG:
            pose_term = 0.0
        elif off > POSE_FULL_CREDIT_DEG:
            pose_term = 1.0 - (off - POSE_FULL_CREDIT_DEG) / (
                POSE_ZERO_CREDIT_DEG - POSE_FULL_CREDIT_DEG
            )
    return size_term * pose_term
