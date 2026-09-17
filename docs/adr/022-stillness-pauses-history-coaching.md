# ADR-022 Stillness, live pauses, microexpression tier, subject history, capture coaching

**Context.** Before the first outside tests the maintainer asked for one more broad pass.
Gaps found: reduced movement (the one movement cue with a consistent direction in the
meta-analyses) had no event of its own; live sessions had no pause events although the
offline audio stage has them; brief patterns were not separated by onset speed; nothing
compared a person across sessions; operators got no help when the capture was poor.

**Decision.**

1. *Stillness episodes.* Head speed under 35% of this person's usual speed (clamped to 1-3
   deg/s) for 3 s or more, after calibration. OBSERVATION; the description names listening,
   concentration and fatigue first. Offline and streaming.
2. *Live pauses.* Within-speech gaps of at least audio.long_pause_ms (1.5 s) once the audio
   baseline is ready, as speech_pause events from the live audio stream (same type as offline).
3. *Microexpression tier.* A brief pattern (under 500 ms) that peaks within 150 ms of onset is
   labelled "microexpression candidate" and tagged fast_onset, offline and live. Candidate only:
   the literature's definitions need 100+ fps and FACS coders. New prototype: lip bite (AU32
   without AU12).
4. *Subject history.* GET /api/sessions/{id}/history: the same subject's sessions with baseline
   centers of eight signals, blink rate, pulse median, episodes and the session cue index, plus
   this session's baseline shift against the median of the others in robust SD. Live start
   takes a subject id. UI card under the summary; its note says shifts point to lighting,
   distance and mood, not to answers.
5. *Capture coaching.* Per frame, the analyzer emits hints from the quality terms it already
   computes: no face, face small (under the AU model minimum), dim, too bright, soft image,
   turn toward the camera, low frame rate. Shown as a banner on the HUD.
6. *Protocol statistics.* The relevant-vs-control index delta carries a 95% bootstrap interval
   (2000 resamples) and a permutation p; when the interval includes zero the text says the
   difference could be noise. Per-question narrative lists the patterns.
7. *UI.* Expression lane on the timeline (green smiles, red negative valence, violet other;
   fast-onset marked), event list sort and filter box, copy-summary button, question script
   templates and shuffle, hotkeys n (next), e (end answer), o (overlays).

**Rejected.** Hand or body tracking for illustrators (no model in scope yet). Treating
stillness or pauses as cues with weight beyond what the meta-analyses give them.

**Consequences.** New event types stillness and (live) speech_pause; new tag fast_onset; new
endpoint history. Nothing here changes the index weights.
