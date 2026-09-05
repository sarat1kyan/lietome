"""Live runner: capture thread -> bounded queue (drop oldest) -> analysis loop on the caller's
thread -> streaming baseline/detectors -> event sink -> session outputs at stop.

Latency policy: the queue holds at most ``queue_size`` frames; when full, the oldest frame is
dropped and counted. Stale frames are never analyzed, so end-to-end latency stays bounded by
(queue_size + 1) x inference time instead of growing without limit.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from lightman import __version__
from lightman.config import LightmanConfig
from lightman.core.env import snapshot_environment
from lightman.core.logging import get_logger
from lightman.core.timebase import format_timecode, utc_now_iso
from lightman.events.blinks import blink_threshold
from lightman.face.au_base import AUDetector
from lightman.face.base import FaceLandmarker
from lightman.features.action_units import OPENGRAPHAU_NAMES
from lightman.features.eyes import eye_aspect_ratios
from lightman.features.head_pose import head_pose_from_matrix
from lightman.features.quality import face_quality
from lightman.features.table import FeatureTableBuilder
from lightman.live.sources import FrameSource, LiveFrame
from lightman.live.streaming import (
    StreamingBaseline,
    StreamingBlinkDetector,
    StreamingDeviationDetector,
)
from lightman.media import sha256_file
from lightman.pipeline.analyze import DISCLAIMER, _artifact, _nan_to_none, _new_session_id
from lightman.schema import AnalysisManifest, Event, MediaInfo, OutputArtifact, QualitySummary
from lightman.schema.media import VideoStreamInfo

log = get_logger(__name__)

EventSink = Callable[[Event], None]


@dataclass(slots=True)
class LiveStats:
    frames_captured: int = 0
    frames_analyzed: int = 0
    frames_dropped: int = 0
    frames_with_face: int = 0
    latency_ms: list[float] = field(default_factory=list)
    infer_ms: list[float] = field(default_factory=list)
    started_monotonic: float = 0.0

    def summary(self) -> dict[str, Any]:
        lat = np.asarray(self.latency_ms) if self.latency_ms else np.zeros(0)
        inf = np.asarray(self.infer_ms) if self.infer_ms else np.zeros(0)
        elapsed = max(1e-6, time.monotonic() - self.started_monotonic)
        return {
            "frames_captured": self.frames_captured,
            "frames_analyzed": self.frames_analyzed,
            "frames_dropped": self.frames_dropped,
            "frames_with_face": self.frames_with_face,
            "analyzed_fps": self.frames_analyzed / elapsed,
            "latency_ms_p50": float(np.percentile(lat, 50)) if lat.size else None,
            "latency_ms_p95": float(np.percentile(lat, 95)) if lat.size else None,
            "infer_ms_p50": float(np.percentile(inf, 50)) if inf.size else None,
        }


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
    preview: Callable[[LiveFrame, dict[str, float], list[Event], LiveStats], bool] | None = None,
    queue_size: int = 2,
    stop_flag: threading.Event | None = None,
) -> Path:
    """Run live analysis until the source ends, ``duration_s`` elapses, the preview callback
    returns False, or ``stop_flag`` is set. Returns the session directory."""
    sink = sink or console_sink
    stats = LiveStats(started_monotonic=time.monotonic())
    q: queue.Queue[LiveFrame | None] = queue.Queue(maxsize=queue_size)
    cap = _Capture(source, q, stats)
    session_id = _new_session_id()
    session_dir = out_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=False)
    log.info("live_session_started", session_id=session_id, source=source.description)

    signals = list(cfg.events.signals)
    baseline = StreamingBaseline(cfg.baseline, [*signals, "eye.aspect_ratio_mean"])
    deviation: StreamingDeviationDetector | None = None
    blinks: StreamingBlinkDetector | None = None
    events: list[Event] = []
    builder = FeatureTableBuilder()
    period_us = 33_333
    last_t: int | None = None
    frame_index = 0
    warmup_us = cfg.events.warmup_ms * 1000
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
            h, w = fr.rgb.shape[:2]
            t_inf = time.perf_counter()
            faces = landmarker.process(fr.rgb, fr.t_us)
            values: dict[str, float] = {}
            quality = 0.0
            if faces:
                face = faces[0]
                bbox = face.bbox_normalized()
                width_px = (bbox[2] - bbox[0]) * w
                head = None
                yaw = pitch = None
                if face.transform is not None:
                    hp = head_pose_from_matrix(face.transform)
                    head = (hp.yaw_deg, hp.pitch_deg, hp.roll_deg, hp.tx, hp.ty, hp.tz)
                    yaw, pitch = hp.yaw_deg, hp.pitch_deg
                    values.update(
                        {
                            "head.yaw_deg": hp.yaw_deg,
                            "head.pitch_deg": hp.pitch_deg,
                            "head.roll_deg": hp.roll_deg,
                        }
                    )
                ear_r, ear_l = eye_aspect_ratios(face.landmarks, w, h)
                ear_mean = float(np.nanmean([ear_r, ear_l]))
                values["eye.aspect_ratio_mean"] = ear_mean
                values.update({f"blendshape.{k}": v for k, v in face.blendshapes.items()})
                quality = face_quality(width_px, yaw, pitch)
                aus = None
                if (
                    au_detector is not None
                    and frame_index % cfg.au.stride == 0
                    and width_px >= cfg.au.min_face_px
                ):
                    aus = au_detector.process(
                        fr.rgb, (bbox[0] * w, bbox[1] * h, bbox[2] * w, bbox[3] * h)
                    )
                    values.update(
                        {f"au.{n}": float(v) for n, v in zip(OPENGRAPHAU_NAMES, aus, strict=True)}
                    )
                builder.add_frame(
                    frame_index=frame_index,
                    source_index=frame_index,
                    t_us=fr.t_us,
                    timestamp_estimated=False,
                    face_count=len(faces),
                    quality=quality,
                    bbox=bbox,
                    face_width_px=width_px,
                    head=head,
                    eyes=(ear_r, ear_l, ear_mean),
                    blendshapes=face.blendshapes,
                    aus=aus,
                )
                stats.frames_with_face += 1
            else:
                builder.add_frame(
                    frame_index=frame_index,
                    source_index=frame_index,
                    t_us=fr.t_us,
                    timestamp_estimated=False,
                    face_count=0,
                    quality=0.0,
                    bbox=None,
                    face_width_px=0.0,
                    head=None,
                    eyes=None,
                    blendshapes=None,
                )
            stats.infer_ms.append((time.perf_counter() - t_inf) * 1000)
            stats.latency_ms.append((time.monotonic_ns() - fr.capture_wall_ns) / 1e6)
            stats.frames_analyzed += 1
            if last_t is not None and fr.t_us > last_t:
                period_us = int(0.9 * period_us + 0.1 * (fr.t_us - last_t))
            last_t = fr.t_us
            frame_index += 1

            new_events: list[Event] = []
            if not baseline.ready:
                if baseline.update(fr.t_us, quality, values):
                    snap = baseline.snapshot
                    assert snap is not None  # noqa: S101 - just set by update()
                    deviation = StreamingDeviationDetector(
                        cfg.events,
                        snap,
                        subject_id=subject_id,
                        extractor_id=landmarker.provenance.extractor_id,
                        frame_period_us=period_us,
                        id_start=len(events),
                    )
                    blinks = StreamingBlinkDetector(
                        cfg.events,
                        blink_threshold(snap, cfg.events),
                        baseline=snap,
                        subject_id=subject_id,
                        extractor_id=landmarker.provenance.extractor_id,
                        frame_period_us=period_us,
                        id_start=100_000,
                    )
                    log.info(
                        "live_baseline_ready",
                        frames_used=snap.frames_used,
                        quality=round(snap.quality, 2),
                    )
            else:
                assert deviation is not None and blinks is not None  # noqa: S101
                new_events += deviation.update(fr.t_us, quality, values)
                new_events += blinks.update(
                    fr.t_us, quality, values.get("eye.aspect_ratio_mean", float("nan"))
                )
            for e in new_events:
                if e.start_us < warmup_us:
                    continue
                events.append(e)
                sink(e)
            if preview is not None and not preview(fr, values, new_events, stats):
                ended_by = "user"
                break
    finally:
        cap.stop_event.set()
        source.close()
        if deviation is not None:
            for e in deviation.flush():
                events.append(e)
                sink(e)
    if not baseline.ready:
        baseline.finalize()
    snap = baseline.snapshot
    assert snap is not None  # noqa: S101

    # ---- outputs (same layout as prerecorded sessions)
    cols = builder.to_numpy()
    n = len(builder)
    outputs: list[OutputArtifact] = []
    feat_path = session_dir / "features.parquet"
    builder.write_parquet(feat_path)
    outputs.append(_artifact(feat_path, "parquet"))
    events.sort(key=lambda e: (e.start_us, e.event_id))
    events_path = session_dir / "events.json"
    events_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "events": [_nan_to_none(e.model_dump(mode="json")) for e in events],
            },
            indent=2,
        ),
        "utf-8",
    )
    outputs.append(_artifact(events_path, "json"))
    base_path = session_dir / "baseline.json"
    base_path.write_text(json.dumps(_nan_to_none(snap.model_dump(mode="json")), indent=2), "utf-8")
    outputs.append(_artifact(base_path, "json"))
    live_stats = stats.summary()
    live_stats["ended_by"] = ended_by
    live_stats["blink_count"] = blinks.blink_count if blinks else 0
    (session_dir / "analysis.json").write_text(
        json.dumps(
            _nan_to_none(
                {
                    "session_id": session_id,
                    "mode": "live",
                    "source": source.description,
                    **live_stats,
                }
            ),
            indent=2,
        ),
        "utf-8",
    )
    outputs.append(_artifact(session_dir / "analysis.json", "json"))

    media = MediaInfo(
        path_name=source.description,
        size_bytes=0,
        sha256="0" * 64,
        container_format="live",
        duration_us=int(cols["t_us"][-1]) if n else 0,
        video_streams=[
            VideoStreamInfo(
                index=0,
                codec="raw",
                width=int(w) if n else 0,
                height=int(h) if n else 0,
                time_base="1/1000000",
            )
        ],
        audio_streams=[],
    )
    face_frames = int(cols["face_present"].sum()) if n else 0
    q_present = cols["quality"][cols["face_present"]] if n else np.zeros(0)
    quality_summary = QualitySummary(
        frames_total=stats.frames_captured,
        frames_decoded=n,
        frames_with_face=face_frames,
        face_coverage=face_frames / n if n else 0.0,
        mean_face_quality=float(q_present.mean()) if q_present.size else None,
        baseline_quality=snap.quality,
        baseline_window_us=(0, snap.window_end_us),
        notes=list(snap.notes)
        + (
            [f"{stats.frames_dropped} frames dropped to bound latency"]
            if stats.frames_dropped
            else []
        ),
    )
    if cfg.storage.write_report and n:
        from lightman.report.html import render_report

        report_path = session_dir / "report.html"
        render_report(
            dest=report_path,
            media=media,
            summary={
                "session_id": session_id,
                "subject_id": subject_id,
                "duration_us": media.duration_us,
                "inference_ms_per_frame": {
                    "p50": live_stats["infer_ms_p50"],
                    "p95": live_stats["infer_ms_p50"],
                },
                "blink_count": live_stats["blink_count"],
                "blink_rate_per_min": None,
                "event_counts": {
                    k: sum(1 for e in events if e.event_type == k)
                    for k in sorted({e.event_type for e in events})
                },
            },
            quality=quality_summary,
            baseline=snap,
            events=events,
            table=cols,
            thumbnails={},
            disclaimer=DISCLAIMER,
            signals_to_plot=cfg.events.signals,
        )
        outputs.append(_artifact(report_path, "html"))
    manifest = AnalysisManifest(
        session_id=session_id,
        subject_ids=[subject_id],
        created_utc=utc_now_iso(),
        lightman_version=__version__,
        media=media,
        config=cfg.snapshot(),
        environment=snapshot_environment(),
        provenance=[landmarker.provenance] + ([au_detector.provenance] if au_detector else []),
        quality=quality_summary,
        outputs=outputs,
        timing_ms={},
        disclaimer=DISCLAIMER,
    )
    (session_dir / "manifest.json").write_text(
        json.dumps(_nan_to_none(manifest.model_dump(mode="json")), indent=2), "utf-8"
    )
    log.info(
        "live_session_complete",
        session_id=session_id,
        **{k: (round(v, 1) if isinstance(v, float) else v) for k, v in live_stats.items()},
    )
    return session_dir


__all__ = ["LiveStats", "console_sink", "run_live", "sha256_file"]
