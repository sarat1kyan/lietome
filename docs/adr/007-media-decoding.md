# ADR-007 Media decoding via PyAV

**Context.** Inputs are hostile; timestamps must be exact; VFR and rotated phone video are
common; we must never build shell commands from user input.

**Decision.** PyAV (`av`) for probing and decoding in-process. Per-frame PTS -> us. Display
rotation from `VideoFrame.rotation`. Time-based subsampling. Limits checked before and during
decode. No `ffmpeg`/`ffprobe` subprocess in the core.

**Rejected.** `cv2.VideoCapture` (index/FPS-based timing, silent VFR errors, weak metadata),
shelling out to ffmpeg (argument-injection surface, parsing text output, extra process).

**Consequences.** PyAV wheels bundle FFmpeg; keep updated for CVEs. OpenCV (pulled by
MediaPipe) bundles a second FFmpeg; macOS prints objc duplicate-class warnings - harmless so far,
monitored.
