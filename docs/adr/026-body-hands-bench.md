# ADR-026 Upper body and hands, per-machine benchmark, automatic live AU model

**Context.** Illustrators (hand gestures accompanying speech) are the movement cue with a
consistent direction in the meta-analyses (d = -0.14), and Lightman measured them only through
head speed. Self-touch and shrugs, which people read constantly, were invisible. And the live
AU model was fixed to resnet18 on every machine, although resnet50 is more accurate and fast
hardware can run it live.

**Decision.**

1. *Pose model.* MediaPipe Pose Landmarker lite (Apache-2.0, 5.8 MB, SHA-pinned in the model
   manifest) on every frame, offline and live; 5.8 ms per frame on an M5 Pro CPU. Missing
   model or runtime means body tracking is skipped, never a failure.
2. *Features*, normalized by the face so distance does not matter: shoulder height below the
   face center (face heights), shoulder tilt, fastest wrist speed (face widths per second),
   distance from the nearest hand point to the face box (face widths), shoulder visibility.
3. *Events.* Self-touch of the face (hand point within 0.1 face widths of the face box for
   400 ms or more) and shrug (shoulders more than max(0.08 face heights, 3 SD) above their
   calibration height for 150 ms to 2 s). OBSERVATION level; the self-touch description says
   the lying association is a myth (self-fidgeting d = -0.01).
4. *Movement cue.* Uses hand speed when the hands are tracked, head speed otherwise.
5. *Benchmark.* `lightman bench` times face landmarks, both AU models and pose on this machine
   (bundled test portrait or `--image`), lists ONNX providers and writes the result to the user
   config directory. M5 Pro CPU: face 3.5 ms, pose 5.8 ms, AU resnet18 16.5 ms, resnet50 71 ms.
6. *Automatic live AU model.* `au.live_model = "auto"` (default) uses resnet50 when the
   benchmark measured its p95 at 45 ms or less, else resnet18; an explicit model id overrides.
   CUDA machines (the `cuda` extra) and Windows laptops can now be measured with one command.

**Rejected.** A separate hand-landmark model (the pose model's hand points are enough for
touch and speed). Treating self-touch as a cue.

**Consequences.** Five new feature columns (body.*), two event types (self_touch, shrug), the
HUD draws shoulders, arms and wrists and flags a hand on the face.
