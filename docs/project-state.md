# Project state

Last updated: 2026-09-05 (session 3: browser live capture, four real webcam sessions, adaptive baseline). Facts only.

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
* Web UI: `lightman serve` (FastAPI on 127.0.0.1:8710, read-only session endpoints, upload
  + analyze job, static SPA) and `frontend/` (Svelte 5 + Vite + TS): session rail, video stage
  with local-file playback, canvas timeline (SD lanes, event strip, playhead), evidence panel,
  quality strip. Demo single-file build. API tests with TestClient.
* Browser live tab: WS /api/live, LiveAnalyzer shared with the CLI, StreamingAudioAnalyzer
  (Silero VAD + single-window YIN, voiced-gated baseline, voice deviation events), landmark
  overlay, readouts, rolling lanes, event feed, session saved on stop. Tested with fake models
  over the WebSocket; first real webcam run happened on the maintainer's machine via the CLI.
* Guided calibration in the live tab (settle 12 s, read passage 18 s) with phase hints to the
  server and a baseline-ready summary; protocol in docs/calibration.md.
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

## Findings from the first real webcam sessions (2026-09-06)

* Pipeline held both times: 13.3-13.4 fps analyzed, 0 drops, 21-23 ms inference/latency,
  audio events fired, sessions saved and opened in the UI.
* MAD scale collapsed on zero-inflated blendshapes (resting jawOpen MAD 0.004 vs SD 0.12):
  expressions read 50-80 SD. Fixed with floors measured on the calibration window and a
  trimmed-SD fallback when the MAD is degenerate (ADR-006 amendment). Replay: max severity
  81 -> 38; count unchanged (real motion).
* Speaking dominated mouth signals (123 of 310, then nearly all of 252 events). Now:
  speaking/silent state baselines from VAD when the window has both (ADR-013), otherwise a
  "speaking" tag with halved confidence. Calibration instruction: sit quietly AND talk.
* AU probabilities jitter frame to frame (AU4 0.11-0.49 on a calm face): 5-frame median.
* Live had no grouping: StreamingEpisodes groups overlapping deviations into episodes; the UI
  lists episodes first.
* Session 3 (3:18 conversation after guided calibration): 381 deviations/min, 25 episodes/min.
  61/70 eye events and 131/165 squint events overlapped blinks (live path lacked the offline
  blink exclusion, fixed); reading-only speaking baseline did not represent conversation
  (jawOpen p90 0.03 vs 0.20), so calibration v2 adds a 14 s free-talk phase (40 s total).
  AU/blendshape entry thresholds raised to 4 SD.
* Session 4 (3:11 with calibration v2): 268 deviations/min, 29 episodes/min; conversation
  range far wider than the speaking calibration (browInnerUp p90 0.08 vs 0.61). Bounded
  adaptive baseline added (ADR-014): replay 336 -> 133/min (session 4), 381 -> 117/min
  (session 3). Remaining rate is dominated by jaw/brow motion during animated speech.

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
* Web UI: no auth (localhost only), no live view, no multi-session comparison, no keyboard
  shortcuts; only checked via demo build and API tests, not yet through a browser session.
* Live: CLI path has no microphone; browser path has audio but no jitter/shimmer/segments; baseline frozen after calibration; camera access could not
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
3. Interview protocol mode: question markers, per-question deviation summaries, response
   latency, control-vs-relevant comparison, ground-truth harness (per-person AUROC with CIs).
   Never a lie label.
4. Measure a conversation with the adaptive baseline; tune bounds/half-life via
   experiments/replay_events.py on stored sessions.
5. Adaptive (anchored, bounded) baseline; UI keyboard scrubbing; session comparison.
5. Camera-motion compensation / global motion energy so pans and zooms do not read as behavior.
6. Phase 6: ASR (faster-whisper / whisper.cpp, opt-in), word timings, turn structure and
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
