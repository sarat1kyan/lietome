"""Live runner for the CLI: capture thread -> bounded queue (drop oldest) -> LiveAnalyzer on
the caller's thread -> event sink -> session outputs at stop.

Latency policy: the queue holds at most ``queue_size`` frames; when full, the oldest frame is
dropped and counted, so end-to-end latency stays bounded by (queue_size + 1) x inference time.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from pathlib import Path

from lightman.config import LightmanConfig
from lightman.core.logging import get_logger
from lightman.core.timebase import format_timecode
from lightman.face.au_base import AUDetector
from lightman.face.base import FaceLandmarker
from lightman.live.analyzer import LiveAnalyzer, LiveStats
from lightman.live.sources import FrameSource, LiveFrame
from lightman.schema import Event

log = get_logger(__name__)

EventSink = Callable[[Event], None]
PreviewFn = Callable[[LiveFrame, dict[str, float], list[Event], LiveStats], bool]


class _Capture(threading.Thread):
    def __init__(
        self, source: FrameSource, q: queue.Queue[LiveFrame | None], stats: LiveStats
    ) -> None:
        super().__init__(name="lightman-capture", daemon=True)
        self.source = source
        self.q = q
        self.stats = stats
        self.stop_event = threading.Event()

    def run(self) -> None:
        try:
            while not self.stop_event.is_set():
                fr = self.source.read()
                if fr is None:
                    break
                self.stats.frames_captured += 1
                while True:
                    try:
                        self.q.put_nowait(fr)
                        break
                    except queue.Full:
                        try:
                            self.q.get_nowait()  # drop the oldest frame
                            self.stats.frames_dropped += 1
                        except queue.Empty:
                            pass
        finally:
            self.q.put(None)  # sentinel


def console_sink(event: Event) -> None:
    contrib = event.contributions[0] if event.contributions else None
    extra = f" {contrib.peak_deviation:+.1f} SD" if contrib and event.event_type != "blink" else ""
    print(  # noqa: T201 - live console output is the product here
        f"[{format_timecode(event.start_us)}] {event.event_type:<20} {event.label}{extra}",
        flush=True,
    )


def run_live(
    source: FrameSource,
    *,
    cfg: LightmanConfig,
    out_dir: Path,
    landmarker: FaceLandmarker,
    au_detector: AUDetector | None = None,
    duration_s: float | None = None,
    subject_id: str = "subject_001",
    sink: EventSink | None = None,
    preview: PreviewFn | None = None,
    queue_size: int = 2,
    stop_flag: threading.Event | None = None,
) -> Path:
    """Run live analysis until the source ends, ``duration_s`` elapses, the preview callback
    returns False, or ``stop_flag`` is set. Returns the session directory."""
    sink = sink or console_sink
    analyzer = LiveAnalyzer(
        cfg, landmarker, au_detector, subject_id=subject_id, source_description=source.description
    )
    stats = analyzer.stats
    q: queue.Queue[LiveFrame | None] = queue.Queue(maxsize=queue_size)
    cap = _Capture(source, q, stats)
    log.info("live_session_started", session_id=analyzer.session_id, source=source.description)
    ended_by = "source_end"
    cap.start()
    try:
        while True:
            if stop_flag is not None and stop_flag.is_set():
                ended_by = "stop_flag"
                break
            if duration_s is not None and time.monotonic() - stats.started_monotonic >= duration_s:
                ended_by = "duration"
                break
            try:
                fr = q.get(timeout=0.5)
            except queue.Empty:
                continue
            if fr is None:
                break
            res = analyzer.process_frame(fr.rgb, fr.t_us, capture_wall_ns=fr.capture_wall_ns)
            for e in res.new_events:
                sink(e)
            if preview is not None and not preview(fr, res.values, res.new_events, stats):
                ended_by = "user"
                break
    finally:
        cap.stop_event.set()
        source.close()
    before = len(analyzer.events)
    session_dir = analyzer.finish(out_dir, ended_by=ended_by)
    for e in analyzer.events[before:]:  # runs flushed at end of stream
        sink(e)
    return session_dir


__all__ = ["LiveStats", "console_sink", "run_live"]
