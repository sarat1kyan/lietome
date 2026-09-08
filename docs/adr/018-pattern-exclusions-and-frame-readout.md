# ADR-018 Exclusion AUs in expression prototypes, per-signal event rules, frame readout

**Context.** Session 5 (3:04 conversation, calibration v2, adaptive baseline): 131
deviations/min; gaze.vertical (42), jawOpen (38), head.speed (32) and gaze.horizontal (18)
were the top signals. Gaze and head-speed excursions were mostly sub-second glances and
turns; jaw/AU25/AU26 excursions were articulation whose bimodal distribution the robust scale
underestimates. 13 expression patterns fired (8 happiness, 5 surprise); "surprise" during
speech was brow raises without eye widening, and smiles were not split by cheek raise.
Live view showed a face box and lane plots but nothing about which AUs were active.

**Decision.**

1. Prototypes gain an `absent` list: a pattern scores 0 while any listed AU exceeds 0.35.
   New prototypes: social smile (12 without 6), brow flash (1+2 without 5/26), lip press
   (24 without 12), brow furrow (4 without 1/2/12). Happiness keeps 6+12 (Duchenne). The
   narrative reports the Duchenne vs lip-corner-only split as descriptive counts.
2. Event rules by signal prefix, most specific prefix wins: entry 5 SD for gaze.* and
   head.speed_deg_s, 6 SD for blendshape.jawOpen, au.AU25, au.AU26; minimum duration 400 ms
   for gaze.* and 250 ms for head speed. Session 5 replay: 404 -> 268 deviations (167 ->
   111/min), gaze.vertical 33 -> 7, head.speed 14 -> 6, jawOpen 47 -> 24, severity
   distribution unchanged (p50 5.6, max 28).
3. Live sessions persist voice hops (audio_features.parquet, audio_baseline.json), and the
   pitch cue is evaluated live from voiced F0 against the speaking baseline.
4. Frame readout: GET /api/sessions/{id}/frame?t_us= returns every signal at the nearest
   frame plus the matching state baseline; the sessions view shows AU bars with FACS names
   and z, pattern meter, head pose, gaze and eye opening at the playhead. The live self-view
   draws the same: AU bars (amber when >= 4 SD), pattern meter, head axes, gaze arrow, blink
   and speech indicators, event flashes near the face.

**Rejected.** Per-AU learned thresholds (no labelled data). Dropping gaze/head speed
(useful when sustained). Emotion words on the overlay without the AU list.

**Consequences.** Fewer, longer, more explainable deviation events; pattern names are
narrower and each names its exclusion. Frame readout cost: one parquet column scan per
request, debounced client-side (90 ms).
