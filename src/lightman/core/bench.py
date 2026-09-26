"""Per-machine inference benchmark and the live AU model choice it drives.

`lightman bench` times each model on this machine (face landmarks, both AU models, pose, VAD)
and stores the result under the user config directory. Live mode with the AU model set to
"auto" uses resnet50 when this machine ran it within the live frame budget, else resnet18.
"""

from __future__ import annotations

import json
import platform
import socket
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from platformdirs import user_config_dir

LIVE_BUDGET_MS = 45.0
"""AU inference p95 that still leaves room for landmarks, pose and encoding at ~15 fps."""
RESNET50 = "opengraphau/resnet50_s2"
RESNET18 = "opengraphau/resnet18_s2"


def bench_path() -> Path:
    return Path(user_config_dir("lightman", appauthor=False)) / "bench.json"


def _time(fn: Callable[[], Any], n: int, warmup: int = 3) -> dict[str, float]:
    for _ in range(warmup):
        fn()
    ts = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        ts.append((time.perf_counter() - t0) * 1000)
    return {
        "p50_ms": round(float(np.percentile(ts, 50)), 2),
        "p95_ms": round(float(np.percentile(ts, 95)), 2),
        "n": n,
    }


def run_bench(
    image: npt.NDArray[np.uint8], *, registry: Any, frames: int = 40, prefer_gpu: bool = True
) -> dict[str, Any]:
    """Time every available model on ``image`` (HxWx3 RGB). Missing models are skipped."""
    import onnxruntime as ort

    from lightman.core.errors import LightmanError

    h, w = image.shape[:2]
    out: dict[str, Any] = {
        "host": socket.gethostname(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "onnx_providers": ort.get_available_providers(),
        "image": [w, h],
        "models": {},
    }
    bbox = (w * 0.3, h * 0.15, w * 0.7, h * 0.6)
    try:
        from lightman.face.mediapipe_backend import MediaPipeFaceLandmarker

        lm = MediaPipeFaceLandmarker(registry.ensure("mediapipe/face_landmarker"))
        t = [0]

        def face() -> None:
            t[0] += 66_000
            lm.process(image, t[0])

        out["models"]["mediapipe/face_landmarker"] = _time(face, frames)
        faces = lm.process(image, t[0] + 66_000)
        if faces:
            x0, y0, x1, y1 = faces[0].bbox_normalized()
            bbox = (x0 * w, y0 * h, x1 * w, y1 * h)
        lm.close()
    except (LightmanError, OSError, RuntimeError) as exc:
        out["models"]["mediapipe/face_landmarker"] = {"error": str(exc)}
    for mid in (RESNET18, RESNET50):
        try:
            from lightman.face.opengraphau_onnx import OpenGraphAUOnnx

            au = OpenGraphAUOnnx(registry.ensure(mid), model_id=mid, prefer_gpu=prefer_gpu)

            def run_au(det: Any = au) -> None:
                det.process(image, bbox)

            out["models"][mid] = {**_time(run_au, frames), "provider": au.provenance.runtime}
            au.close()
        except (LightmanError, OSError, RuntimeError) as exc:
            out["models"][mid] = {"error": str(exc)}
    try:
        from lightman.body.pose import MediaPipePose

        pose = MediaPipePose(registry.ensure("mediapipe/pose_landmarker_lite"))
        tp = [0]

        def body() -> None:
            tp[0] += 66_000
            pose.process(image, tp[0])

        out["models"]["mediapipe/pose_landmarker_lite"] = _time(body, frames)
        pose.close()
    except (LightmanError, OSError, RuntimeError) as exc:
        out["models"]["mediapipe/pose_landmarker_lite"] = {"error": str(exc)}
    out["live_au_model"] = choose_from(out)
    out["created"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    return out


def choose_from(bench: dict[str, Any]) -> str:
    r50 = bench.get("models", {}).get(RESNET50, {})
    p95 = r50.get("p95_ms")
    return RESNET50 if isinstance(p95, int | float) and p95 <= LIVE_BUDGET_MS else RESNET18


def save_bench(result: dict[str, Any]) -> Path:
    p = bench_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, indent=2))
    return p


def live_au_model(setting: str) -> str:
    """Resolve the live AU model: an explicit id, or "auto" from this machine's benchmark."""
    if setting != "auto":
        return setting
    p = bench_path()
    if not p.is_file():
        return RESNET18
    try:
        return choose_from(json.loads(p.read_text("utf-8")))
    except (OSError, json.JSONDecodeError):
        return RESNET18
