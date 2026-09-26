# ADR-023 Fixes from the first outside test sessions; localhost access

**Context.** Three live sessions on 17 September (two subjects, 106-189 s) and a static review
showed thirteen defects. Several only appear on real people: a resting gaze that is not aimed
at the lens, a muted microphone, JPEG-compressed skin colour, tracker glitches.

**Decision.**

1. Gaze-away and the embarrassment gaze-down condition are measured against this person's
   calibration center (gaze and head yaw), offline and live. Replay: total away time 77 s to
   23 s and 55 s to 29 s; longest run 19 s to 4 s.
2. A microphone that hears no speech during the reading and talking phases (or for 60 s)
   raises a HUD hint; a session with audio but no speech carries a warning in its notes and
   narrative.
3. Without a microphone the calibration phase hint no longer marks post-calibration frames as
   speech; those frames are scored against the combined baseline.
4. Microexpression candidates need a rise from rest (score under 0.3 within 8 frames before
   the entry crossing) to peak in 150 ms or less. Replay: 12 to 8 and 4 to 1 candidates.
5. The pulse estimate needs 25% usable windows overall and a mostly usable reference window;
   otherwise it reports not usable instead of a reference built from a few noisy windows.
6. The browser measures forehead and cheek colour means on the raw frame (boxes from the
   previous frame's landmarks) and sends them as binary kind 3; the analyzer prefers them to
   means from the JPEG. The session records which source the estimate used.
7. The whole-session cue index is flagged explicitly and always discounted; it has no
   within-person comparison.
8. Head speed is median-filtered over three frames before scoring (single-frame pose flips
   reached 280 deg/s).
9. Pattern counts in the narrative and summary exclude meta tags (brief, fast_onset,
   valence). The live pattern meter shows the server's scores against this person's entry
   thresholds; the client prototype list matches the server for the offline readout.
10. Parquet reads in the API are cached by file and modification time.
11. Localhost: direct loopback connections skip the token (not when a forwarding header is
    present). In LAN mode `serve` also opens plain HTTP on 127.0.0.1 at port + 1; browsers
    allow the camera on http://localhost, so no certificate warning on the host machine.

**Rejected.** A per-subject gaze calibration step (the existing calibration window already
gives the center). Dropping rPPG (it stays, gated, and now has a better input).

**Consequences.** Binary message kind 3 added to the live protocol. `serve --local-port`
(0 = port + 1, -1 = off). New regression tests in tests/unit/test_audit_fixes.py.
