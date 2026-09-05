# Answers to the founding research questions

Status as of 2026-09-05. "Open" means not yet answered with evidence.

1. **Strongest practical open-source AU extraction?** No permissively licensed AU model is
   validated in Lightman yet. OpenGraphAU (Apache-2.0) is the leading candidate; Py-Feat's
   models are MIT-wrapped with per-model licenses. The strongest *tools* (OpenFace 3.0,
   LibreFace) are non-commercial.
2. **What modernizes OpenFace?** OpenFace 3.0 (multitask, RetinaFace+STAR), LibreFace 2.0
   (synthetic-data-augmented), OpenGraphAU (graph AU relations). All three post-date OpenFace 2.
3. **Commercial/open-source friendly?** MediaPipe (Apache-2.0), OpenGraphAU (Apache-2.0),
   Py-Feat (MIT + per-model), Whisper family (MIT), Silero (MIT), pyannote (MIT gated).
4. **Face detection?** MediaPipe BlazeFace inside the landmarker bundle (V0.1). RetinaFace MIT
   re-implementations if a stronger standalone detector is needed.
5. **Stable tracking?** MediaPipe VIDEO-mode tracker for single face. Multi-face: IoU/landmark
   association + re-identification embedding later (must be permissively licensed; ArcFace packs
   are not).
6. **Landmarks?** FaceMesh-V2 (478). Alternatives: STAR (in OpenFace 3.0, license blocked),
   face-alignment (BSD, 68/3D).
7. **Head pose?** Euler from MediaPipe's transform. Verified round-trip mathematically; camera
   sign conventions **open**.
8. **Gaze?** Proxy from `eyeLook*` blendshapes; dedicated model **open** (license issues).
9. **One AU model or several?** One multi-AU model (graph/multitask) plus geometric features;
   specialized models only where measured to help.
10. **Temporal architecture?** V0.1: robust-z + hysteresis. Next: change-point (ruptures) and
    TCN/state-space on baseline-normalized features, evaluated LOSO.
11. **Evaluating ME spotting?** MEGC protocol (F1 on interval IoU >= 0.5), LOSO, cross-dataset.
12. **Obtainable datasets?** All require agreements; MU3D free for research. See datasets.md.
13. **Audio features with support?** F0 statistics, energy, speech rate, pauses, response
    latency; jitter/shimmer as voice-quality observations.
14. **Weak / excluded?** Any "voice stress" or "layered voice analysis" style deception index.
15. **ASR?** faster-whisper (CUDA/CPU) and whisper.cpp (Apple) - both MIT. Transcripts are
    opt-in and never logged.
16. **A/V sync?** Shared integer-us media time from container PTS for both streams (ADR-004).
17. **Subject baselines?** Robust per-signal statistics over a quality-gated window (V0.1);
    later: anchored + adaptive windows, question-aware segmentation.
18. **Calibration length?** Default 30 s; reliability term saturates at 600 usable frames
    (~20 s at 30 fps). Empirical tuning **open**.
19. **Online adaptation?** Planned for live mode with slow EWMA and drift guards; **open**.
20. **Drift prevention?** Anchor to the initial window; adapt only within bounds; log when the
    adaptive baseline diverges from the anchor. **open**.
21. **Multimodal confidence calibration?** Event confidence = measurement quality today. Real
    calibration needs labeled data; **open**.
22. **Low-quality propagation?** Quality gates baseline membership and event opening; it
    multiplies into confidence. Implemented.
23. **Multiple faces?** `track_id`/`subject_id` in schema; detector-side association **open**.
24. **Real time on RTX 3060 Ti?** Landmarks+blendshapes already real time on CPU; AU CNN and
    Whisper small/medium should be real time on 3060 Ti. **Not measured yet.**
25. **Apple Silicon?** MediaPipe CPU: 3.5 ms/frame measured. whisper.cpp CoreML for ASR.
26. **ONNX?** Preferred packaging for any PyTorch-origin model so one runtime covers CPU, CUDA
    (RTX), CoreML (Apple). 27. **TensorRT?** Only if ONNX-CUDA is insufficient on the desktop.
    28. **CoreML?** Via onnxruntime CoreML EP or whisper.cpp; not needed yet.
29. **PyTorch canonical for training?** Yes; export to ONNX for inference.
30. **License?** Apache-2.0 (ADR-005).
