"""Prerecorded-video vertical slice.

probe -> limits -> decode (PyAV) -> face landmarks -> per-frame features
      -> leading-window robust baseline -> events (blinks, deviations, clusters)
      -> outputs (metadata.json, features.parquet, baseline.json, events.json,
                  analysis.json, thumbnails/, report.html, manifest.json)
"""

from __future__ import annotations

import json
import math
import secrets
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from lightman import __version__
from lightman.audio.vad import SileroVAD
from lightman.baseline import BaselineSnapshot, compute_state_baselines
from lightman.baseline.robust import STATE_ALL, STATE_SILENT, STATE_SPEAKING
from lightman.config import LightmanConfig
from lightman.core.env import snapshot_environment
from lightman.core.errors import LightmanError, UnsupportedMediaError
from lightman.core.logging import get_logger
from lightman.core.timebase import utc_now_iso
from lightman.events import cluster_cooccurring, detect_blinks, detect_deviation_events
from lightman.face.au_base import AUDetector
from lightman.face.base import FaceLandmarker
from lightman.features.eyes import eye_aspect_ratios
from lightman.features.head_pose import head_pose_from_matrix
from lightman.features.quality import face_quality
from lightman.features.smoothing import median_smooth
from lightman.features.table import AU_COLUMNS, SIGNAL_COLUMNS, FeatureTableBuilder
from lightman.live.streaming import tag_speaking
from lightman.media import MediaLimits, iter_video_frames, probe_media, sha256_file
from lightman.models import ModelRegistry
from lightman.pipeline.audio_stage import AudioStageResult, run_audio_stage
from lightman.schema import (
    AnalysisManifest,
    Event,
    MediaInfo,
    OutputArtifact,
    QualitySummary,
)

log = get_logger(__name__)

DISCLAIMER = (
    "Lightman measures observable behavior and reports deviations from a subject-specific "
    "baseline. It does not detect lies, read minds, or establish intent. Deviations can arise "
    "from stress, cognitive load, humor, discomfort, lighting, camera motion, or chance. "
    "Independent project; not affiliated with any television series or its rights holders."
)

LandmarkerFactory = Callable[[LightmanConfig, ModelRegistry], FaceLandmarker]
AUDetectorFactory = Callable[[LightmanConfig, ModelRegistry], AUDetector]
VADFactory = Callable[[LightmanConfig, ModelRegistry], "SileroVAD"]


@dataclass(slots=True)
class AnalysisResult:
    session_id: str
    session_dir: Path
    manifest: AnalysisManifest
    baseline: BaselineSnapshot
    events: list[Event]
    summary: dict[str, Any]
    audio: AudioStageResult | None = None


def default_landmarker_factory(cfg: LightmanConfig, registry: ModelRegistry) -> FaceLandmarker:
    from lightman.face.mediapipe_backend import MediaPipeFaceLandmarker

    model_id = "mediapipe/face_landmarker"
    path = registry.ensure(model_id)
    return MediaPipeFaceLandmarker(
        path,
        model_sha256=registry.get(model_id).sha256,
        max_faces=cfg.video.max_faces,
        min_face_detection_confidence=cfg.video.min_face_detection_confidence,
        min_face_presence_confidence=cfg.video.min_face_presence_confidence,
        min_tracking_confidence=cfg.video.min_tracking_confidence,
    )


def default_au_factory(cfg: LightmanConfig, registry: ModelRegistry) -> AUDetector:
    from lightman.face.opengraphau_onnx import OpenGraphAUOnnx

    path = registry.ensure(cfg.au.model)
    return OpenGraphAUOnnx(
        path,
        model_id=cfg.au.model,
        model_sha256=registry.get(cfg.au.model).sha256,
        prefer_gpu=cfg.au.prefer_gpu,
    )


def _new_session_id() -> str:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"{stamp}-{secrets.token_hex(3)}"


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False), "utf-8")


def _nan_to_none(obj: Any) -> Any:
    if isinstance(obj, float):
        return None if not math.isfinite(obj) else obj
    if isinstance(obj, dict):
        return {k: _nan_to_none(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_nan_to_none(v) for v in obj]
    return obj


def _artifact(path: Path, kind: str) -> OutputArtifact:
    return OutputArtifact(
        name=path.name, kind=kind, size_bytes=path.stat().st_size, sha256=sha256_file(path)
    )


def extract_frames_at(
    path: Path, wanted_us: Iterable[int], limits: MediaLimits, *, tolerance_us: int
) -> dict[int, npt.NDArray[np.uint8]]:
    """Second sequential pass returning the nearest frame for each wanted timestamp."""
    targets = sorted(set(wanted_us))
    if not targets:
        return {}
    out: dict[int, npt.NDArray[np.uint8]] = {}
    i = 0
    for fr in iter_video_frames(path, limits=limits):
        while i < len(targets) and fr.t_us >= targets[i] - tolerance_us:
            if abs(fr.t_us - targets[i]) <= tolerance_us:
                out[targets[i]] = fr.rgb
            i += 1
        if i >= len(targets):
            break
    return out


def _save_thumbnail(
    rgb: npt.NDArray[np.uint8],
    bbox: tuple[float, float, float, float] | None,
    dest: Path,
    max_px: int,
) -> None:
    import cv2

    h, w = rgb.shape[:2]
    if bbox and all(math.isfinite(v) for v in bbox):
        x0, y0, x1, y1 = bbox
        bw, bh = (x1 - x0) * w, (y1 - y0) * h
        cx, cy = (x0 + x1) / 2 * w, (y0 + y1) / 2 * h
        half = max(bw, bh) * 0.75
        xa, xb = int(max(0, cx - half)), int(min(w, cx + half))
        ya, yb = int(max(0, cy - half)), int(min(h, cy + half))
        crop = rgb[ya:yb, xa:xb]
    else:
        crop = rgb
    if crop.size == 0:
        crop = rgb
    scale = max_px / max(crop.shape[:2])
    if scale < 1:
        crop = np.asarray(
            cv2.resize(crop, (int(crop.shape[1] * scale), int(crop.shape[0] * scale))),
            dtype=np.uint8,
        )
    cv2.imwrite(str(dest), cv2.cvtColor(crop, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 82])


def analyze_video(
    media_path: Path,
    out_dir: Path,
    cfg: LightmanConfig | None = None,
    *,
    landmarker_factory: LandmarkerFactory | None = None,
    au_factory: AUDetectorFactory | None = None,
    vad_factory: VADFactory | None = None,
    registry: ModelRegistry | None = None,
    subject_id: str = "subject_001",
) -> AnalysisResult:
    cfg = cfg or LightmanConfig()
    registry = registry or ModelRegistry(
        cache_dir=cfg.models.cache_dir, allow_download=cfg.models.allow_download
    )
    factory = landmarker_factory or default_landmarker_factory
    timing: dict[str, float] = {}
    t0 = time.perf_counter()

    session_id = _new_session_id()
    session_dir = out_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=False)
    log.info("session_created", session_id=session_id)

    # ---- probe
    media: MediaInfo = probe_media(media_path, cfg.limits)
    if not media.has_video:
        raise UnsupportedMediaError("no video stream; audio-only analysis arrives in a later phase")
    vstream = media.video_streams[0]
    timing["probe_ms"] = (time.perf_counter() - t0) * 1000
    log.info(
        "media_probed",
        container=media.container_format,
        codec=vstream.codec,
        size=f"{vstream.width}x{vstream.height}",
        fps=vstream.average_fps,
        duration_s=(media.duration_us or 0) / 1e6,
        has_audio=media.has_audio,
    )

    # ---- landmarker
    t1 = time.perf_counter()
    landmarker = factory(cfg, registry)
    au_detector: AUDetector | None = None
    if cfg.au.enabled:
        au_detector = (au_factory or default_au_factory)(cfg, registry)
    timing["model_load_ms"] = (time.perf_counter() - t1) * 1000

    # ---- decode + features
    builder = FeatureTableBuilder()
    t2 = time.perf_counter()
    infer_ms: list[float] = []
    au_ms: list[float] = []
    au_frames = 0
    origin_us: int | None = None
    try:
        for fr in iter_video_frames(media_path, target_fps=cfg.video.target_fps, limits=cfg.limits):
            if origin_us is None:
                origin_us = fr.container_t_us - fr.t_us
            h, w = fr.rgb.shape[:2]
            ti = time.perf_counter()
            faces = landmarker.process(fr.rgb, fr.t_us)
            infer_ms.append((time.perf_counter() - ti) * 1000)
            if faces:
                face = faces[0]  # V0.1: first face only; multi-face tracking is a later phase
                bbox = face.bbox_normalized()
                width_px = (bbox[2] - bbox[0]) * w
                head = None
                yaw = pitch = None
                if face.transform is not None:
                    hp = head_pose_from_matrix(face.transform)
                    head = (hp.yaw_deg, hp.pitch_deg, hp.roll_deg, hp.tx, hp.ty, hp.tz)
                    yaw, pitch = hp.yaw_deg, hp.pitch_deg
                ear_r, ear_l = eye_aspect_ratios(face.landmarks, w, h)
                ear_mean = float(np.nanmean([ear_r, ear_l]))
                aus = None
                if (
                    au_detector is not None
                    and fr.index % cfg.au.stride == 0
                    and width_px >= cfg.au.min_face_px
                ):
                    ta = time.perf_counter()
                    aus = au_detector.process(
                        fr.rgb, (bbox[0] * w, bbox[1] * h, bbox[2] * w, bbox[3] * h)
                    )
                    au_ms.append((time.perf_counter() - ta) * 1000)
                    au_frames += 1
                builder.add_frame(
                    frame_index=fr.index,
                    source_index=fr.source_index,
                    t_us=fr.t_us,
                    timestamp_estimated=fr.timestamp_estimated,
                    face_count=len(faces),
                    quality=face_quality(width_px, yaw, pitch),
                    bbox=bbox,
                    face_width_px=width_px,
                    head=head,
                    eyes=(ear_r, ear_l, ear_mean),
                    blendshapes=face.blendshapes,
                    aus=aus,
                )
            else:
                builder.add_frame(
                    frame_index=fr.index,
                    source_index=fr.source_index,
                    t_us=fr.t_us,
                    timestamp_estimated=fr.timestamp_estimated,
                    face_count=0,
                    quality=0.0,
                    bbox=None,
                    face_width_px=0.0,
                    head=None,
                    eyes=None,
                    blendshapes=None,
                )
    finally:
        landmarker.close()
        if au_detector is not None:
            au_detector.close()
    timing["decode_and_landmarks_ms"] = (time.perf_counter() - t2) * 1000
    cols = builder.to_numpy()
    n_frames = len(builder)
    log.info(
        "features_extracted",
        frames=n_frames,
        frames_with_face=int(cols["face_present"].sum()),
        mean_infer_ms=round(float(np.mean(infer_ms)), 2) if infer_ms else None,
        au_frames=au_frames,
        mean_au_ms=round(float(np.mean(au_ms)), 2) if au_ms else None,
    )

    # ---- audio (before the baseline: speech segments define the speaking state)
    audio: AudioStageResult | None = None
    if cfg.audio.enabled and media.has_audio:
        ta = time.perf_counter()
        try:
            vad = vad_factory(cfg, registry) if vad_factory else None
            audio = run_audio_stage(
                media_path,
                cfg=cfg,
                registry=registry,
                origin_us=origin_us or 0,
                subject_id=subject_id,
                event_id_start=500_000,
                vad=vad,
            )
        except LightmanError as exc:
            log.warning("audio_stage_failed", error=str(exc))
        timing["audio_ms"] = (time.perf_counter() - ta) * 1000

    # ---- baseline
    t3 = time.perf_counter()
    t_us = cols["t_us"].astype(np.int64)
    quality = cols["quality"].astype(np.float64)
    signals: dict[str, npt.NDArray[np.floating]] = {
        name: cols[name].astype(np.float64) for name in SIGNAL_COLUMNS
    }
    for name in AU_COLUMNS:  # classifier outputs jitter frame to frame; smooth before scoring
        signals[name] = median_smooth(signals[name])
    speaking_mask: npt.NDArray[np.bool_] | None = None
    frame_state: npt.NDArray[np.str_] | None = None
    if audio is not None and audio.segments:
        speaking_mask = np.zeros(t_us.shape, dtype=bool)
        for seg in audio.segments:
            speaking_mask |= (t_us >= seg.start_us) & (t_us < seg.end_us)
    if speaking_mask is not None:
        cols["speaking"] = speaking_mask
        builder.set_column("speaking", speaking_mask)
    state_baselines = compute_state_baselines(t_us, quality, signals, cfg.baseline, speaking_mask)
    baseline = state_baselines[STATE_ALL]
    if speaking_mask is not None:
        frame_state = np.where(speaking_mask, STATE_SPEAKING, STATE_SILENT).astype(str)
        if STATE_SPEAKING not in state_baselines:
            frame_state = None  # not enough speech in the window: fall back to 'all'
    timing["baseline_ms"] = (time.perf_counter() - t3) * 1000

    # ---- events
    t4 = time.perf_counter()
    prov = landmarker.provenance
    blinks = detect_blinks(
        t_us=t_us,
        quality=quality,
        ear=signals["eye.aspect_ratio_mean"],
        baseline=baseline,
        cfg=cfg.events,
        subject_id=subject_id,
        extractor_id=prov.extractor_id,
        id_start=0,
    )
    deviations = detect_deviation_events(
        t_us=t_us,
        quality=quality,
        signals=signals,
        baseline=baseline,
        cfg=cfg.events,
        subject_id=subject_id,
        extractor_id=prov.extractor_id,
        id_start=len(blinks),
        exclude_intervals=[(b.start_us, b.end_us) for b in blinks],
        state_baselines=state_baselines if frame_state is not None else None,
        frame_state=frame_state,
    )
    clusters = cluster_cooccurring(
        deviations,
        subject_id=subject_id,
        extractor_id=prov.extractor_id,
        id_start=len(blinks) + len(deviations),
    )
    warmup_us = cfg.events.warmup_ms * 1000
    events = sorted(
        (e for e in blinks + deviations + clusters if e.start_us >= warmup_us),
        key=lambda e: (e.start_us, e.event_id),
    )
    if audio is not None:
        speech = [(sg.start_us, sg.end_us) for sg in audio.segments]

        def _in_speech(e: Event) -> bool:
            return any(e.start_us < b and e.end_us > a for a, b in speech)

        # Only tag when no speaking-state baseline exists; with one, speech is scored fairly.
        if frame_state is None:
            events = [tag_speaking(e) if _in_speech(e) else e for e in events]
        events = sorted(
            events + [e for e in audio.events if e.start_us >= warmup_us],
            key=lambda e: (e.start_us, e.event_id),
        )
    timing["events_ms"] = (time.perf_counter() - t4) * 1000

    # ---- summary
    face_frames = int(cols["face_present"].sum())
    coverage = face_frames / n_frames if n_frames else 0.0
    face_time_s = 0.0
    if n_frames:
        period_s = float(np.median(np.diff(t_us))) / 1e6 if n_frames > 1 else 0.0
        face_time_s = face_frames * period_s
    blink_count = sum(1 for e in events if e.event_type == "blink")
    q_present = quality[cols["face_present"]]
    notes: list[str] = list(baseline.notes)
    if coverage < 0.5:
        notes.append(f"face visible in only {coverage:.0%} of frames")
    if any(cols["timestamp_estimated"]):
        notes.append("some frame timestamps were reconstructed from the nominal frame rate")
    if audio is not None and audio.quality["speech_fraction"] < 0.05:
        notes.append("little or no speech detected; audio baseline unreliable")
    if cfg.audio.enabled and not media.has_audio:
        notes.append("no audio stream; audio analysis skipped")
    quality_summary = QualitySummary(
        frames_total=n_frames,
        frames_decoded=n_frames,
        frames_with_face=face_frames,
        face_coverage=coverage,
        mean_face_quality=float(q_present.mean()) if q_present.size else None,
        baseline_quality=baseline.quality,
        baseline_window_us=(baseline.window_start_us, baseline.window_end_us),
        notes=notes,
    )
    summary: dict[str, Any] = {
        "session_id": session_id,
        "subject_id": subject_id,
        "duration_us": int(t_us[-1]) if n_frames else 0,
        "frames_analyzed": n_frames,
        "face_coverage": coverage,
        "blink_count": blink_count,
        "blink_rate_per_min": (blink_count / (face_time_s / 60)) if face_time_s > 0 else None,
        "audio": (
            {
                "speech_segments": len(audio.segments),
                "speech_fraction": audio.quality["speech_fraction"],
                "snr_db": audio.quality["snr_db"],
                "clipping_fraction": audio.quality["clipping_fraction"],
                "baseline_quality": audio.baseline.quality,
                "timing_ms": audio.timing_ms,
            }
            if audio is not None
            else None
        ),
        "baseline_states": {
            k: {"frames_used": v.frames_used, "quality": v.quality}
            for k, v in state_baselines.items()
        },
        "event_counts": {
            k: sum(1 for e in events if e.event_type == k)
            for k in sorted({e.event_type for e in events})
        },
        "inference_ms_per_frame": {
            "mean": float(np.mean(infer_ms)) if infer_ms else None,
            "p50": float(np.percentile(infer_ms, 50)) if infer_ms else None,
            "p95": float(np.percentile(infer_ms, 95)) if infer_ms else None,
        },
        "au_inference_ms_per_frame": {
            "frames": au_frames,
            "mean": float(np.mean(au_ms)) if au_ms else None,
            "p50": float(np.percentile(au_ms, 50)) if au_ms else None,
            "p95": float(np.percentile(au_ms, 95)) if au_ms else None,
        },
        "signals": {
            name: {
                "baseline_center": sb.center,
                "baseline_scale": sb.scale,
                "n": sb.n,
                "unit": sb.unit,
            }
            for name, sb in baseline.signals.items()
        },
    }

    # ---- outputs
    t5 = time.perf_counter()
    outputs: list[OutputArtifact] = []
    meta_path = session_dir / "metadata.json"
    _write_json(meta_path, media.model_dump(mode="json"))
    outputs.append(_artifact(meta_path, "json"))

    feat_path = session_dir / "features.parquet"
    builder.write_parquet(feat_path)
    outputs.append(_artifact(feat_path, "parquet"))

    base_path = session_dir / "baseline.json"
    _write_json(base_path, _nan_to_none(baseline.model_dump(mode="json")))
    outputs.append(_artifact(base_path, "json"))
    if len(state_baselines) > 1:
        sb_path = session_dir / "state_baselines.json"
        _write_json(
            sb_path,
            {k: _nan_to_none(v.model_dump(mode="json")) for k, v in state_baselines.items()},
        )
        outputs.append(_artifact(sb_path, "json"))

    if audio is not None:
        af_path = session_dir / "audio_features.parquet"
        audio.write_frame_table(af_path)
        outputs.append(_artifact(af_path, "parquet"))
        seg_path = session_dir / "speech_segments.json"
        _write_json(seg_path, audio.segments_json())
        outputs.append(_artifact(seg_path, "json"))
        ab_path = session_dir / "audio_baseline.json"
        _write_json(ab_path, _nan_to_none(audio.baseline.model_dump(mode="json")))
        outputs.append(_artifact(ab_path, "json"))

    events_path = session_dir / "events.json"
    _write_json(
        events_path,
        {"schema_version": 1, "events": [_nan_to_none(e.model_dump(mode="json")) for e in events]},
    )
    outputs.append(_artifact(events_path, "json"))

    thumbs: dict[str, Path] = {}
    if cfg.storage.event_thumbnails and events:
        peak_by_event = {e.event_id: e.peak_us for e in events if e.peak_us is not None}
        # Only thumbnail the most informative events to bound disk usage.
        interesting = [e for e in events if e.event_type != "blink"][:200]
        wanted = {peak_by_event[e.event_id] for e in interesting if e.event_id in peak_by_event}
        period_us = int(np.median(np.diff(t_us))) if n_frames > 1 else 40_000
        frames = extract_frames_at(media_path, wanted, cfg.limits, tolerance_us=period_us)
        tdir = session_dir / "thumbnails"
        tdir.mkdir(exist_ok=True)
        idx_by_t = {int(t): i for i, t in enumerate(t_us)}
        for e in interesting:
            pk = peak_by_event.get(e.event_id)
            if pk is None or pk not in frames:
                continue
            i = idx_by_t.get(pk)
            thumb_bbox: tuple[float, float, float, float] | None = None
            if i is not None and bool(cols["face_present"][i]):
                thumb_bbox = (
                    float(cols["face.bbox_x0"][i]),
                    float(cols["face.bbox_y0"][i]),
                    float(cols["face.bbox_x1"][i]),
                    float(cols["face.bbox_y1"][i]),
                )
            dest = tdir / f"{e.event_id}.jpg"
            _save_thumbnail(frames[pk], thumb_bbox, dest, cfg.storage.thumbnail_max_px)
            thumbs[e.event_id] = dest
    timing["outputs_ms"] = (time.perf_counter() - t5) * 1000

    analysis_path = session_dir / "analysis.json"
    summary["timing_ms"] = timing
    _write_json(analysis_path, _nan_to_none(summary))
    outputs.append(_artifact(analysis_path, "json"))

    if cfg.storage.write_report:
        from lightman.report.html import render_report

        report_path = session_dir / "report.html"
        render_report(
            dest=report_path,
            media=media,
            summary=summary,
            quality=quality_summary,
            baseline=baseline,
            events=events,
            table=cols,
            thumbnails=thumbs,
            disclaimer=DISCLAIMER,
            signals_to_plot=cfg.events.signals,
            audio=audio,
        )
        outputs.append(_artifact(report_path, "html"))

    timing["total_ms"] = (time.perf_counter() - t0) * 1000
    manifest = AnalysisManifest(
        session_id=session_id,
        subject_ids=[subject_id],
        created_utc=utc_now_iso(),
        lightman_version=__version__,
        media=media,
        config=cfg.snapshot(),
        environment=snapshot_environment(),
        provenance=[prov]
        + ([au_detector.provenance] if au_detector is not None else [])
        + ([audio.provenance] if audio is not None else []),
        quality=quality_summary,
        outputs=outputs,
        timing_ms={k: round(v, 2) for k, v in timing.items()},
        disclaimer=DISCLAIMER,
    )
    _write_json(session_dir / "manifest.json", _nan_to_none(manifest.model_dump(mode="json")))
    log.info(
        "session_complete",
        session_id=session_id,
        events=len(events),
        total_ms=round(timing["total_ms"]),
    )
    return AnalysisResult(
        session_id=session_id,
        session_dir=session_dir,
        manifest=manifest,
        baseline=baseline,
        events=events,
        summary=summary,
        audio=audio,
    )


__all__ = ["DISCLAIMER", "AnalysisResult", "analyze_video"]
