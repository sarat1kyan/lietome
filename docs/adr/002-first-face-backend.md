# ADR-002 First face backend: MediaPipe Face Landmarker

**Context.** V0.1 needs face detection, tracking, dense landmarks, head pose and *some*
expression signal, commercially usable, fast on CPU on both target machines.

**Decision.** MediaPipe Face Landmarker (Apache-2.0 code and models) in VIDEO mode, with
blendshapes and the facial transformation matrix enabled. Wrapped behind
`face.base.FaceLandmarker` so it can be replaced or complemented.

**Rejected.** OpenFace 2/3 and LibreFace (non-commercial), InsightFace packs (non-commercial),
custom RetinaFace + separate landmark model (more moving parts, no expression signal).

**Consequences.** Blendshapes are animation coefficients, not AUs; all AU wording is "(proxy)".
A validated AU model is a separate future backend (OpenGraphAU or Py-Feat). `mediapipe==1.0.1`
is excluded (macOS abort). MediaPipe pulls heavy transitive deps (opencv-contrib, matplotlib,
sounddevice); acceptable for now, revisit if install size matters.
