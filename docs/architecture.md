# Architecture

## Pipeline (V0.1, prerecorded video)

```
media file
  |  lightman.media.probe      container/stream metadata, SHA-256, limit checks (no decode)
  |  lightman.media.decode     PyAV, PTS -> int us, display rotation, time-based subsampling
  v
RGB frame + t_us
  |  lightman.face             FaceLandmarker Protocol -> FaceObservation (landmarks, blendshapes, 4x4)
  v
FaceObservation
  |  lightman.face.au_base     AUDetector -> 41 AU probabilities from the face crop (OpenGraphAU ONNX)
  |  lightman.features         head pose (Euler from 4x4), EAR, blendshape + AU columns, quality -> Arrow row
  v
FeatureTable (one row per analyzed frame, NaN where no face)
  |  lightman.baseline         per-signal median / 1.4826,MAD over a quality-gated leading window
  v
robust z per signal
  |  lightman.events           blinks (EAR, subject-relative threshold), per-signal hysteresis
  |                            deviations (OBSERVATION), co-occurrence clusters (INTERPRETATION)
  v
events + summary
  |  lightman.pipeline         orchestration, timings, thumbnails (second sequential pass)
  |  lightman.report           self-contained HTML (inline SVG, base64 thumbnails)
  v
output/<session_id>/{metadata,baseline,events,analysis,manifest}.json, features.parquet, report.html
```

Cross-cutting: `schema` (pydantic models), `models` (pinned asset registry), `config` (typed
TOML), `core` (errors, timebase, logging, environment snapshot).

## Why this shape (and what was challenged)

The founding brief proposed INPUT -> VIDEO+AUDIO+SPEECH -> TEMPORAL -> BASELINE -> FUSION -> EVENTS
-> TIMELINE. We kept the layering but made three changes:

1. **Normalization precedes temporal modeling.** Deviations are computed *relative to the
   subject* before any temporal detector runs. This is what makes an event
   "unusual for this person" instead of "unusual for the population" and it must sit as low in
   the stack as possible so every later module reasons in baseline-relative units.
2. **Quality is a first-class signal, not a post-hoc filter.** A per-frame quality scalar rides
   alongside every feature row; baselines, detectors, and confidence all consume it. Bad input
   degrades confidence rather than producing confident nonsense.
3. **Fusion is deferred and event-level.** Early feature-level fusion would lock the design to
   one model family. Co-occurrence of per-modality events (with shared us time base) is a
   simple, explainable fusion that already gives most of the value; learned fusion is a later
   research item that must beat it on held-out data to be adopted.

## Data model (see `src/lightman/schema/`)

* `Provenance` - extractor id/version, model id + SHA-256, runtime, Lightman version.
* `MediaInfo` / `VideoStreamInfo` / `AudioStreamInfo` - demuxer facts; file name + hash only.
* Per-frame **FeatureTable** (Arrow/Parquet) - not pydantic; columns are documented in
  `features/table.py`. Meta: `frame_index, source_index, t_us, timestamp_estimated,
  face_present, face_count, quality, face.bbox_*, face.width_px`. Signals: `head.*`, `eye.*`,
  `blendshape.*`.
* `SignalBaseline` / `BaselineSnapshot` - center, scale, n, floor flag per signal; window,
  reliability, notes.
* `FeatureContribution` - one signal's peak value, baseline center/scale, signed robust z.
* `Event` - id, subject, source, type, **EvidenceLevel**, start/end/peak us, label, description,
  contributions, severity, confidence, quality, baseline_quality, extractor_id, tags. The model
  validator rejects `SPECULATION`.
* `QualitySummary`, `OutputArtifact`, `AnalysisManifest` - session-level record: config
  snapshot, environment, provenance list, output hashes, stage timings, disclaimer.

Extensibility already designed in: `subject_id` and `source` on every event (multi-person,
multi-modality), `track_id` on `FaceObservation`, `speaker`/audio events can share `t_us`.

## Time base (ADR-004)

Media time is `int` microseconds from the first decoded frame. Derived exactly from container
PTS via `Fraction` arithmetic; never from frame index x FPS unless PTS is missing (then flagged
`timestamp_estimated`). Wall clock is a separate ISO-8601 UTC string.

## Head pose conventions

`features.head_pose.head_pose_from_matrix` re-orthonormalizes the 3x3 block (SVD) and
decomposes as pitch(x),yaw(y),roll(z) Tait-Bryan angles in degrees. Round-trip is tested to
1e-6 deg. **Sign conventions relative to the camera (e.g. positive yaw = subject turns to their
left?) are not yet verified on real footage** - see project-state. Until verified, only
*deviations* in these angles are used, which are sign-agnostic.

## Signal quality heuristic (`features/quality.py`)

`quality = size_term x pose_term`, size full credit at >=120 px face width, pose full credit at
<=20 deg off-axis, zero at >=60 deg. Deliberately simple and documented; to be replaced by measured
blur/illumination/occlusion terms.

## Live mode (implemented for video, ADR-010)

`live.sources` (webcam / real-time file replay) -> capture thread -> queue(2, drop oldest) ->
main-thread analysis loop -> `live.streaming` (StreamingBaseline, StreamingDeviationDetector,
StreamingBlinkDetector: the offline statistics with explicit state) -> sink (console, preview
window) -> same session outputs at stop. Latency is bounded by (queue size + 1) x inference
time. Live audio and a WebSocket event stream are next.

## Replaceable seams

| Seam | Interface | Today |
|---|---|---|
| Face landmarks | `face.base.FaceLandmarker` | MediaPipe Face Landmarker |
| AU detection | `face.au_base.AUDetector` | OpenGraphAU ONNX (resnet50 / resnet18) |
| Model assets | `models/manifest.json` + `ModelRegistry` | 1 entry |
| Event detectors | pure functions in `events/` | blinks, deviations, clusters |
| Baseline | `baseline.compute_leading_window_baseline` | leading window |
| Report | `report.html.render_report` | HTML |
