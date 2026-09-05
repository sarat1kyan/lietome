"""Micro-benchmark: MediaPipe Face Landmarker throughput on this machine.

Usage: uv run python experiments/bench_face_landmarker.py [frames]
Prints ms/frame (mean, p50, p95) at several resolutions using the licensed portrait fixture.
This measures the landmarker only (decode excluded). Results go to docs/benchmarks.md.
"""

from __future__ import annotations

import platform
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from lightman.face.mediapipe_backend import MediaPipeFaceLandmarker
from lightman.models import ModelRegistry

ROOT = Path(__file__).resolve().parents[1]
PORTRAIT = ROOT / "tests" / "fixtures" / "portrait_mediapipe_apache2.jpg"


def letterbox(img: np.ndarray, w: int, h: int) -> np.ndarray:
    """Scale to fit inside (w, h) preserving aspect ratio; pad with mid-gray."""
    ih, iw = img.shape[:2]
    scale = min(w / iw, h / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    canvas = np.full((h, w, 3), 96, dtype=np.uint8)
    x0, y0 = (w - nw) // 2, (h - nh) // 2
    canvas[y0 : y0 + nh, x0 : x0 + nw] = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
    return canvas


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    reg = ModelRegistry(allow_download=False)
    path = reg.verify("mediapipe/face_landmarker")
    img = cv2.cvtColor(cv2.imread(str(PORTRAIT)), cv2.COLOR_BGR2RGB)
    print(f"machine: {platform.machine()} {platform.system()} python {platform.python_version()}")
    for w, h in ((640, 480), (1280, 720), (1920, 1080)):
        frame = letterbox(img, w, h)
        lm = MediaPipeFaceLandmarker(path)
        # warm-up
        for i in range(10):
            lm.process(frame, i * 33_333)
        times = []
        for i in range(n):
            t = time.perf_counter()
            faces = lm.process(frame, (i + 10) * 33_333)
            times.append((time.perf_counter() - t) * 1000)
        lm.close()
        arr = np.array(times)
        print(
            f"{w}x{h}: mean {arr.mean():.2f} ms  p50 {np.percentile(arr, 50):.2f}  "
            f"p95 {np.percentile(arr, 95):.2f}  faces={len(faces)}"
        )


if __name__ == "__main__":
    main()
