# ADR-008 Action Unit backend: OpenGraphAU via ONNX Runtime

**Context.** Blendshapes are animation coefficients; Lightman needs FACS Action Units from a
model trained on FACS-coded data, usable commercially, runnable on CPU, CUDA and Apple
Silicon without adding PyTorch as a runtime dependency.

**Decision.** Add an `AUDetector` protocol (`face/au_base.py`) and implement it with
OpenGraphAU stage-2 (MEFL) models exported to ONNX and run through onnxruntime. Two assets:
ResNet-50 (default, quality) and ResNet-18 (fast). Exports are reproducible with
`experiments/export_opengraphau_onnx.py` and hosted as hash-pinned release assets with NOTICE.
AU probabilities become `au.AUxx` feature columns, take part in baseline deviation events with
unit "probability" (scale floor 0.02), and are labelled with FACS names, not emotions.

**Rejected.** OpenFace 3.0 and LibreFace (non-commercial licenses). Py-Feat (per-model licenses
unclear; heavier dependency surface). Running the PyTorch checkpoint directly (torch as a hard
dependency; pickle loading). CoreML execution provider (slower than CPU for this graph).

**Consequences.** ~88 ms/frame CPU for resnet50 inside the pipeline: a 20 s clip takes ~1 min
on M5 Pro. `au.stride` and the resnet18 model trade accuracy for speed. Weights are trained on
research datasets; see licensing.md for the recorded risk. Values are occurrence probabilities,
not intensities; no validation on our footage yet.
