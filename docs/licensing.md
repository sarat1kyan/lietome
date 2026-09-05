# Licensing

Lightman is Apache-2.0 (ADR-005). Every third-party component is recorded here with the
decision. **Rule:** research-only / non-commercial code, weights, or datasets never ship in the
core package or its default download manifest.

## Runtime dependencies (core)

| Package | License | Notes |
|---|---|---|
| numpy | BSD-3 | |
| av (PyAV) 18 | BSD-3 | Bundles FFmpeg (LGPL build in wheels). |
| mediapipe 1.0.0 | Apache-2.0 | Code + Face Landmarker model bundle (BlazeFace, FaceMesh-V2, Blendshape-V2) are Apache-2.0 per model cards. Pulls opencv-contrib-python, matplotlib, sounddevice, absl-py, flatbuffers. |
| opencv-contrib-python | Apache-2.0 | Contrib modules included by mediapipe's dependency; we use only core imgproc/imgcodecs. |
| pydantic 2 | MIT | |
| typer | MIT | (rich: MIT, click: BSD-3) |
| structlog | MIT / Apache-2.0 | |
| pyarrow | Apache-2.0 | |
| jinja2 | BSD-3 | |
| platformdirs | MIT | |
| httpx | BSD-3 | |
| onnxruntime | MIT | CPU by default; `lightman[cuda]` swaps in onnxruntime-gpu on Linux/Windows |

Dev tools (pytest MIT, hypothesis MPL-2.0, ruff MIT, mypy MIT, pre-commit MIT, pip-audit
Apache-2.0) are not distributed.

## Models

| Model | Code | Weights | Decision |
|---|---|---|---|
| MediaPipe Face Landmarker | Apache-2.0 | Apache-2.0 | **Accepted** (default backend). |
| OpenGraphAU / ME-GraphAU (CVI-SZU) | Apache-2.0 | Apache-2.0 (repo LICENSE) | **Accepted** as AU backend (ADR-008). Stage-2 ResNet-50 and ResNet-18 checkpoints converted to ONNX and redistributed under Apache-2.0 with NOTICE at github.com/sarat1kyan/lietome/releases/tag/models-v1. Trained on BP4D, DISFA, RAF-AU, Aff-Wild2, CK+, CASME II (research-licensed datasets). Dataset terms bind the trainers, not (by their text) downstream users of the weights; legally untested, recorded as a risk. Outputs unvalidated on this project's footage. |
| Py-Feat 2.x | MIT | Mixed; per-model licenses linked from repo LICENSE | **Candidate**. Each model must be checked individually before use. |
| OpenFace 2.x (Baltrusaitis) | Academic, non-commercial | same | **Rejected** for core. |
| OpenFace 3.0 (CMU) | "Academic or non-profit noncommercial research use only" | same | **Rejected** for core. |
| LibreFace 1.x/2.0 (USC IHP) | USC research license, non-commercial | same | **Rejected** for core. |
| InsightFace (RetinaFace/ArcFace packs) | MIT (code) | Non-commercial research only | **Rejected** for core. Could be an opt-in plugin the user installs. |
| RetinaFace re-implementations (yakhyo, biubug6, serengil) | MIT | Trained on WIDER FACE (research dataset) | **Candidate** if a separate detector is ever needed; same dataset caveat as above. |
| L2CS-Net (gaze) | MIT | Unspecified; trained on Gaze360 / MPIIFaceGaze | **Hold**. Weights license not stated. |
| ETH-XGaze | CC BY-NC-SA 4.0 | same | **Rejected** for core. |
| openSMILE | audEERING dual license, non-commercial for open version | - | **Rejected** for core. |
| Whisper / faster-whisper / whisper.cpp | MIT | MIT | **Accepted for Phase 6** (ASR). |
| Silero VAD | MIT | MIT | **Accepted for Phase 5**. |
| pyannote.audio 3.x / community-1 | MIT | MIT (gated download on Hugging Face) | **Acceptable, opt-in** (requires user's HF token; never auto-download). |
| librosa | ISC | - | Accepted for Phase 5. |
| torchaudio / PyTorch | BSD-3 | - | Accepted when needed. |
| praat-parselmouth | GPL-3.0-or-later | - | **Not in core** (GPL would bind the whole distribution). Possible optional extra with clear notice, or re-implement jitter/shimmer natively. |
| ruptures | BSD-2 | - | Accepted for change-point detection (note: currently declares `<3.14`). |

## Datasets

See `docs/datasets.md`. All microexpression and AU datasets found (CASME II, SAMM, SMIC,
CAS(ME)3, 4DME, MMEW, BP4D, DISFA) require signed research license agreements and forbid
redistribution. They may be used for evaluation/training research by licensed researchers; no
data or derived per-sample artifacts may be committed. Deception datasets (Real-life Trial,
Bag-of-Lies, MU3D, Box-of-Lies, DOLOS) likewise require agreements; MU3D is free for research.

## Test fixtures

`tests/fixtures/portrait_mediapipe_apache2.jpg` is MediaPipe's test asset
(`storage.googleapis.com/mediapipe-assets/portrait.jpg`), Apache-2.0.

## Process

Before adding anything: check code license, weight license, dataset terms, redistribution and
attribution requirements; add a row here; if in doubt, keep it out of the default install.
