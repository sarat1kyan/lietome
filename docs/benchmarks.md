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

## End-to-end `lightman analyze` (probe -> decode -> landmarks -> features -> baseline -> events -> outputs)

Sample: 20 s, 30 fps, 640x480 H.264 + AAC (synthetic pan/zoom over the licensed portrait).

| Machine | Total | Decode+landmarks | Model load | Outputs (thumbnails, report) | Realtime factor |
|---|---|---|---|---|---|
| Apple M5 Pro, AU disabled | 3.45 s | 2.73 s (600 frames -> 4.6 ms/frame incl. decode) | 0.37 s | 0.29 s | ~ 5.8x faster than real time |
| Apple M5 Pro, AU resnet18 | 17.7 s | 16.6 s | 0.72 s | 0.37 s | ~ 1.1x real time |
| Apple M5 Pro, AU resnet50 (default) | 58.2 s | 57.1 s | 0.63 s | 0.38 s | ~ 0.34x real time |

Command: `uv run lightman analyze samples/portrait_kenburns_20s.mp4 -o output/` (timings in
`analysis.json -> timing_ms`).

## Not yet measured

CUDA/RTX 3060 Ti anything; end-to-end at 1080p/4K; memory footprint over long recordings;
audio pipeline (does not exist yet); live-mode latency/backpressure.
