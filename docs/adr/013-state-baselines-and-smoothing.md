# ADR-013 Speaking/silent state baselines and AU smoothing

**Context.** Two real webcam sessions: calibration was silent, the subject then talked, and
nearly every episode was mouth articulation compared against a closed-mouth baseline. AU
probabilities also jittered frame to frame (AU4 spanning 0.11-0.49 on a calm face), producing
constant brow events.

**Decision.** (1) Baselines are computed per behavioral state when the calibration window
holds at least `min_samples` frames of each: `silent` and `speaking` (from VAD), next to `all`.
Each frame is scored against the baseline of its own state; the event carries the state tag.
Without a speaking-state baseline the earlier fallback stays: mouth-region events during
speech are tagged "speaking" with halved confidence. Audio now runs before the video baseline
in the prerecorded pipeline so speech segments define the states. (2) `au.*` signals pass
through a 5-frame median (centered offline, causal live) before baselines and events.

**Consequences.** Calibration instructions change: the subject should both sit quietly and
talk during the first 30 s (read a paragraph) so both states get a baseline. Live mode gets
the speaking flag from the browser audio stream; the CLI live path has no audio and therefore
no speaking state. Smoothing delays AU onsets by up to 2 frames.
