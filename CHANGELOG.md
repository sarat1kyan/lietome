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
