# Changelog

All notable changes are recorded here. Format follows Keep a Changelog; versions follow SemVer.

## [Unreleased]

### Added
- Expression prototypes with exclusion AUs: social smile, brow flash, lip press, brow furrow;
  Duchenne vs lip-corner smile counts in the narrative (ADR-018).
- Per-signal event rules: entry thresholds for gaze, head speed and articulation signals,
  longer minimum duration for gaze and head speed; most specific prefix wins.
- Live sessions write audio_features.parquet and audio_baseline.json; pitch cue evaluated live.
- GET /api/sessions/{id}/frame: all signals at the nearest frame with the state baseline.
- Sessions view: frame readout at the playhead (AU bars with FACS names and z, pattern meter,
  head pose, gaze, eye opening).
- Live self-view overlays: AU bars, pattern meter, head axes, gaze arrow, blink and speech
  indicators, event flashes; toggle in the toolbar.
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
- Expression pattern events from FACS prototypes (brief tag under 500 ms) and a
  deception-research cue checklist with effect sizes per session and per question (ADR-017).
- Interview protocol mode: question script, timestamped markers over the live WebSocket,
  protocol.json with per-question summaries, category comparison and experimental AUROC;
  protocol table and timeline spans in the UI; narrative lines (ADR-016).
- Network serving: token + self-signed TLS when bound off localhost (ADR-015).
- New signals: gaze proxy, brow/smile asymmetry, head speed; blur and luminance in frame
  quality; blink-rate change events; plain-language session narrative in analysis.json,
  report and UI; live lanes in SD units fed by the adaptive baseline; summary card with top
  contributors; keyboard scrubbing (arrows, j/k).
- Bounded adaptive baseline after calibration (ADR-014): EWMA center/scale per state,
  anchored to the calibration, offline and live.
- Calibration v2: 40 s window with a free-talk phase; per-frame `speaking` column in
  features.parquet; per-group entry thresholds (AU and blendshape 4 SD); blink suppression for
  eye-region blendshapes live and partial-overlap blink exclusion offline; replay tool
  rebuilds state baselines from the speaking column.
- Guided live calibration: 12 s settle + 18 s reading a fixed neutral passage, on-screen
  countdown, baseline-ready summary with per-state frame counts (docs/calibration.md).
- Speaking/silent state baselines (ADR-013) and 5-frame median smoothing of AU probabilities;
  `state_baselines.json`; audio stage runs before the video baseline.
- Baseline scale: measured floors, trimmed-SD fallback for degenerate MAD; live episodes
  (grouped deviations); "speaking" tag on mouth-region events during speech;
  `experiments/replay_events.py` to re-run detection on saved features.
- Browser live tab: getUserMedia capture streamed over `WS /api/live`, shared LiveAnalyzer,
  streaming audio analyzer (VAD + YIN, voiced-gated baseline), landmark overlay, event feed.
- `lightman live`: webcam or real-time file replay, bounded drop-oldest queue, streaming
  baseline/detectors, console and preview sinks, same session outputs.
