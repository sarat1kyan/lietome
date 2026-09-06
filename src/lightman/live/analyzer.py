"""Frame-by-frame live analyzer shared by the CLI runner and the WebSocket endpoint.

``LiveAnalyzer.process_frame`` runs landmarks (+ optional AU model), updates the streaming
baseline and detectors and returns what a UI needs for that frame. ``finish`` writes the same
session artifacts as the prerecorded pipeline.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from lightman import __version__
from lightman.config import LightmanConfig
from lightman.core.env import snapshot_environment
from lightman.core.logging import get_logger
from lightman.core.timebase import utc_now_iso
from lightman.events.blinks import blink_threshold
from lightman.face.au_base import AUDetector
from lightman.face.base import FaceLandmarker
from lightman.features.action_units import OPENGRAPHAU_NAMES
from lightman.features.eyes import eye_aspect_ratios
from lightman.features.head_pose import head_pose_from_matrix
from lightman.features.quality import face_quality
from lightman.features.table import FeatureTableBuilder
from lightman.live.streaming import (
    StreamingBaseline,
    StreamingBlinkDetector,
    StreamingDeviationDetector,
    StreamingEpisodes,
    tag_speaking,
)
from lightman.pipeline.analyze import DISCLAIMER, _artifact, _nan_to_none, _new_session_id
from lightman.schema import AnalysisManifest, Event, MediaInfo, OutputArtifact, QualitySummary
from lightman.schema.media import VideoStreamInfo

log = get_logger(__name__)


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
        lat = np.asarray(self.latency_ms[-600:]) if self.latency_ms else np.zeros(0)
        inf = np.asarray(self.infer_ms[-600:]) if self.infer_ms else np.zeros(0)
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


@dataclass(slots=True)
class FrameResult:
    t_us: int
    face: bool
    quality: float
    bbox: tuple[float, float, float, float] | None
    values: dict[str, float]
    landmarks_xy: npt.NDArray[np.float32] | None
    new_events: list[Event]
    baseline_ready: bool


class LiveAnalyzer:
    def __init__(
        self,
        cfg: LightmanConfig,
        landmarker: FaceLandmarker,
        au_detector: AUDetector | None = None,
        *,
        subject_id: str = "subject_001",
        source_description: str = "live",
    ) -> None:
        self.cfg = cfg
        self.landmarker = landmarker
        self.au_detector = au_detector
        self.subject_id = subject_id
        self.source_description = source_description
        self.stats = LiveStats(started_monotonic=time.monotonic())
        self.session_id = _new_session_id()
        signals = list(cfg.events.signals)
        self.baseline = StreamingBaseline(cfg.baseline, [*signals, "eye.aspect_ratio_mean"])
        self.deviation: StreamingDeviationDetector | None = None
        self.blinks: StreamingBlinkDetector | None = None
        self.events: list[Event] = []
        self.builder = FeatureTableBuilder()
        self.period_us = 33_333
        self._last_t: int | None = None
        self._frame_index = 0
        self._warmup_us = cfg.events.warmup_ms * 1000
        self._size: tuple[int, int] = (0, 0)
        self._closed = False
        self.episodes = StreamingEpisodes(
            subject_id=subject_id, extractor_id=landmarker.provenance.extractor_id
        )
        self.speaking = False
        """Set by the caller from the audio stream: True while speech is detected."""

    @property
    def baseline_ready(self) -> bool:
        return self.baseline.ready

    def process_frame(
        self, rgb: npt.NDArray[np.uint8], t_us: int, *, capture_wall_ns: int | None = None
    ) -> FrameResult:
        cfg = self.cfg
        h, w = rgb.shape[:2]
        self._size = (w, h)
        t_inf = time.perf_counter()
        faces = self.landmarker.process(rgb, t_us)
        values: dict[str, float] = {}
        quality = 0.0
        bbox: tuple[float, float, float, float] | None = None
        lm_xy: npt.NDArray[np.float32] | None = None
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
                self.au_detector is not None
                and self._frame_index % cfg.au.stride == 0
                and width_px >= cfg.au.min_face_px
            ):
                aus = self.au_detector.process(
                    rgb, (bbox[0] * w, bbox[1] * h, bbox[2] * w, bbox[3] * h)
                )
                values.update(
                    {f"au.{n}": float(v) for n, v in zip(OPENGRAPHAU_NAMES, aus, strict=True)}
                )
            lm_xy = face.landmarks[:, :2]
            self.builder.add_frame(
                frame_index=self._frame_index,
                source_index=self._frame_index,
                t_us=t_us,
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
            self.stats.frames_with_face += 1
        else:
            self.builder.add_frame(
                frame_index=self._frame_index,
                source_index=self._frame_index,
                t_us=t_us,
                timestamp_estimated=False,
                face_count=0,
                quality=0.0,
                bbox=None,
                face_width_px=0.0,
                head=None,
                eyes=None,
                blendshapes=None,
            )
        self.stats.infer_ms.append((time.perf_counter() - t_inf) * 1000)
        if capture_wall_ns is not None:
            self.stats.latency_ms.append((time.monotonic_ns() - capture_wall_ns) / 1e6)
        self.stats.frames_analyzed += 1
        if self._last_t is not None and t_us > self._last_t:
            self.period_us = int(0.9 * self.period_us + 0.1 * (t_us - self._last_t))
        self._last_t = t_us
        self._frame_index += 1

        new_events: list[Event] = []
        if not self.baseline.ready:
            if self.baseline.update(t_us, quality, values):
                self._arm_detectors()
        else:
            assert self.deviation is not None and self.blinks is not None  # noqa: S101
            new_events += self.deviation.update(t_us, quality, values)
            new_events += self.blinks.update(
                t_us, quality, values.get("eye.aspect_ratio_mean", float("nan"))
            )
        kept = [e for e in new_events if e.start_us >= self._warmup_us]
        if self.speaking:
            kept = [tag_speaking(e) for e in kept]
        kept += self.episodes.add(kept, t_us)
        self.events.extend(kept)
        return FrameResult(
            t_us=t_us,
            face=bool(faces),
            quality=quality,
            bbox=bbox,
            values=values,
            landmarks_xy=lm_xy,
            new_events=kept,
            baseline_ready=self.baseline.ready,
        )

    def _arm_detectors(self) -> None:
        snap = self.baseline.snapshot
        assert snap is not None  # noqa: S101 - set by update()/finalize()
        ext = self.landmarker.provenance.extractor_id
        self.deviation = StreamingDeviationDetector(
            self.cfg.events,
            snap,
            subject_id=self.subject_id,
            extractor_id=ext,
            frame_period_us=self.period_us,
            id_start=len(self.events),
        )
        self.blinks = StreamingBlinkDetector(
            self.cfg.events,
            blink_threshold(snap, self.cfg.events),
            baseline=snap,
            subject_id=self.subject_id,
            extractor_id=ext,
            frame_period_us=self.period_us,
            id_start=100_000,
        )
        log.info(
            "live_baseline_ready", frames_used=snap.frames_used, quality=round(snap.quality, 2)
        )

    def finish(self, out_dir: Path, *, ended_by: str = "stop") -> Path:
        """Flush detectors and write the session directory. Idempotent."""
        if self._closed:
            return out_dir / self.session_id
        self._closed = True
        if self.deviation is not None:
            flushed = self.deviation.flush()
            self.events.extend(flushed)
            self.events.extend(self.episodes.add(flushed, self._last_t or 0))
        self.events.extend(self.episodes.flush())
        if not self.baseline.ready:
            self.baseline.finalize()
        snap = self.baseline.snapshot
        assert snap is not None  # noqa: S101
        session_dir = out_dir / self.session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        cols = self.builder.to_numpy()
        n = len(self.builder)
        outputs: list[OutputArtifact] = []
        feat_path = session_dir / "features.parquet"
        self.builder.write_parquet(feat_path)
        outputs.append(_artifact(feat_path, "parquet"))
        self.events.sort(key=lambda e: (e.start_us, e.event_id))
        events_path = session_dir / "events.json"
        events_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "events": [_nan_to_none(e.model_dump(mode="json")) for e in self.events],
                },
                indent=2,
            ),
            "utf-8",
        )
        outputs.append(_artifact(events_path, "json"))
        base_path = session_dir / "baseline.json"
        base_path.write_text(json.dumps(_nan_to_none(snap.model_dump(mode="json")), indent=2))
        outputs.append(_artifact(base_path, "json"))
        live_stats = self.stats.summary()
        live_stats["ended_by"] = ended_by
        live_stats["blink_count"] = self.blinks.blink_count if self.blinks else 0
        analysis = {
            "session_id": self.session_id,
            "mode": "live",
            "source": self.source_description,
            "duration_us": int(cols["t_us"][-1]) if n else 0,
            "event_counts": {
                k: sum(1 for e in self.events if e.event_type == k)
                for k in sorted({e.event_type for e in self.events})
            },
            **live_stats,
        }
        (session_dir / "analysis.json").write_text(json.dumps(_nan_to_none(analysis), indent=2))
        outputs.append(_artifact(session_dir / "analysis.json", "json"))

        w, h = self._size
        media = MediaInfo(
            path_name=self.source_description,
            size_bytes=0,
            sha256="0" * 64,
            container_format="live",
            duration_us=analysis["duration_us"],
            video_streams=[
                VideoStreamInfo(index=0, codec="raw", width=w, height=h, time_base="1/1000000")
            ],
            audio_streams=[],
        )
        face_frames = int(cols["face_present"].sum()) if n else 0
        q_present = cols["quality"][cols["face_present"]] if n else np.zeros(0)
        notes = list(snap.notes)
        if self.stats.frames_dropped:
            notes.append(f"{self.stats.frames_dropped} frames dropped to bound latency")
        quality_summary = QualitySummary(
            frames_total=self.stats.frames_captured or n,
            frames_decoded=n,
            frames_with_face=face_frames,
            face_coverage=face_frames / n if n else 0.0,
            mean_face_quality=float(q_present.mean()) if q_present.size else None,
            baseline_quality=snap.quality,
            baseline_window_us=(0, snap.window_end_us),
            notes=notes,
        )
        if self.cfg.storage.write_report and n:
            from lightman.report.html import render_report

            report_path = session_dir / "report.html"
            render_report(
                dest=report_path,
                media=media,
                summary={
                    "session_id": self.session_id,
                    "subject_id": self.subject_id,
                    "duration_us": media.duration_us,
                    "inference_ms_per_frame": {
                        "p50": live_stats["infer_ms_p50"],
                        "p95": live_stats["infer_ms_p50"],
                    },
                    "blink_count": live_stats["blink_count"],
                    "blink_rate_per_min": None,
                    "event_counts": analysis["event_counts"],
                },
                quality=quality_summary,
                baseline=snap,
                events=self.events,
                table=cols,
                thumbnails={},
                disclaimer=DISCLAIMER,
                signals_to_plot=self.cfg.events.signals,
            )
            outputs.append(_artifact(report_path, "html"))
        manifest = AnalysisManifest(
            session_id=self.session_id,
            subject_ids=[self.subject_id],
            created_utc=utc_now_iso(),
            lightman_version=__version__,
            media=media,
            config=self.cfg.snapshot(),
            environment=snapshot_environment(),
            provenance=[self.landmarker.provenance]
            + ([self.au_detector.provenance] if self.au_detector else []),
            quality=quality_summary,
            outputs=outputs,
            timing_ms={},
            disclaimer=DISCLAIMER,
        )
        (session_dir / "manifest.json").write_text(
            json.dumps(_nan_to_none(manifest.model_dump(mode="json")), indent=2)
        )
        log.info(
            "live_session_complete",
            session_id=self.session_id,
            **{k: (round(v, 1) if isinstance(v, float) else v) for k, v in live_stats.items()},
        )
        return session_dir
