"""Subject screen: a second view for the person being interviewed.

The operator keeps the HUD, numbers and gauges; the subject sees only what they need: the
calibration instruction and passage, the current question, and (in the validation game) a
private card telling them whether to answer truthfully or lie on this question. Nothing the
subject sees depends on measurements, so they cannot react to their own numbers.

The operator's live page posts subject state over its live WebSocket; this hub keeps the
latest state and fans it out to every connected subject screen.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

ALLOWED_KEYS = frozenset(
    {"status", "phase", "instruction", "passage", "remaining_s", "question", "card", "note"}
)
MAX_TEXT = 1200


def clean_state(raw: Any) -> dict[str, Any]:
    """Keep only known keys and bounded plain values."""
    out: dict[str, Any] = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        if k not in ALLOWED_KEYS:
            continue
        if isinstance(v, str):
            out[k] = v[:MAX_TEXT]
        elif isinstance(v, int | float) and not isinstance(v, bool):
            out[k] = float(v)
        elif v is None:
            out[k] = None
        elif isinstance(v, dict) and k == "question":
            out[k] = {
                kk: str(vv)[:MAX_TEXT] for kk, vv in v.items() if kk in ("id", "text", "number")
            }
    return out


class SubjectHub:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {"status": "idle"}
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def publish(self, raw: Any) -> None:
        self.state = clean_state(raw) or {"status": "idle"}
        msg = json.dumps({"type": "subject", **self.state})
        async with self._lock:
            dead = []
            for ws in self._clients:
                try:
                    await ws.send_text(msg)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._clients.discard(ws)

    async def serve(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        await ws.send_text(json.dumps({"type": "subject", **self.state}))
        try:
            while True:
                await ws.receive_text()  # screens only listen; keep the socket open
        except WebSocketDisconnect:
            pass
        finally:
            async with self._lock:
                self._clients.discard(ws)
            with contextlib.suppress(Exception):
                await ws.close()

    @property
    def screens(self) -> int:
        return len(self._clients)
