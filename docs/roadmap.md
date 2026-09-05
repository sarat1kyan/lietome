# Roadmap

Phases are ordered by dependency and by how much scientific ground they stand on. Each phase
ends with tests, measurements, and a project-state update.

| Phase | Scope | Status |
|---|---|---|
| 0 | Research, architecture, toolchain, licensing, scaffolding | done (2026-09-05) |
| 1 | Media ingestion: probe, limits, PTS-exact decode, rotation, VFR | done |
| 2 | Single-face prerecorded video: landmarks, blendshapes, head pose, EAR, quality, Parquet | done |
| 3 | Facial features & timeline: AU backend (OpenGraphAU behind `AUDetector`, done), gaze proxy, optical-flow motion energy, camera-motion compensation, richer report | in progress |
| 4 | Baseline modeling: anchored+adaptive windows, change-point detection (ruptures), question-aware segments, baseline reliability calibration | next |
| 5 | Audio: PyAV audio decode, Silero VAD, F0/energy/rate/pauses (librosa), approximate jitter/shimmer, audio quality (SNR, clipping), audio events on the shared us time base | done (first slice) |
| 6 | Speech: faster-whisper / whisper.cpp ASR (opt-in), word timings, response latency to questions, disfluencies; any language-model step optional and isolated from feature extraction | planned |
| 7 | Multimodal: event-level co-occurrence across modalities, uncertainty-aware confidence, missing-modality handling | planned |
| 8 | Microexpression spotting research track: dataset adapters (licensed), LOSO/cross-dataset evaluation harness, optical strain baseline, TCN/transformer experiments | research |
| 9 | Live webcam: bounded queues, drop-oldest, incremental baseline, WebSocket event stream | planned |
| 10 | Live call/screen capture sources | planned |
| 11 | Investigative frontend: Svelte 5 + Vite + TypeScript, custom design system, video-dominant layout, timeline scrubber, evidence panel | planned |
| 12 | Training/fine-tuning only after 8's evaluation harness is credible | research |

Cross-cutting, continuous: Docker image and Windows/macOS/Linux CI, privacy modes (no-retention, metadata-only), security hardening
(decoder isolation), benchmarks on RTX 3060 Ti and Apple Silicon, ONNX packaging of any
PyTorch model, API (FastAPI) once there is more than one consumer.

## Explicitly not planned

A deception score, "truth" score, or any per-person verdict. See scientific-limitations.md.
