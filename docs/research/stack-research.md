# Stack research (Phase 0, 2026-09-05)

Findings that drove the first architecture. Each row was checked against primary sources
(PyPI JSON, repository LICENSE files, model cards, papers) on the date above; several were
verified empirically on the development machine (Apple M5 Pro, macOS 27, Python 3.12).

## Runtime / packaging

| Question | Finding | Evidence |
|---|---|---|
| Python version | 3.12 primary, 3.13 in CI. 3.14 resolves for all core deps on macOS arm64 but CUDA/PyTorch coverage on 3.14 was still uneven; MediaPipe 1.0 ships `py3-none` wheels (ctypes C API) so it is version-agnostic. | `uv pip install --dry-run` on 3.12/3.13/3.14; PyPI file lists for torch 2.14.0, onnxruntime 1.29.0 (cp311-cp314), mediapipe 1.0.1 (py3-none, 5 platforms) |
| Env/lock | `uv` (fast, lockfile, Python management). Poetry also present but slower and no Python management. | local tooling |
| Lint/type/test | ruff (lint+format), mypy `--strict` with pydantic plugin, pytest + hypothesis | - |

## Face analysis

| Candidate | Result |
|---|---|
| **MediaPipe Face Landmarker** | Apache-2.0 code and models. 478 landmarks, 52 blendshapes, 4x4 transform, tracked VIDEO mode. Measured 3.4-3.6 ms/frame CPU on M5 Pro (640x480). **Chosen for V0.1.** Regression: 1.0.1 macOS wheel aborts (`DrishtiMetalHelper`, "Service is unavailable") in every configuration incl. `Delegate.CPU`; 1.0.0 and 0.10.35 fine. |
| OpenFace 2.x | Non-commercial academic license. Rejected. |
| OpenFace 3.0 (CMU, FG 2025) | RetinaFace + STAR + multitask AU/gaze/emotion. LICENSE: "academic or non-profit organization noncommercial research use only". Rejected for core. |
| LibreFace 1/2 (USC, WACV 2024 / FG 2026) | 12 DISFA AUs intensity + detection, ONNX, MediaPipe alignment. USC research license (non-commercial). Rejected for core. |
| OpenGraphAU (CVI-SZU, IJCAI 2022 lineage) | Apache-2.0 code + weights; 41 AUs incl. unilateral; ResNet/Swin/MobileNetV3 backbones; trained on ~2M images from BP4D/DISFA/RAF-AU/Aff-Wild2/CK+/CASME II. Reported hybrid-set F1 only ~22-24 (accuracy ~92% is imbalance-inflated); per-dataset BP4D/DISFA numbers from the ME-GraphAU paper are ~65 F1 (BP4D). **Leading AU candidate**, must be validated before adoption. |
| Py-Feat 2.1.1 | MIT, py>=3.11, torch>=2.5, weights on HF hub, "respect individual model licenses". **Candidate**, per-model license check required. |
| InsightFace | Code MIT, all model packs non-commercial. Rejected for core. |
| RetinaFace (MIT re-implementations) | Fine as detector if needed; WIDER FACE training-data caveat. Not needed while MediaPipe's BlazeFace suffices. |
| Gaze: L2CS-Net (MIT code, weights unspecified), ETH-XGaze (CC BY-NC-SA) | Hold / reject. V0.1 uses iris-related blendshapes (`eyeLook*`) as gaze proxies only. |
| Blendshape vs AU on the fixture | MediaPipe `browDownLeft/Right` = 0.84/0.82 on a broad smile while OpenGraphAU AU4 = 0.35; `eyeSquint` 0.74 vs AU7 0.95; `mouthSmile` 0.96 vs AU12 0.96. Proxies agree on the smile, disagree on the brow. One image, but it shows why proxies stay labelled. |
| Blendshape<->AU validity | Only mapping found (Blendshape features meet action units, 2026) is expert-consensus, not empirically validated. Hence "(proxy)". |

## Microexpressions

MEGC 2025 (ACM MM) spot-then-recognize: STRS ~ 0.0062 (SAMM), ~ 0.0086 (CAS(ME)3); spotting is
the bottleneck. Datasets require signed agreements (see datasets.md). Decision: research track,
LOSO/cross-dataset evaluation, no product claims.

## Audio / speech (for Phases 5-6)

| Component | License | Decision |
|---|---|---|
| librosa 1.0 | ISC | features (F0 via pyin, energy, spectral) |
| torchaudio | BSD-3 | when torch is present |
| Silero VAD 6.x | MIT | VAD |
| faster-whisper 1.2 / whisper.cpp | MIT | ASR; whisper.cpp for Apple Metal/CoreML, faster-whisper for CUDA batch |
| pyannote 3.x / community-1 | MIT, gated | opt-in diarization |
| openSMILE | non-commercial | rejected |
| praat-parselmouth | GPL-3 | not in core |
| Voice stress analysis | chance-level for deception across reviews (NRC etc.) | measure prosody as observations only |

## Baseline / temporal (for Phase 4)

Robust z (median, 1.4826,MAD) chosen for V0.1: resistant to window contamination, unit-free,
interpretable. `ruptures` (BSD-2) for offline change-point detection later. Online variants
(EWMA/rolling median, Page-Hinkley/CUSUM) for live mode. Learned anomaly detectors deferred until
there is data to validate them on.

## License for Lightman

Apache-2.0: explicit patent grant and retaliation clause (relevant in ML), compatible with
MIT/BSD deps and with Apache-2.0 model weights, permissive for downstream research and
commercial use, standard in the ML ecosystem. MIT lacks the patent grant; GPL/AGPL would block
combining with many permissively-licensed but GPL-incompatible components and deter adoption.
See ADR-005.

## Sources

* MediaPipe Face Landmarker guide and model cards: https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker
* mediapipe PyPI: https://pypi.org/project/mediapipe/ ; releases: https://github.com/google-ai-edge/mediapipe/releases
* PyTorch releases: https://github.com/pytorch/pytorch/releases ; Python 3.14 tracking: https://github.com/pytorch/pytorch/issues/156856
* onnxruntime releases: https://github.com/microsoft/onnxruntime/releases
* OpenFace 3.0: https://github.com/CMU-MultiComp-Lab/OpenFace-3.0 (LICENSE), arXiv:2506.02891
* LibreFace: https://github.com/ihp-lab/LibreFace , arXiv:2308.10713
* OpenGraphAU / ME-GraphAU: https://github.com/CVI-SZU/ME-GraphAU , https://github.com/lingjivoo/OpenGraphAU
* Py-Feat: https://py-feat.org/ , https://github.com/cosanlab/py-feat , arXiv:2104.03509
* InsightFace license: https://github.com/deepinsight/insightface , https://github.com/deepinsight/insightface/issues/2587
* RetinaFace impls: https://github.com/yakhyo/retinaface-pytorch , https://github.com/biubug6/Pytorch_Retinaface , https://github.com/serengil/retinaface
* L2CS-Net: https://github.com/Ahmednull/L2CS-Net ; ETH-XGaze: https://github.com/xucong-zhang/ETH-XGaze
* Blendshape-AU mapping study (2026): https://www.sciencedirect.com/science/article/pii/S2451958826001995
* MEGC 2025: https://doi.org/10.1145/3746027.3762065 ; MEGC 2026: https://arxiv.org/abs/2603.08927
* CASME II: http://casme.psych.ac.cn/casme/e2 ; awesome-MER list: https://github.com/Vision-Intelligence-and-Robots-Group/awesome-micro-expression-recognition
* CAS(ME)3: https://ieeexplore.ieee.org/document/9774929 ; 4DME: https://ieeexplore.ieee.org/document/9796028
* Deception datasets / cross-domain benchmark: https://arxiv.org/abs/2405.06995 ; SVC 2025: https://arxiv.org/abs/2508.04129 ; SVC 2026: https://arxiv.org/abs/2604.05748
* Voice stress analysis evidence: https://pubmed.ncbi.nlm.nih.gov/7047675/ ; https://www.sciencedaily.com/releases/2004/02/040211080041.htm
* openSMILE license: https://github.com/audeering/opensmile/blob/master/LICENSE
* Parselmouth license: https://github.com/YannickJadoul/Parselmouth/blob/master/LICENSE
* pyannote: https://huggingface.co/pyannote/speaker-diarization-3.1
* Whisper family: https://github.com/openai/whisper , https://github.com/ggml-org/whisper.cpp
* ruptures: https://github.com/deepcharles/ruptures , arXiv:1801.00826
* Apache-2.0 vs MIT patent discussion: https://www.credativ.de/en/blog/credativ-inside/understanding-open-source-licenses-gpl-mit-apache-compared/
