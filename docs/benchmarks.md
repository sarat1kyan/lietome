# Benchmarks

All numbers are measured, not estimated. Re-run with the commands shown; add rows for new
machines rather than overwriting.

## Face landmarker (MediaPipe Face Landmarker, CPU/XNNPACK, blendshapes + transform on)

`uv run python experiments/bench_face_landmarker.py 300` - landmarker only, decode excluded,
one face present (letterboxed portrait), VIDEO mode, 300 frames after 10 warm-up frames.

| Machine | Runtime | 640x480 | 1280x720 | 1920x1080 |
|---|---|---|---|---|
| Apple M5 Pro (18 cores, 24 GB), macOS 27, Python 3.12, mediapipe 1.0.0 | CPU | 3.44 ms (p95 3.57) | 3.52 ms (p95 3.65) | 3.77 ms (p95 3.90) |
| Intel i5-12400F + RTX 3060 Ti | - | not yet measured | | |

Resolution barely matters: the detector runs on a 192x192 downscale and the mesh on a 256x256
crop; the extra cost at 1080p is mostly image conversion.

## Action Unit detector (OpenGraphAU stage-2, ONNX Runtime, 224x224 crop)

Isolated single-image timings (scratch script, 10 iterations after warm-up) and in-pipeline
means from `analysis.json -> au_inference_ms_per_frame` on the 20 s sample.

| Machine | Model | ORT CPU isolated | ORT CPU in pipeline | torch CPU | torch MPS | ORT CoreML |
|---|---|---|---|---|---|---|
| Apple M5 Pro | resnet50_s2 (143 MB) | 67.5 ms | 88.0 ms (p95 108) | 136-145 ms | 29.4 ms | 122 ms |
| Apple M5 Pro | resnet18_s2 (48 MB) | 17.0 ms | 20.4 ms (p95 24) | 40.6 ms | 10.9 ms | 40.9 ms |
| RTX 3060 Ti | both | not yet measured (CUDA EP) | | | | |

## Audio (16 kHz mono, M5 Pro CPU)

| Component | Input | Time | Notes |
|---|---|---|---|
| Silero VAD v6 ONNX | 5.6 s speech (176 chunks) | 12 ms | 0.002x real time, single thread |
| librosa pyin (hop 20 ms, frame 64 ms, 60-400 Hz) | 3 s | 36 ms steady state; ~25 s first call | first call is numba JIT compilation |
| librosa yin (same) | 3 s | 3 ms | no voicing decision; kept as a future live-mode option |

pyin accuracy on a synthetic 90-150 Hz glide: median error 0.28 Hz, p95 0.70 Hz; 0/29
pause frames marked voiced. yin: 0.18 Hz median but marks silence as voiced.

## End-to-end `lightman analyze` (probe -> decode -> landmarks -> features -> baseline -> events -> outputs)

Sample: 20 s, 30 fps, 640x480 H.264 + AAC (synthetic pan/zoom over the licensed portrait).

| Machine | Total | Decode+landmarks | Model load | Outputs (thumbnails, report) | Realtime factor |
|---|---|---|---|---|---|
| Apple M5 Pro, AU disabled | 3.45 s | 2.73 s (600 frames -> 4.6 ms/frame incl. decode) | 0.37 s | 0.29 s | ~ 5.8x faster than real time |
| Apple M5 Pro, AU resnet18 | 17.7 s | 16.6 s | 0.72 s | 0.37 s | ~ 1.1x real time |
| Apple M5 Pro, AU resnet50 (default) | 58.2 s | 57.1 s | 0.63 s | 0.38 s | ~ 0.34x real time |

Audio stage on a 17 s clip with synthesized speech (same machine): decode 18 ms, VAD 57 ms,
frame features (pyin) 1.43 s, total audio stage ~1.5 s (0.09x real time) after the JIT warm-up.

Command: `uv run lightman analyze samples/portrait_kenburns_20s.mp4 -o output/` (timings in
`analysis.json -> timing_ms`).

## Live mode (file replay at real-time pace, 640x480 @ 30 fps, M5 Pro CPU, 12 s)

| Configuration | Analyzed fps | Latency p50 / p95 | Dropped | Inference p50 |
|---|---|---|---|---|
| landmarks + blendshapes | 30.0 | 7.3 / 8.6 ms | 0 / 361 | 7.2 ms |
| + AU resnet18 | 29.9 | 19.3 / 20.7 ms | 0 / 361 | 19.2 ms |
| + AU resnet50 | 14.4 | 121 / 137 ms | 186 / 362 | 68 ms |

Latency = capture to end of analysis; the queue (size 2) keeps it bounded when the model is
slower than the frame period, at the cost of dropped frames.

## First real webcam sessions (browser live tab, M5 Pro, 2026-09-06)

Session 1: 99 s, 640 px frames at 15 fps client target: 1321 frames analyzed, 13.3 fps, 0
dropped, inference p50 21 ms (landmarks + AU resnet18), 25 blinks, 3 voice events. Baseline
used 400 frames (quality 0.67). MAD-only scale: 310 deviation events in 69 s, max severity
81 SD. Replayed with measured floors and the trimmed-SD fallback: 313 events, max 38 SD, 32
episodes (the count is real motion of an expressive subject; the SD inflation was the bug).

Session 2: 79 s, 13.4 fps, latency p50 23 ms (receive to analyzed), 0 dropped, 9 blinks:
252 deviations, 17 episodes, nearly all tagged speaking; AU4 spanned 0.11-0.49 on a calm
face. Motivated ADR-013 (state baselines, AU smoothing).

Session 3: 3 min 18 s, guided calibration (12 s quiet + 18 s reading), then free conversation:
2635 frames, 13.3 fps, latency 23 ms, 0 dropped, 78 blinks, 12 voice events, two-state baseline
(silent 207 / speaking 194 frames). 1070 deviations (381/min), 69 episodes (25/min). Of 70
eye-openness events 61 overlapped a blink; of 165 eyeSquint events 131 did (live path lacked
blink exclusion). Calibration jawOpen p90 0.03 vs 0.20 in conversation: reading is not
talking. Led to the free-talk phase, per-group thresholds and blink suppression for eye-region
signals.

Session 4: 3 min 11 s with calibration v2 (quiet, read, free talk) then conversation: 2535
frames, 13.3 fps, 23 ms latency, 0 dropped, 63 blinks, 17 voice events, baseline quality 0.88
(silent 241 / speaking 289 frames). 675 deviations (268/min), 72 episodes. Conversation
range far exceeded the speaking calibration sample (browInnerUp p90 0.08 vs 0.61, AU1 0.33 vs
0.82, jawOpen 0.05 vs 0.18). Led to ADR-014 (bounded adaptive baseline). Replayed with the adaptive baseline: 335
deviations (133/min), 58 episodes, max severity 29 SD; session 3 replayed: 117/min.

## Not yet measured

CUDA/RTX 3060 Ti anything; end-to-end at 1080p/4K; memory footprint over long recordings;
audio pipeline (does not exist yet); live-mode latency/backpressure.
