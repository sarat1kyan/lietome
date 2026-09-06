# ADR-014 Bounded adaptive baseline

**Context.** Four real sessions: a 30-40 s calibration cannot sample a person's conversational
range. In session 4 the speaking-state calibration gave browInnerUp p90 0.08 while free
conversation later had p90 0.61 (AU1 0.33 vs 0.82, jawOpen 0.05 vs 0.18). Ordinary talking
therefore read as a stream of deviations. Longer calibration helps but does not remove the
gap, and the maintainer will not sit through five minutes of it.

**Decision.** After the calibration window, every signal (per state) is tracked by an
exponentially weighted center and scale (half-life 60 s). The center updates only from frames
within 2.5 SD of the current baseline (excursions cannot pull it); the scale learns from every
frame with the residual clipped at 2.5 scales (bounded influence, otherwise a wider
distribution could never be learned). Both are bounded to the calibration anchor: the center may move
at most 3 anchor scales, the scale may grow to at most 4 x the anchor scale and never shrinks
below it. Offline and live share the tracker; offline runs it as a sequential pass so results
match live behavior. Events keep reporting the center/scale in force at the peak.

**Rejected.** Unbounded rolling statistics (absorb the changes we want to see), no adaptation
(calibration too short to be representative), a much longer calibration (user burden, and
still a sample of one situation).

**Measured.** Replaying stored sessions with identical thresholds: session 4 went from 336 to
133 deviations per minute, session 3 from 381 to 117; maximum severity 43 -> 29 SD.

**Consequences.** A deviation now means "unusual relative to how this person has been behaving
in this session so far, within limits set by the calibration". Slow drifts over minutes are
partly absorbed by design and are visible in the stored baselines, not as events. Bounds are
configurable (`[baseline.adaptive]`).
