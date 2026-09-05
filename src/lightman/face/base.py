"""Backend-agnostic face landmark interface.

Any backend (MediaPipe today; ONNX/PyTorch models later) must produce
:class:`FaceObservation` objects. Downstream feature code depends only on this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import numpy as np
import numpy.typing as npt

from lightman.schema.provenance import Provenance


@dataclass(slots=True)
class FaceObservation:
    """One detected face in one frame.

    ``landmarks`` are normalized image coordinates (x, y in [0, 1], z relative depth) with
    shape (N, 3). ``blendshapes`` maps coefficient names to values in [0, 1] and may be
    empty for backends that do not produce them. ``transform`` is a 4x4 canonical-face to
    camera-space matrix (row-major) or ``None``.
    """

    landmarks: npt.NDArray[np.float32]
    blendshapes: dict[str, float] = field(default_factory=dict)
    transform: npt.NDArray[np.float32] | None = None
    track_id: int = 0
    """Backend-local tracking id (stable across frames if the backend tracks)."""

    def bbox_normalized(self) -> tuple[float, float, float, float]:
        xs, ys = self.landmarks[:, 0], self.landmarks[:, 1]
        return float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())


@runtime_checkable
class FaceLandmarker(Protocol):
    """Stateful per-stream face landmarker. Call ``process`` with monotonically increasing
    timestamps; call ``close`` when done."""

    @property
    def provenance(self) -> Provenance: ...

    @property
    def blendshape_names(self) -> list[str]: ...

    def process(self, rgb: npt.NDArray[np.uint8], t_us: int) -> list[FaceObservation]: ...

    def close(self) -> None: ...
