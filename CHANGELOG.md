# Changelog

All notable changes are recorded here. Format follows Keep a Changelog; versions follow SemVer.

## [Unreleased]

### Added
- Project foundations: uv/ruff/mypy/pytest toolchain, Apache-2.0 license, CI.
- Media ingestion with PyAV: probing, safety limits, PTS-accurate decoding, rotation, VFR.
- Model registry with SHA-256-pinned manifest and verified download/import.
- MediaPipe Face Landmarker backend (478 landmarks, 52 blendshapes, head transform).
- Per-frame features: head pose, eye aspect ratio, blendshapes, quality heuristic.
- Leading-window robust baseline (median / scaled MAD) and robust z-scores.
- Events: blinks, per-signal baseline deviations, co-occurrence clusters.
- `lightman analyze` writing metadata/features/baseline/events/analysis/manifest + HTML report.
- Action Unit detector: OpenGraphAU stage-2 (ResNet-50 default, ResNet-18 fast) via ONNX
  Runtime behind an `AUDetector` protocol; 41 `au.*` feature columns; AU deviation events.
- `lightman[cuda]` extra (onnxruntime-gpu) for NVIDIA machines.
- Audio stage: PyAV 16 kHz decode aligned to the video clock, Silero VAD (ONNX), pyin F0,
  energy, speech segments with pause/rate/jitter-approx features, speech-only baseline,
  voice deviation and pause events, `audio_features.parquet`, `speech_segments.json`,
  report section.
- Dockerfile and CI image build.
- Web UI: `lightman serve` (FastAPI, localhost) + Svelte 5 workstation (session rail, video
  stage with local playback, canvas timeline in robust-SD units, evidence panel, quality
  strip); upload-and-analyze endpoint; single-file demo build.
- Browser live tab: getUserMedia capture streamed over `WS /api/live`, shared LiveAnalyzer,
  streaming audio analyzer (VAD + YIN, voiced-gated baseline), landmark overlay, event feed.
- `lightman live`: webcam or real-time file replay, bounded drop-oldest queue, streaming
  baseline/detectors, console and preview sinks, same session outputs.
