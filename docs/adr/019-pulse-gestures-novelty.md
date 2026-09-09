# ADR-019 Camera pulse estimate, head gestures, unfamiliar AU pairings

**Context.** Sessions so far report deviations, episodes, blinks, expression patterns and
voice. Three observable behaviors with real literature were missing: pulse rate (remote
photoplethysmography, rPPG), head nods and shakes, and "the face is doing something it has not
done before in this session". Each can be measured against the person's own calibration and
worded without a claim about cause.

**Decision.**

1. *Pulse estimate (rPPG).* Per frame, mean R/G/B over forehead and both cheeks (MediaPipe
   landmarks) is stored as skin.r/g/b. Every second, a 10 s window is resampled to 15 Hz,
   projected with POS (Wang et al. 2017), detrended, and the dominant frequency in 0.7-3.0 Hz
   is taken as the pulse. SNR follows de Haan and Jeanne (2013): peak and harmonic vs the rest
   of the band. Estimates below 3 dB are kept in pulse.json but faded in the UI and ignored for
   events. Events "pulse estimate up/down: X vs Y bpm" fire when the estimate stays 10 bpm or
   more from the reference (first 30 s of usable estimates) for 5 s or more. OBSERVATION level
   with the caveat in every description: optical estimate, fails with motion, light and low
   contrast; darker skin tones give lower SNR (Nowara et al. 2020), so the gate drops more of
   their windows rather than reporting noise.
2. *Head gestures.* Alternating extrema of smoothed pitch (nod) or yaw (shake) with swings of
   at least 3 deg (nod) or 4 deg (shake) and 0.1-0.8 s between extrema; at least three extrema.
   Label "head nod: 1.5 cycles, 8 deg". OBSERVATION level; the description says nods accompany
   agreement, rhythm, emphasis and listening alike. Live version runs the same detector on a
   4 s buffer and emits a gesture 0.5 s after it ends. Session 5 replay: 5 nods, 0 shakes.
3. *Unfamiliar AU pairings.* Calibration records which pairs of watched AUs (1, 2, 4, 5, 6, 7,
   9, 12, 15, 17, 20, 23, 24) are active together at probability 0.5 or more. After it, a frame
   whose active AUs include a pairing never seen, held 300 ms, yields "new AU pairing:
   AU4+AU23" once. Articulation AUs (10, 14, 25, 26, unilateral) are excluded: in speech they
   pair with everything. A first version used whole combinations and produced 30 events of 6-8
   AUs on session 5; pairings are fewer and nameable.
4. *UI.* Timeline gains a pulse lane in bpm (faded where gated). Sessions view gains "key
   moments": the largest changes spread across the session (one per 15 s), with thumbnails,
   click to seek. Live sessions now save thumbnails at emission for episodes, patterns,
   gestures and pairings (bounded to 200). Live HUD shows the pulse estimate with its SNR or
   "not usable". Event panel gains gestures and pulse filters.

**Rejected.** Reporting bpm without an SNR gate. Emotion or arousal words on pulse changes.
Learned gesture classifiers (no need: the kinematics are simple and explainable). Whole-set AU
novelty (see 3).

**Consequences.** New columns skin.r/g/b in features.parquet (three floats per frame, not
biometric identifiers but skin color means; documented in privacy.md). pulse.json artifact.
New event types: pulse_change, head_gesture, au_novelty. Config sections [pulse], [gestures],
[novelty].
