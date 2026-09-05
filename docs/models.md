# Models

Assets are declared in `src/lightman/models/manifest.json` and managed by
`lightman.models.ModelRegistry`. Nothing is committed to Git.

## Manifest fields

`filename, url, sha256, size_bytes, task, runtime, license, source, input, output, notes`.
`sha256` and `size_bytes` are mandatory and enforced.

## Cache

Default: `platformdirs.user_cache_dir("lightman")/models/<id-with-__>/<filename>`
(macOS: `~/Library/Caches/lightman/models`). Override with `LIGHTMAN_MODEL_DIR` or
`[models] cache_dir` in config. `allow_download = false` makes the registry refuse network
access; use `lightman models import <id> <file>` for air-gapped installs.

## Current assets

### mediapipe/face_landmarker

* Bundle of three TFLite models + geometry metadata (unzip the `.task` to inspect):
  `face_detector.tflite` (BlazeFace short-range, 192x192), `face_landmarks_detector.tflite`
  (FaceMesh-V2, 256x256, 478 points), `face_blendshapes.tflite` (52 coefficients).
* SHA-256 `64184e22...bc9ff`, 3,758,596 bytes. The upstream URL says "latest" but the bundled
  files are dated 2023-05-03; if Google republishes, our pin will fail verification loudly,
  which is the intended behavior. A versioned URL should replace "latest" when one is confirmed.
* Runtime: MediaPipe Tasks (XNNPACK CPU delegate). GPU delegate on macOS aborts (unsupported
  ImageFrame format); not used.
* Measured: 3.4-3.6 ms/frame at 640x480 on Apple M5 Pro CPU (see benchmarks).
* Known issue: `mediapipe==1.0.1` macOS arm64 wheel aborts in `TensorsToDetectionsCalculator`
  (`DrishtiMetalHelper`, "Service is unavailable") for every configuration tested. 1.0.0 and
  0.10.35 work. Pinned `!=1.0.1`.

## Planned

* An AU detector behind a new `AUDetector` interface (OpenGraphAU or a Py-Feat model), exported to
  ONNX where possible so one runtime (onnxruntime with CPU/CUDA/CoreML providers) serves all
  machines. Adoption requires: license row, hash pin, and a measured comparison against
  blendshape proxies on FACS-coded data we are licensed to use.
