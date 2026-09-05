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

### opengraphau/resnet50_s2 and opengraphau/resnet18_s2

* OpenGraphAU (Luo et al., IJCAI 2022; github.com/lingjivoo/OpenGraphAU) stage-2 MEFL models:
  ResNet backbone -> 27 per-AU linear blocks -> edge-feature GNN -> 41 sigmoid outputs
  (27 AUs + left/right variants of AU1, 2, 4, 6, 10, 12, 14).
* Converted to ONNX (opset 17) with `experiments/export_opengraphau_onnx.py`; checkpoint loaded
  with `weights_only=True`; ONNX output matches PyTorch to <1e-6. Hosted as release assets on
  this repository (`models-v1`) with NOTICE and upstream LICENSE; SHA-256 pinned in the
  manifest. Original checkpoint hashes are recorded in the manifest notes.
* Preprocessing (from upstream `image_eval`): square crop, margin 1.3 around the landmark box,
  resize to 256, center crop 224, ImageNet normalization. Margin sweep 1.0-1.6 changed mean
  probability by <0.06 on the fixture; 2.0 by 0.10.
* Measured on Apple M5 Pro, onnxruntime 1.29 CPU: resnet50 67 ms/frame isolated, ~88 ms
  inside the pipeline (shares cores with decode and MediaPipe); resnet18 17 ms isolated,
  ~20 ms in pipeline. CoreML EP is slower than CPU (partial partitioning); torch MPS was
  29 ms / 11 ms but torch is not a Lightman dependency. CUDA not yet measured.
* Quality note: on the smiling fixture resnet50 gives AU6 0.92, AU7 0.95, AU10 0.95, AU12 0.96,
  AU25 0.98 (a Duchenne smile with parted lips); resnet18 hedges near 0.5 on the same AUs.
  Default is resnet50; resnet18 is for live/low-power use.
* Upstream demo.py imports the stage-1 (ANFL) class for every checkpoint; stage-2 weights only
  load cleanly into `model.MEFL.MEFARG` (strict load verified). Documented so nobody repeats it.
* Not a facial-expression or emotion classifier. Outputs are occurrence probabilities, not
  FACS intensities (A-E).

### silero/vad_v6

* Silero VAD v6.2.1, `silero_vad.onnx` from the tagged upstream repository (MIT), 2.3 MB.
  Stateful: 512-sample chunks at 16 kHz with 64 samples of context prepended, state (2,1,128).
  Measured: 5.6 s of speech in 12 ms on M5 Pro CPU (0.002x real time). On synthesized speech
  87% of chunks scored > 0.5; on Gaussian noise the maximum was 0.06.
* Our wrapper (`audio/vad.py`) reproduces the upstream framing; using the raw model without the
  context window silently yields ~0 everywhere (found the hard way; tested).

## Planned

* AU intensity (not just occurrence) and a measured comparison of OpenGraphAU vs blendshape
  proxies on FACS-coded data we are licensed to use.
* fp16 / int8 quantization of the ONNX exports (143 MB and 48 MB today).
