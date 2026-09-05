"""OpenGraphAU (MEFL stage-2) Action Unit detector via ONNX Runtime.

Model: Luo et al., "Learning Multi-dimensional Edge Feature-based AU Relation Graph for
Facial Action Unit Recognition" (IJCAI 2022); OpenGraphAU release trained on a hybrid of
BP4D, DISFA, RAF-AU, Aff-Wild2, CK+ and CASME II. Code and weights Apache-2.0. Exported to
ONNX by ``experiments/export_opengraphau_onnx.py`` (see docs/models.md for hashes).

Preprocessing reproduces the repository's evaluation transform: square crop around the face
box with margin 1.3 (measured stable in 1.0-1.6), resize shorter side to 256, center-crop
224, ImageNet mean/std. Output: 41 sigmoid probabilities (27 AUs + 14 unilateral variants).

Outputs are *occurrence probabilities* from a classifier trained on posed and spontaneous
lab/in-the-wild data. They are not intensities and not validated on this project's footage.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import numpy.typing as npt

from lightman import __version__
from lightman.core.logging import get_logger
from lightman.features.action_units import OPENGRAPHAU_NAMES
from lightman.schema.provenance import Provenance

log = get_logger(__name__)

EXTRACTOR_ID = "au.opengraphau_onnx"
EXTRACTOR_VERSION = "0.1.0"

CROP_MARGIN = 1.3
RESIZE_SHORT = 256
CROP_SIZE = 224
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def preprocess_face(
    rgb: npt.NDArray[np.uint8],
    bbox_px: tuple[float, float, float, float],
    *,
    margin: float = CROP_MARGIN,
) -> npt.NDArray[np.float32]:
    """Square crop around the face box (padded with black where it leaves the frame), resize
    the shorter side to 256, center-crop 224, normalize. Returns (1, 3, 224, 224) float32."""
    h, w = rgb.shape[:2]
    x0, y0, x1, y1 = bbox_px
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    side = max(x1 - x0, y1 - y0) * margin
    if side < 2:
        raise ValueError("face box too small")
    sx0, sy0 = round(cx - side / 2), round(cy - side / 2)
    sx1, sy1 = round(cx + side / 2), round(cy + side / 2)
    canvas = np.zeros((sy1 - sy0, sx1 - sx0, 3), dtype=np.uint8)
    ix0, iy0, ix1, iy1 = max(sx0, 0), max(sy0, 0), min(sx1, w), min(sy1, h)
    if ix1 > ix0 and iy1 > iy0:
        canvas[iy0 - sy0 : iy1 - sy0, ix0 - sx0 : ix1 - sx0] = rgb[iy0:iy1, ix0:ix1]
    # torchvision Resize(256) on a square image gives 256x256; CenterCrop(224) then trims.
    resized = cv2.resize(canvas, (RESIZE_SHORT, RESIZE_SHORT), interpolation=cv2.INTER_LINEAR)
    off = (RESIZE_SHORT - CROP_SIZE) // 2
    crop = resized[off : off + CROP_SIZE, off : off + CROP_SIZE].astype(np.float32) / 255.0
    crop = (crop - _MEAN) / _STD
    return np.ascontiguousarray(crop.transpose(2, 0, 1)[None, ...], dtype=np.float32)


def select_providers(prefer_gpu: bool = True) -> list[str]:
    import onnxruntime as ort

    available = ort.get_available_providers()
    chosen: list[str] = []
    if prefer_gpu and "CUDAExecutionProvider" in available:
        chosen.append("CUDAExecutionProvider")
    # CoreML EP measured slower than CPU for this graph (partial partitioning); not used.
    chosen.append("CPUExecutionProvider")
    return chosen


class OpenGraphAUOnnx:
    def __init__(
        self,
        model_path: Path,
        *,
        model_id: str,
        model_sha256: str | None = None,
        prefer_gpu: bool = True,
        intra_op_threads: int | None = None,
    ) -> None:
        import onnxruntime as ort

        so = ort.SessionOptions()
        so.log_severity_level = 3
        if intra_op_threads:
            so.intra_op_num_threads = intra_op_threads
        providers = select_providers(prefer_gpu)
        self._session = ort.InferenceSession(str(model_path), sess_options=so, providers=providers)
        self._input = self._session.get_inputs()[0].name
        used = self._session.get_providers()[0]
        runtime = f"onnxruntime-{ort.__version__}-" + ("cuda" if used.startswith("CUDA") else "cpu")
        self._provenance = Provenance(
            extractor_id=EXTRACTOR_ID,
            extractor_version=EXTRACTOR_VERSION,
            model_id=model_id,
            model_sha256=model_sha256,
            runtime=runtime,
            lightman_version=__version__,
        )
        log.info("au_detector_loaded", backend=EXTRACTOR_ID, model_id=model_id, provider=used)

    @property
    def provenance(self) -> Provenance:
        return self._provenance

    @property
    def au_names(self) -> list[str]:
        return list(OPENGRAPHAU_NAMES)

    def process(
        self, rgb: npt.NDArray[np.uint8], bbox_px: tuple[float, float, float, float]
    ) -> npt.NDArray[np.float32]:
        x = preprocess_face(rgb, bbox_px)
        out = self._session.run(None, {self._input: x})[0]
        probs = np.asarray(out, dtype=np.float32).reshape(-1)
        if probs.shape[0] != len(OPENGRAPHAU_NAMES):
            raise RuntimeError(f"unexpected AU output size {probs.shape[0]}")
        return np.clip(probs, 0.0, 1.0)

    def close(self) -> None:
        del self._session
