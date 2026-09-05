"""Backend-agnostic Action Unit detector interface.

An AU detector consumes an aligned face crop and returns per-AU occurrence probabilities.
It is deliberately separate from :class:`FaceLandmarker`: landmarks/blendshapes come from a
geometric model, AUs from a FACS-trained classifier. Both are measured signals; the report
labels them by source so the two are never confused.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np
import numpy.typing as npt

from lightman.schema.provenance import Provenance


@runtime_checkable
class AUDetector(Protocol):
    @property
    def provenance(self) -> Provenance: ...

    @property
    def au_names(self) -> list[str]:
        """Ordered output names, e.g. ['AU1', 'AU2', ..., 'AUL14', 'AUR14']."""
        ...

    def process(
        self, rgb: npt.NDArray[np.uint8], bbox_px: tuple[float, float, float, float]
    ) -> npt.NDArray[np.float32]:
        """Return probabilities aligned with ``au_names`` for the face inside ``bbox_px``
        (x0, y0, x1, y1 in pixels of ``rgb``)."""
        ...

    def close(self) -> None: ...
