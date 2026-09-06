"""WebSocket live endpoint: the browser captures camera/microphone (its permission model) and
streams JPEG frames and 16 kHz PCM; the server runs LiveAnalyzer / StreamingAudioAnalyzer and
streams results back. One analysis at a time per connection; frames are processed in a worker
thread so the event loop stays responsive.

Binary message layout (client -> server): 1 byte kind (1 video JPEG, 2 audio float32 PCM),
8 bytes big-endian t_us, payload. Text messages are JSON.
"""

from __future__ import annotations

import contextlib
import functools
import json
import struct
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from anyio import to_thread
from fastapi import WebSocket, WebSocketDisconnect

from lightman.config import LightmanConfig
from lightman.core.errors import LightmanError
from lightman.core.logging import get_logger
from lightman.face.au_base import AUDetector
from lightman.face.base import FaceLandmarker
from lightman.live.analyzer import LiveAnalyzer
from lightman.live.audio_stream import StreamingAudioAnalyzer
from lightman.models import ModelRegistry
from lightman.pipeline.analyze import _nan_to_none
from lightman.pipeline.audio_stage import VAD_MODEL_ID
from lightman.schema import Event

log = get_logger(__name__)

MAX_FRAME_BYTES = 4 * 1024 * 1024
MAX_AUDIO_SAMPLES = 16_000 * 5
LANDMARK_STRIDE = 1  # send all 478 points (x, y) rounded to 4 decimals

LandmarkerFactory = Callable[[LightmanConfig, ModelRegistry], FaceLandmarker]
AUFactory = Callable[[LightmanConfig, ModelRegistry], AUDetector]


def _decode_jpeg(buf: bytes) -> np.ndarray:
    import cv2

    arr = np.frombuffer(buf, dtype=np.uint8)
    bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if bgr is None:
        raise LightmanError("undecodable frame")
    return np.ascontiguousarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), dtype=np.uint8)


def _events_payload(events: list[Event]) -> dict[str, Any]:
    return {"type": "events", "events": [_nan_to_none(e.model_dump(mode="json")) for e in events]}


async def live_endpoint(
    ws: WebSocket,
    *,
    cfg: LightmanConfig,
    registry: ModelRegistry,
    output_root: Path,
    landmarker_factory: LandmarkerFactory,
    au_factory: AUFactory,
) -> None:
    await ws.accept()
    analyzer: LiveAnalyzer | None = None
    audio: StreamingAudioAnalyzer | None = None
    landmarker: FaceLandmarker | None = None
    au: AUDetector | None = None
    ended_by = "disconnect"
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("text") is not None:
                data = json.loads(msg["text"])
                kind = data.get("type")
                if kind == "start" and analyzer is None:
                    run_cfg = cfg
                    if data.get("au"):
                        run_cfg = run_cfg.model_copy(
                            update={
                                "au": run_cfg.au.model_copy(
                                    update={"enabled": True, "model": "opengraphau/resnet18_s2"}
                                )
                            }
                        )
                    else:
                        run_cfg = run_cfg.model_copy(
                            update={"au": run_cfg.au.model_copy(update={"enabled": False})}
                        )
                    try:
                        landmarker = await to_thread.run_sync(landmarker_factory, run_cfg, registry)
                        if run_cfg.au.enabled:
                            au = await to_thread.run_sync(au_factory, run_cfg, registry)
                        if data.get("audio"):
                            from lightman.audio.vad import SileroVAD

                            path = await to_thread.run_sync(registry.ensure, VAD_MODEL_ID)
                            vad = SileroVAD(
                                path,
                                model_id=VAD_MODEL_ID,
                                model_sha256=registry.get(VAD_MODEL_ID).sha256,
                            )
                            audio = StreamingAudioAnalyzer(
                                run_cfg, vad, subject_id=str(data.get("subject", "subject_001"))
                            )
                    except LightmanError as exc:
                        await ws.send_text(json.dumps({"type": "error", "detail": str(exc)}))
                        break
                    analyzer = LiveAnalyzer(
                        run_cfg,
                        landmarker,
                        au,
                        subject_id=str(data.get("subject", "subject_001")),
                        source_description=str(data.get("source", "browser"))[:80],
                    )
                    await ws.send_text(
                        json.dumps({"type": "ready", "session_id": analyzer.session_id})
                    )
                elif kind == "stop":
                    ended_by = "user"
                    break
                continue
            raw: bytes | None = msg.get("bytes")
            if raw is None or analyzer is None or len(raw) < 9:
                continue
            kind_b, t_us = raw[0], struct.unpack(">Q", raw[1:9])[0]
            payload = raw[9:]
            if kind_b == 1:
                if len(payload) > MAX_FRAME_BYTES:
                    await ws.send_text(json.dumps({"type": "error", "detail": "frame too large"}))
                    continue
                analyzer.stats.frames_captured += 1
                received_ns = (
                    time.monotonic_ns()
                )  # latency = receive -> analyzed (excludes network)
                try:
                    rgb = await to_thread.run_sync(_decode_jpeg, payload)
                    res = await to_thread.run_sync(
                        functools.partial(
                            analyzer.process_frame, rgb, int(t_us), capture_wall_ns=received_ns
                        )
                    )
                except LightmanError as exc:
                    await ws.send_text(json.dumps({"type": "error", "detail": str(exc)}))
                    continue
                lm = None
                if res.landmarks_xy is not None:
                    lm = np.round(res.landmarks_xy[::LANDMARK_STRIDE].reshape(-1), 4).tolist()
                shown = {
                    k: round(v, 4)
                    for k, v in res.values.items()
                    if k.startswith(("head.", "eye.", "au.")) or k in cfg.events.signals
                }
                await ws.send_text(
                    json.dumps(
                        _nan_to_none(
                            {
                                "type": "frame",
                                "t_us": res.t_us,
                                "face": res.face,
                                "quality": round(res.quality, 3),
                                "bbox": list(res.bbox) if res.bbox else None,
                                "values": shown,
                                "landmarks": lm,
                                "baseline_ready": res.baseline_ready,
                                "stats": analyzer.stats.summary(),
                            }
                        )
                    )
                )
                if res.new_events:
                    await ws.send_text(json.dumps(_events_payload(res.new_events)))
            elif kind_b == 2 and audio is not None:
                if len(payload) % 4 or len(payload) // 4 > MAX_AUDIO_SAMPLES:
                    continue
                pcm = np.frombuffer(payload, dtype="<f4")
                results = await to_thread.run_sync(audio.push, pcm, int(t_us))
                if results:
                    last = results[-1]
                    analyzer.speaking = last.speech_prob >= cfg.audio.vad_threshold
                    await ws.send_text(
                        json.dumps(
                            _nan_to_none(
                                {
                                    "type": "audio",
                                    "t_us": last.t_us,
                                    "speech_prob": round(last.speech_prob, 3),
                                    "f0_hz": last.f0_hz,
                                    "energy_db": round(last.energy_db, 1),
                                    "voiced": last.voiced,
                                    "baseline_ready": last.baseline_ready,
                                }
                            )
                        )
                    )
                    new = [e for r in results for e in r.new_events]
                    if new:
                        analyzer.events.extend(new)
                        await ws.send_text(json.dumps(_events_payload(new)))
    except WebSocketDisconnect:
        ended_by = "disconnect"
    finally:
        if analyzer is not None:
            if audio is not None:
                analyzer.events.extend(audio.finish())
            session_dir = await to_thread.run_sync(
                lambda: analyzer.finish(output_root, ended_by=ended_by)
            )
            with contextlib.suppress(Exception):  # client may already be gone
                await ws.send_text(json.dumps({"type": "session", "session_id": session_dir.name}))
        if landmarker is not None:
            landmarker.close()
        if au is not None:
            au.close()
        with contextlib.suppress(Exception):
            await ws.close()
