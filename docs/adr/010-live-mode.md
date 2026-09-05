# ADR-010 Live mode: bounded queue, streaming detectors, same outputs

**Context.** The maintainer and consenting friends want to test on themselves with a webcam.
Live analysis must never accumulate latency, must reuse the validated detectors, and must
produce the same session artifacts as prerecorded analysis.

**Decision.** `lightman live`: a capture thread (OpenCV webcam, or a real-time-paced file
replay for testing) feeds a queue of size 2; when full the oldest frame is dropped and
counted. The analysis loop runs on the main thread (required for the OpenCV preview on
macOS): landmarks (+ optional AU model, resnet18 by default) -> streaming baseline (collects
the first `baseline.window_s` seconds, then freezes) -> streaming hysteresis deviation
detector and blink detector with explicit state -> console/preview sink. Long runs emit a
provisional event after 1.5 s (tagged "provisional"); everything else is emitted on close. At
stop the run writes features.parquet, events.json, baseline.json, analysis.json (fps,
latency, drops), manifest.json and report.html like a prerecorded session.

**Verified.** Streaming baseline reproduces the offline baseline exactly on the same frames;
streaming deviation/blink events match offline start/peak/magnitude (end differs by at most
one frame; no merge-gap post-processing). Replay of a 30 fps file on M5 Pro: landmarks only
30 fps, 7 ms p50 latency, 0 drops; with AU resnet18 30 fps, 19 ms, 0 drops; with AU resnet50
14 fps, 51% dropped, latency bounded at ~120 ms.

**Rejected.** Unbounded queue (latency grows without limit), analyzing every frame with a slow
model (same), asyncio (no benefit for a single CPU-bound consumer), separate live-only
feature code (drift from the offline path).

**Consequences.** No live audio yet (microphone capture and streaming VAD/F0 are the next
step). Baseline does not adapt after calibration. Camera/mic permissions are the user's: the
tool prints a visible notice and the preview window is labelled.
