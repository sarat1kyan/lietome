"""MediaPipe Pose Landmarker backend (33 body landmarks, image-normalized).

Only the upper body is used: shoulders, elbows, wrists and the hand points (pinky, index,
thumb). Runs in VIDEO mode so the internal tracker carries between frames.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from lightman import __version__
from lightman.schema.provenance import Provenance

EXTRACTOR_ID = "body.mediapipe_pose"
EXTRACTOR_VERSION = "0.1.0"
POSE_MODEL_ID = "mediapipe/pose_landmarker_lite"

L_SHOULDER, R_SHOULDER = 11, 12
L_ELBOW, R_ELBOW = 13, 14
L_WRIST, R_WRIST = 15, 16
HAND_POINTS = (15, 16, 17, 18, 19, 20, 21, 22)


@dataclass(frozen=True, slots=True)
class PoseObservation:
    landmarks: npt.NDArray[np.float32]
    """(33, 4): x, y, z, visibility."""


def default_pose_factory(cfg: Any, registry: Any) -> MediaPipePose | None:
    """Pose backend, or None when body tracking is off or the model cannot be had."""
    from lightman.core.errors import LightmanError

    if not cfg.body.enabled:
        return None
    try:
        path = registry.ensure(cfg.body.model)
        return MediaPipePose(path, model_sha256=registry.get(cfg.body.model).sha256)
    except (LightmanError, OSError, ImportError, RuntimeError, ValueError):
        return None


class MediaPipePose:
    def __init__(self, model_path: Path, *, model_sha256: str | None = None) -> None:
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python import vision as mpv

        self._mp = mp
        options = mpv.PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_path)),
            running_mode=mpv.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._pose = mpv.PoseLandmarker.create_from_options(options)
        self._last_ms = -1
        self.provenance = Provenance(
            extractor_id=EXTRACTOR_ID,
            extractor_version=EXTRACTOR_VERSION,
            model_id=POSE_MODEL_ID,
            model_sha256=model_sha256,
            runtime=f"mediapipe-{mp.__version__}-cpu",
            lightman_version=__version__,
        )

    def process(self, rgb: npt.NDArray[np.uint8], t_us: int) -> PoseObservation | None:
        ms = t_us // 1000
        if ms <= self._last_ms:
            ms = self._last_ms + 1
        self._last_ms = ms
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        res = self._pose.detect_for_video(image, ms)
        if not res.pose_landmarks:
            return None
        lm = res.pose_landmarks[0]
        arr = np.array(
            [(p.x, p.y, p.z, float(getattr(p, "visibility", 1.0) or 0.0)) for p in lm],
            dtype=np.float32,
        )
        return PoseObservation(landmarks=arr)

    def close(self) -> None:
        self._pose.close()
