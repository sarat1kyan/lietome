"""Frame sources for live mode.

``WebcamSource`` wraps OpenCV capture (the only place cv2 touches a device). ``FileSource``
replays a file at its real-time pace so the whole live pipeline (queueing, dropping, latency
accounting) can be exercised and tested without a camera.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
import numpy.typing as npt

from lightman.core.errors import MediaError
from lightman.media.decode import iter_video_frames


@dataclass(slots=True)
class LiveFrame:
    capture_wall_ns: int
    """time.monotonic_ns() when the frame was obtained from the device."""
    t_us: int
    """Media time since the source started (monotonic-derived for cameras)."""
    rgb: npt.NDArray[np.uint8]


class FrameSource(Protocol):
    def read(self) -> LiveFrame | None:
        """Blocking read of the next frame; ``None`` at end of stream."""
        ...

    def close(self) -> None: ...

    @property
    def description(self) -> str: ...


class WebcamSource:
    def __init__(
        self, index: int = 0, *, width: int | None = None, height: int | None = None
    ) -> None:
        import cv2

        self._cap = cv2.VideoCapture(index)
        if not self._cap.isOpened():
            raise MediaError(
                f"cannot open camera {index}; check that the terminal/app has camera permission"
            )
        if width:
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        if height:
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self._cv2 = cv2
        self._t0_ns: int | None = None
        self.index = index
        w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(self._cap.get(cv2.CAP_PROP_FPS))
        self._desc = f"camera {index} {w}x{h} @ {fps:.0f} fps (reported)"

    @property
    def description(self) -> str:
        return self._desc

    def read(self) -> LiveFrame | None:
        ok, bgr = self._cap.read()
        now = time.monotonic_ns()
        if not ok or bgr is None:
            return None
        if self._t0_ns is None:
            self._t0_ns = now
        rgb = np.ascontiguousarray(self._cv2.cvtColor(bgr, self._cv2.COLOR_BGR2RGB), dtype=np.uint8)
        return LiveFrame(capture_wall_ns=now, t_us=(now - self._t0_ns) // 1000, rgb=rgb)

    def close(self) -> None:
        self._cap.release()


class FileSource:
    """Replays a video file. ``realtime=True`` sleeps to match media time (drops nothing itself;
    the consumer's queue does the dropping, as with a camera)."""

    def __init__(self, path: Path, *, realtime: bool = True, max_frames: int | None = None) -> None:
        self._path = path
        self._realtime = realtime
        self._iter = iter_video_frames(path, max_frames=max_frames)
        self._t0_ns: int | None = None
        self._desc = f"file {path.name} (realtime={realtime})"

    @property
    def description(self) -> str:
        return self._desc

    def read(self) -> LiveFrame | None:
        fr = next(self._iter, None)
        if fr is None:
            return None
        now = time.monotonic_ns()
        if self._t0_ns is None:
            self._t0_ns = now
        if self._realtime:
            due_ns = self._t0_ns + fr.t_us * 1000
            if due_ns > now:
                time.sleep((due_ns - now) / 1e9)
                now = time.monotonic_ns()
        return LiveFrame(capture_wall_ns=now, t_us=fr.t_us, rgb=fr.rgb)

    def close(self) -> None:
        close = getattr(self._iter, "close", None)
        if callable(close):
            close()
