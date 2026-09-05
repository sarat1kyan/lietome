# Project state

Last updated: 2026-09-05 (end of first session). Facts only.

## Phase

Phase 0 (research/architecture), 1 (media ingestion), and 2 (single-face prerecorded analysis)
are complete as a first vertical slice. Version `0.1.0a0`. Nothing released.

## Working

* `lightman probe <file>` - container/stream metadata as JSON.
* `lightman analyze <video> -o out/ [--fps N] [--config cfg.toml] [--no-report] [--no-thumbnails]`
  -> `out/<session_id>/{metadata,baseline,events,analysis,manifest}.json`, `features.parquet`,
  `report.html`, `thumbnails/`.
* `lightman models list|download|verify|import`, `lightman doctor`.
* Media: PyAV probe/decode, PTS-exact us timestamps, VFR, display rotation, time-based
  subsampling, hostile-input limits (size, duration, pixels, frames, streams).
* Face: MediaPipe Face Landmarker backend (478 landmarks, 52 blendshapes, transform), first face.
* Features: head pose (Euler), EAR (left/right/mean), blendshape columns, face bbox/width,
  quality heuristic -> Parquet (zstd).
* Baseline: leading-window robust median / 1.4826,MAD with unit floors, reliability score, notes.
* Events: blinks / eye closures (subject-relative EAR threshold), per-signal deviation events
  with hysteresis + min duration + merge gap, co-occurrence clusters (INTERPRETATION), warm-up
  filter. SPECULATION level is rejected by the schema.
* Report: self-contained HTML, SD-unit timelines with baseline shading and event spans, ranked
  events with contributors and thumbnails, quality panel, disclaimer.
* Tests: 55 (unit + fake-backend pipeline + real-model integration marked `model`), all passing
  on macOS arm64 / Python 3.12. ruff and mypy --strict clean. CI workflow written (not yet run
  on GitHub - no remote).

## Important decisions (see docs/adr/)

Python >=3.12 + uv/ruff/mypy/pytest , MediaPipe first backend , pinned model manifest , integer
us time base , Apache-2.0 , robust leading-window baseline , PyAV, no shell FFmpeg.

## Known limitations / issues

* **`mediapipe==1.0.1` aborts on macOS arm64** (`TensorsToDetectionsCalculator` ->
  `DrishtiMetalHelper`, "Check failed: service_ Service is unavailable") for IMAGE and VIDEO
  modes, with and without `Delegate.CPU`. 1.0.0 and 0.10.35 work. Pinned `!=1.0.1`. Not yet
  reported upstream (no matching issue found via `gh search`). Linux behavior untested.
* Blendshapes != AUs; AU hints are "(proxy)". No validated AU model yet.
* Head-pose yaw/pitch sign conventions vs. camera not verified on real footage (only the
  mathematical round-trip is tested). Deviation logic is sign-agnostic so results are unaffected.
* Near-constant signals hit the scale floor -> over-sensitive 3SD events on static content
  (observed: `mouthPressRight` on a still portrait). Flagged in baseline/report; better floors
  or a minimum-variance gate are needed.
* Baseline window = first 30 s of the recording; no question-aware or adaptive baseline yet.
* Single face only; no audio; no speech; no live mode.
* Quality heuristic covers size and pose only (no blur/illumination/occlusion).
* Thumbnails are PNG (~100 KB each at 256 px); report embeds them base64 (~0.7 MB for 3).
* `storage.store_landmarks` exists in config but landmark persistence is not implemented.
* PyAV and OpenCV each bundle FFmpeg; macOS prints objc duplicate-class warnings at import.
  No functional impact observed.
* Only tested with H.264/AAC in MP4/MOV and synthetic clips; no real interview footage yet.

## Benchmarks

See docs/benchmarks.md. M5 Pro CPU: 3.4-3.8 ms/frame landmarker; 20 s clip end-to-end 3.45 s.

## Next work (proposed order)

1. Validate on real single-person footage (user-provided or CC-licensed interview): check head
   pose signs, blink detection precision, event plausibility; tune floors/thresholds; record.
2. Phase 3: `AUDetector` interface; evaluate OpenGraphAU (Apache-2.0) vs Py-Feat AU models
   against blendshape proxies; ONNX export; license rows; benchmark on both machines.
3. Camera-motion compensation / global motion energy so pans and zooms do not read as behavior.
4. Phase 5 audio: PyAV audio decode -> Silero VAD -> F0/energy/rate/pauses -> audio events on the
   shared time base.
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
