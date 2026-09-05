"""MediaPipe Face Landmarker adapter (Apache-2.0 model bundle).

Runs the Tasks API in VIDEO mode so the internal tracker is used between frames. Timestamps
must be monotonically increasing in milliseconds; we convert from microseconds and guard
against duplicates caused by rounding.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import numpy.typing as npt

from lightman import __version__
from lightman.core.logging import get_logger
from lightman.face.base import FaceObservation
from lightman.features.blendshapes import BLENDSHAPE_NAMES
from lightman.schema.provenance import Provenance

log = get_logger(__name__)

EXTRACTOR_ID = "face.mediapipe_landmarker"
EXTRACTOR_VERSION = "0.1.0"


class MediaPipeFaceLandmarker:
    def __init__(
        self,
        model_path: Path,
        *,
        model_sha256: str | None = None,
        max_faces: int = 1,
        min_face_detection_confidence: float = 0.5,
        min_face_presence_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ) -> None:
        # Imported lazily so that the rest of Lightman stays importable without MediaPipe.
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python import vision as mpv

        self._mp = mp
        options = mpv.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_path)),
            running_mode=mpv.RunningMode.VIDEO,
            num_faces=max_faces,
            min_face_detection_confidence=min_face_detection_confidence,
            min_face_presence_confidence=min_face_presence_confidence,
            min_tracking_confidence=min_tracking_confidence,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
        )
        self._landmarker = mpv.FaceLandmarker.create_from_options(options)
        self._last_ms = -1
        self._provenance = Provenance(
            extractor_id=EXTRACTOR_ID,
            extractor_version=EXTRACTOR_VERSION,
            model_id="mediapipe/face_landmarker",
            model_sha256=model_sha256,
            runtime=f"mediapipe-{mp.__version__}-cpu",
            lightman_version=__version__,
        )
        log.info("face_landmarker_loaded", backend=EXTRACTOR_ID, mediapipe=mp.__version__)

    @property
    def provenance(self) -> Provenance:
        return self._provenance

    @property
    def blendshape_names(self) -> list[str]:
        return list(BLENDSHAPE_NAMES)

    def process(self, rgb: npt.NDArray[np.uint8], t_us: int) -> list[FaceObservation]:
        if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
            raise ValueError("expected HxWx3 uint8 RGB frame")
        ms = t_us // 1000
        if ms <= self._last_ms:  # MediaPipe requires strictly increasing timestamps
            ms = self._last_ms + 1
        self._last_ms = ms
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(image, ms)
        observations: list[FaceObservation] = []
        n = len(result.face_landmarks)
        for i in range(n):
            lm = result.face_landmarks[i]
            arr = np.array([(p.x, p.y, p.z) for p in lm], dtype=np.float32)
            shapes: dict[str, float] = {}
            if result.face_blendshapes:
                shapes = {c.category_name: float(c.score) for c in result.face_blendshapes[i]}
            transform = None
            if result.facial_transformation_matrixes:
                transform = np.asarray(
                    result.facial_transformation_matrixes[i], dtype=np.float32
                ).reshape(4, 4)
            observations.append(
                FaceObservation(landmarks=arr, blendshapes=shapes, transform=transform, track_id=i)
            )
        return observations

    def close(self) -> None:
        self._landmarker.close()
