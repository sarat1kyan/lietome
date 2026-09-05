# Project state

Last updated: 2026-09-05 (session 2: AU backend, audio stage, Docker, live mode). Facts only.

## Phase

Phase 0 (research/architecture), 1 (media ingestion), 2 (single-face prerecorded analysis)
complete; Phase 3 started (AU backend); Phase 5 first slice done (audio). Version `0.1.0a0`. Model assets
published as release `models-v1` on the repository; no package release.

## Working

* `lightman probe <file>` - container/stream metadata as JSON.
* `lightman analyze <video> -o out/ [--fps N] [--config cfg.toml] [--no-report] [--no-thumbnails]`
  -> `out/<session_id>/{metadata,baseline,events,analysis,manifest}.json`, `features.parquet`,
  `report.html`, `thumbnails/`.
* `lightman models list|download|verify|import`, `lightman doctor`.
* Media: PyAV probe/decode, PTS-exact us timestamps, VFR, display rotation, time-based
  subsampling, hostile-input limits (size, duration, pixels, frames, streams).
* Face: MediaPipe Face Landmarker backend (478 landmarks, 52 blendshapes, transform), first face.
* Audio: PyAV 16 kHz decode aligned to the video origin; Silero VAD v6 (ONNX); pyin F0,
  RMS energy, voicing and speech probability per 20 ms frame (`audio_features.parquet`);
  speech segments with pause-before, F0 median/spread (semitones), syllable-rate proxy,
  approximate jitter/shimmer (`speech_segments.json`); speech-only baseline
  (`audio_baseline.json`); `voice.f0_hz` / `voice.energy_db` deviation events (source
  "audio") and `speech_pause` events; audio quality (SNR, clipping, speech fraction); report
  section. `[audio]` config.
* Docker image (python:3.12-slim + uv, non-root, face model baked in), built in CI.
* Live mode (`lightman live`): webcam or real-time file replay, capture thread + queue(2,
  drop oldest), streaming baseline/deviation/blink detectors verified against the offline
  ones, console + labelled preview window, same session outputs. Video only.
* Action Units: OpenGraphAU stage-2 via onnxruntime (`AUDetector` protocol; resnet50 default,
  resnet18 fast), 41 `au.*` columns, AU deviation events labelled with FACS names. `[au]`
  config: enabled, model, stride, prefer_gpu, min_face_px. `lightman[cuda]` extra.
* Features: head pose (Euler), EAR (left/right/mean), blendshape columns, face bbox/width,
  quality heuristic -> Parquet (zstd).
* Baseline: leading-window robust median / 1.4826,MAD with unit floors, reliability score, notes.
* Events: blinks / eye closures (subject-relative EAR threshold), per-signal deviation events
  with hysteresis + min duration + merge gap, co-occurrence clusters (INTERPRETATION), warm-up
  filter. SPECULATION level is rejected by the schema.
* Report: self-contained HTML, SD-unit timelines with baseline shading and event spans, ranked
  events with contributors and thumbnails, quality panel, disclaimer.
* Tests: 62 (unit + fake-backend pipeline + real-model integration marked `model`), all passing
  on macOS arm64 / Python 3.12. ruff and mypy --strict clean. CI green on ubuntu/macos/windows
  x 3.12/3.13 (PR #1).

## Important decisions (see docs/adr/)

Python >=3.12 + uv/ruff/mypy/pytest , MediaPipe first backend , pinned model manifest , integer
us time base , Apache-2.0 , robust leading-window baseline , PyAV, no shell FFmpeg.

## Known limitations / issues

* **`mediapipe==1.0.1` aborts on macOS arm64** (`TensorsToDetectionsCalculator` ->
  `DrishtiMetalHelper`, "Check failed: service_ Service is unavailable") for IMAGE and VIDEO
  modes, with and without `Delegate.CPU`. 1.0.0 and 0.10.35 work. Pinned `!=1.0.1`. Not yet
  reported upstream (no matching issue found via `gh search`). Linux behavior untested.
* Blendshapes != AUs; blendshape AU hints stay "(proxy)". OpenGraphAU outputs are occurrence
  probabilities from research-dataset training, unvalidated on our footage; resnet18 hedges
  near 0.5 on the fixture where resnet50 is confident. Left/right AU variants least reliable.
* AU resnet50 costs ~88 ms/frame CPU in the pipeline (20 s clip -> 58 s). Use `au.stride`,
  resnet18, or CUDA. GPU path (onnxruntime-gpu) not yet exercised.
* Swin-Tiny stage-2 export was not completed (script produced no output); not offered.
* Live: no microphone/audio yet; baseline frozen after calibration; camera access could not
  be validated on the development machine (terminal lacks camera permission), only file replay.
* Audio: no diarization (multiple speakers pool into one baseline), no ASR, no question/answer
  timing (response latency), jitter/shimmer are frame-track approximations, first pyin call
  costs ~25 s of numba JIT per process. Only validated on synthesized speech and tones.
* Head-pose yaw/pitch sign conventions vs. camera not verified on real footage (only the
  mathematical round-trip is tested). Deviation logic is sign-agnostic so results are unaffected.
* Near-constant signals hit the scale floor -> over-sensitive 3SD events on static content
  (observed: `mouthPressRight` on a still portrait). Flagged in baseline/report; better floors
  or a minimum-variance gate are needed.
* Baseline window = first 30 s of the recording; no question-aware or adaptive baseline yet.
* Single face only; no audio; no speech; no live mode.
* Quality heuristic covers size and pose only (no blur/illumination/occlusion).
* Thumbnails are JPEG (q82, 256 px) embedded base64 in the report.
* `storage.store_landmarks` exists in config but landmark persistence is not implemented.
* PyAV and OpenCV each bundle FFmpeg; macOS prints objc duplicate-class warnings at import.
  No functional impact observed.
* Only tested with H.264/AAC in MP4/MOV and synthetic clips; no real interview footage yet.

## Benchmarks

See docs/benchmarks.md. M5 Pro CPU: 3.4-3.8 ms/frame landmarker; 20 s clip end-to-end 3.45 s.

## Next work (proposed order)

1. Validate on real single-person footage (user-provided or CC-licensed interview): check head
   pose signs, blink detection precision, event plausibility; tune floors/thresholds; record.
2. Phase 3 continued: AU temporal smoothing (probabilities jitter frame to frame), fp16/int8
   ONNX quantization, CUDA benchmark on the RTX 3060 Ti, camera-motion compensation.
3. Live audio (sounddevice capture -> streaming VAD/F0) and a WebSocket event stream.
4. Camera-motion compensation / global motion energy so pans and zooms do not read as behavior.
5. Phase 6: ASR (faster-whisper / whisper.cpp, opt-in), word timings, turn structure and
   response latency; diarization (pyannote, opt-in) or simple speaker clustering.
5. Report/UI: click-to-seek video with landmark overlay (needs a small JS player; keep it
   self-contained).
6. Run CI on GitHub once a remote exists (user decision); add Linux + CUDA benchmarks on the
   RTX 3060 Ti machine.

## Maintainer decisions (2026-09-05)

* Test footage: the maintainer and consenting friends. Recordings stay local and out of Git.
* Platforms: Windows, macOS and Linux are all V1 targets. Windows added to the CI matrix;
  not yet run locally.
* Docker: supported install path (to add; roadmap).
* Frontend (Phase 11): Svelte 5 + Vite + TypeScript SPA served by the API, hand-written CSS
  design system (no component kits), canvas/WebGL for timelines. Chosen for small runtime,
  fast fine-grained updates during scrubbing, and full control of the visual language.
  ADR to follow when the phase starts.
