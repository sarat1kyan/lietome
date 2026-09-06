# ADR-006 Baseline V0.1: robust statistics over a leading window

**Context.** The product promise is "unusual *for this person*". We need a first baseline that
is explainable, cheap, robust to the very excursions we detect, and honest about reliability.

**Decision.** Per signal: center = median, scale = max(1.4826,MAD, unit floor) computed over
frames with `t_us <= window_s` and `quality >= min_quality`. Robust z = (x - center)/scale.
Reliability = min(1, n/good_samples) x mean quality in window, with notes for short windows,
too few samples, and floored scales. Everything is persisted in `baseline.json`.

**Rejected for now.** Mean/SD (one blink or head turn inflates SD), Gaussian mixture / one-class
models / autoencoders (no data to validate; opaque), fully adaptive online baselines (drift risk
without anchoring).

**Amendment (2026-09-06).** The first real webcam session showed the MAD collapsing on
zero-inflated signals (resting jawOpen: MAD 0.004, SD 0.12) so ordinary expressions read 50-80
SD. Floors are now measured from that calibration window (coefficient 0.03, probability 0.05,
deg 1.0, ratio 0.01) and a trimmed-SD fallback rescues degenerate signals while the MAD keeps
its contamination resistance elsewhere. Replay of the same session: max severity 81 -> 38 SD;
event count barely changed (310 -> 313) because the subject really was moving. Speaking is the
next confound: mouth signals during
detected speech are tagged "speaking" with halved confidence, pending a speaking-state baseline.

**Consequences.** The window is a calibration convenience, not a psychological claim - the
report says so. Floored signals produce over-sensitive events; flagged. Next: anchored +
bounded adaptive baseline for live mode; question-aware segmentation when speech timing exists.
