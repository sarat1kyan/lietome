# ADR-020 Gaze-away episodes, live speech rate, span comparison, on-video HUD

**Context.** After ADR-019 the live view showed AU bars and a pattern meter but no session
context on the video itself, the sessions view had no way to compare one stretch of a session
with another (the core "Lie to Me" move: this answer against that answer, against calibration),
and two observable behaviors with literature were still missing: sustained gaze aversion and
speech rate.

**Decision.**

1. *Gaze-away episodes.* Eye-look proxy magnitude >= 0.45 or |head yaw| >= 25 deg opens an
   episode; it closes below 0.30 / 18 deg; at least 1 s. Event "gaze away (left): 2.3 s",
   OBSERVATION. The description states that looking away accompanies thinking, reading and
   listening. Live: same rule, one frame at a time, emitted when the episode ends; the HUD
   shows a running counter while it is open. Session 5 replay: see project-state.
2. *Live speech rate.* Syllable-nuclei proxy (energy-envelope peaks, the same function the
   offline stage uses) over a 2 s window when speech covers 60% or more of it: voice.rate_syl_s
   per 20 ms hop. It joins the live audio baseline and the deviation signals (default config);
   the audio_features table stores it.
3. *Span comparison.* GET /api/sessions/{id}/compare?a0&a1&b0&b1: for two ranges, per-signal
   medians and the shift in this person's robust SD (baseline scale; fallback MAD of span A),
   IQRs, frame counts, event rates per minute by type, speaking fraction, gated pulse medians.
   UI: compare mode (button or c), drag on the timeline sets A then B, presets from protocol
   questions. Table sorted by |shift|, 2 SD highlighted, caveat attached (speaking vs silent
   spans differ in every mouth signal by construction).
4. *On-video HUD.* One drawing module (frontend/src/lib/hud.ts): face-mesh contours (oval,
   eyes, brows, lips, irises, nose bridge) instead of a dot cloud; corner brackets with the
   tracking state; head axes; gaze reticle with the away counter; status block (timecode, fps,
   latency, drops, calibration phase or baseline state); question card during protocol
   (id, category, elapsed, deviations, answer latency); AU panel with z; FACS pattern meter;
   signal tape (four sparklines in SD units over 30 s); pulse block with bpm, SNR and the
   detrended POS waveform streamed per frame (45 samples, 3 s); voice level, F0 and syllable
   rate; last-event ticker; event flashes beside the face. Toggle "overlays" keeps the mesh and
   box only.
5. *Sessions view.* Stats row (episodes/min, deviations/min, patterns, nods/shakes, gaze away,
   blinks/min, voice events, pulse median). Change-density strip under the events: per 2 s,
   count of active deviation events (alpha) and whether any reached 6 SD (amber).

**Rejected.** Any composite "arousal" or "stress" score from the density strip: it stays a
count of out-of-range signals. Reading gaze aversion as a deception cue (the folk belief is not
supported; DePaulo 2003, Global Deception Research Team 2006). Client-side comparison on the
decimated feature series (the server reads full resolution).

**Consequences.** New event type gaze_away, new signal voice.rate_syl_s (unit syl_s), config
section [gaze]. The compare endpoint reads the whole parquet per call (fine for sessions of
minutes; paginate or cache if hour-long sessions appear).
