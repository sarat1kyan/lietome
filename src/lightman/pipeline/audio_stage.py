"""Audio stage of the prerecorded pipeline: VAD -> frame features -> segments -> baseline -> events.

Runs after the video stage and shares its time origin (container time of the first analyzed
video frame) so audio and video events line up on one ``t_us`` axis.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pyarrow as pa
import pyarrow.parquet as pq

from lightman.audio.features import (
    FrameFeatures,
    SegmentFeatures,
    audio_quality,
    compute_frame_features,
    compute_segment_features,
)
from lightman.audio.vad import (
    CHUNK,
    CHUNK_US,
    SileroVAD,
    SpeechSegment,
    segments_from_probabilities,
)
from lightman.baseline import BaselineSnapshot, compute_leading_window_baseline
from lightman.config import LightmanConfig
from lightman.core.logging import get_logger
from lightman.events.deviation import detect_deviation_events
from lightman.media.audio import load_audio_mono
from lightman.models import ModelRegistry
from lightman.schema import Event, EvidenceLevel, Provenance
from lightman.schema.events import FeatureContribution

log = get_logger(__name__)

VAD_MODEL_ID = "silero/vad_v6"
AUDIO_SIGNAL_COLUMNS: tuple[str, ...] = (
    "voice.f0_hz",
    "voice.energy_db",
    "voice.voiced_prob",
    "voice.speech_prob",
)


@dataclass(slots=True)
class AudioStageResult:
    frames: FrameFeatures
    segments: list[SpeechSegment]
    segment_features: list[SegmentFeatures]
    baseline: BaselineSnapshot
    events: list[Event]
    quality: dict[str, float]
    provenance: Provenance
    timing_ms: dict[str, float]

    def frame_table(self) -> pa.Table:
        return pa.table(
            {
                "t_us": pa.array(self.frames.t_us),
                "voice.f0_hz": pa.array(self.frames.f0_hz.astype(np.float32)),
                "voice.energy_db": pa.array(self.frames.energy_db.astype(np.float32)),
                "voice.voiced_prob": pa.array(self.frames.voiced_prob.astype(np.float32)),
                "voice.speech_prob": pa.array(self.frames.speech_prob.astype(np.float32)),
            }
        )

    def write_frame_table(self, path: Path) -> None:
        pq.write_table(self.frame_table(), path, compression="zstd")

    def segments_json(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "segments": [
                {
                    k: (None if isinstance(v, float) and not math.isfinite(v) else v)
                    for k, v in asdict(sf).items()
                }
                for sf in self.segment_features
            ],
        }


def _pause_events(
    segs: list[SegmentFeatures],
    *,
    cfg: LightmanConfig,
    subject_id: str,
    extractor_id: str,
    id_start: int,
) -> list[Event]:
    """Within-speech gaps longer than ``audio.long_pause_ms`` (OBSERVATION)."""
    out: list[Event] = []
    k = id_start
    for prev, cur in itertools.pairwise(segs):
        gap_ms = cur.pause_before_ms or 0.0
        if gap_ms < cfg.audio.long_pause_ms:
            continue
        out.append(
            Event(
                event_id=f"ev_{k:05d}",
                subject_id=subject_id,
                source="audio",
                event_type="speech_pause",
                level=EvidenceLevel.OBSERVATION,
                start_us=prev.end_us,
                end_us=cur.start_us,
                peak_us=prev.end_us,
                label=f"speech pause {gap_ms / 1000:.1f} s",
                description=f"No detected speech for {gap_ms:.0f} ms between two speech segments",
                contributions=[
                    FeatureContribution(
                        feature="speech.pause_ms",
                        unit="ms",
                        peak_value=gap_ms,
                        baseline_center=0.0,
                        baseline_scale=0.0,
                        peak_deviation=0.0,
                        direction="increase",
                    )
                ],
                severity=gap_ms / 1000,
                confidence=min(1.0, prev.voiced_fraction + 0.5),
                quality=1.0,
                baseline_quality=0.0,
                extractor_id=extractor_id,
                tags=["speech"],
            )
        )
        k += 1
    return out


def run_audio_stage(
    media_path: Path,
    *,
    cfg: LightmanConfig,
    registry: ModelRegistry,
    origin_us: int,
    subject_id: str,
    event_id_start: int,
    vad: SileroVAD | None = None,
) -> AudioStageResult:
    import time

    timing: dict[str, float] = {}
    t0 = time.perf_counter()
    samples, first_us = load_audio_mono(media_path, limits=cfg.limits)
    timing["audio_decode_ms"] = (time.perf_counter() - t0) * 1000
    audio_origin = first_us - origin_us  # audio time relative to the video origin

    t1 = time.perf_counter()
    own_vad = vad is None
    if vad is None:
        path = registry.ensure(VAD_MODEL_ID)
        vad = SileroVAD(path, model_id=VAD_MODEL_ID, model_sha256=registry.get(VAD_MODEL_ID).sha256)
    probs = vad.probabilities(samples)
    if own_vad:
        vad.close()
    timing["vad_ms"] = (time.perf_counter() - t1) * 1000
    segments = segments_from_probabilities(
        probs,
        origin_us=audio_origin,
        threshold=cfg.audio.vad_threshold,
        min_speech_ms=cfg.audio.min_speech_ms,
        min_silence_ms=cfg.audio.min_silence_ms,
    )

    t2 = time.perf_counter()
    frames = compute_frame_features(
        samples,
        origin_us=audio_origin,
        speech_probs=probs,
        chunk_us=CHUNK_US,
        f0_min=cfg.audio.f0_min_hz,
        f0_max=cfg.audio.f0_max_hz,
    )
    seg_feats = compute_segment_features(frames, segments)
    quality = audio_quality(samples, probs, CHUNK)
    timing["audio_features_ms"] = (time.perf_counter() - t2) * 1000

    # Baseline and events over *voiced speech* frames only: silence and unvoiced consonant
    # gaps would otherwise dominate energy/F0 statistics and produce spurious "loudness drops".
    speech_mask = (frames.speech_prob >= cfg.audio.vad_threshold) & (
        frames.voiced_prob >= cfg.audio.voiced_prob_min
    )
    frame_quality: npt.NDArray[np.float64] = np.where(speech_mask, 1.0, 0.0)
    signals: dict[str, npt.NDArray[np.floating]] = {
        "voice.f0_hz": frames.f0_hz,
        "voice.energy_db": frames.energy_db,
    }
    baseline = compute_leading_window_baseline(frames.t_us, frame_quality, signals, cfg.baseline)
    if not segments:
        baseline = baseline.model_copy(update={"notes": [*baseline.notes, "no speech detected"]})

    prov = vad.provenance
    events = detect_deviation_events(
        t_us=frames.t_us,
        quality=frame_quality,
        signals=signals,
        baseline=baseline,
        cfg=cfg.events.model_copy(
            update={"signals": cfg.audio.signals, "min_duration_ms": cfg.audio.min_event_ms}
        ),
        subject_id=subject_id,
        extractor_id=prov.extractor_id,
        id_start=event_id_start,
        source="audio",
    )
    events += _pause_events(
        seg_feats,
        cfg=cfg,
        subject_id=subject_id,
        extractor_id=prov.extractor_id,
        id_start=event_id_start + len(events),
    )
    log.info(
        "audio_stage_complete",
        seconds=round(samples.size / 16000, 1),
        speech_segments=len(segments),
        speech_fraction=round(quality["speech_fraction"], 3),
        events=len(events),
    )
    return AudioStageResult(
        frames=frames,
        segments=segments,
        segment_features=seg_feats,
        baseline=baseline,
        events=events,
        quality=quality,
        provenance=prov,
        timing_ms=timing,
    )
