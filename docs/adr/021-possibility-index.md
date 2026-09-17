# ADR-021 Possibility-of-deception cue index and extended live expression patterns

**Context.** ADR-017 rejected any per-question "deception likelihood". The maintainer asked
for a possibility statement anyway: not "lie", but "how close to the lie-associated pattern",
with the emotion layer extended and as accurate as the inputs allow. The honest version of
that request is an index over the weak literature cues, worded as possibility, with its
reliability and its counter-evidence shown next to it.

**Decision.**

1. *Cue index.* For a window (session, question, or live answer), each evaluable cue
   contributes +1 when it moved in the lie-associated direction, -1 when it moved clearly the
   other way, 0 otherwise, weighted by |d| from the source meta-analyses (pitch 0.21, lip
   press 0.16, movement 0.14, tension 0.27, negative-affect pattern 0.30, brief pattern 0.20,
   latency 0.02, blink 0.05). Index = 50 + 50 * weighted mean * reliability, reliability =
   (share of total weight that was evaluable) * min(1, window_s / 20). Bands: low < 40,
   unremarkable < 55, some < 70, elevated < 85, high. Output always carries drivers,
   counters, reliability and a caveat stating that this is not a probability and that all
   such cues combined reach about 54-60% accuracy. Wording everywhere: "possibility of
   deception, cue-based".
2. *New cues.* Negative-affect expression pattern during the answer (fear, anger, sadness,
   disgust, contempt, embarrassment, distress, tension; ten Brinke & Porter 2012), brief
   pattern during the answer (Porter & ten Brinke 2008), facial tension (mean z of AU4, AU7,
   AU23; DePaulo 2003 nervousness d 0.27).
3. *Protocol.* Per question: cue index. Session: relevant-vs-control mean index and delta,
   top question with drivers, one paragraph of possibility text. A delta of 10 or more is
   worded as "worth a follow-up question, not a finding".
4. *Live.* When an answer ends (end marker or next question), the server computes the cue
   profile and index for that answer against the person's baseline and the control answers
   so far, and pushes a question_summary message. The live panel shows a gauge with the
   control mean as a marker; the HUD shows the last answer's index under the question card.
5. *Expression patterns.* New prototypes: embarrassment (AU12 without AU6 with gaze down,
   Keltner 1995), distress (AU4+7+10, Prkachin 1992 pain core), tension (AU7+23 without
   12/26). Prototypes carry a valence tag used only by the cue layer. Personal thresholds:
   the resting level of each pattern during calibration (p90) raises the entry threshold by
   0.15 above it (capped 0.85), so a face that rests near a prototype does not fire it all
   session. Offline detection was missing from the prerecorded pipeline; it is now wired.

**Rejected.** Calling the index a probability or likelihood; a learned classifier (no
licensed labelled data); hiding counters or reliability; any single-cue verdict.

**Consequences.** ADR-017's rejection is amended: an index is allowed under the wording and
disclosure rules above. Expect the index to hover 45-60 for honest conversation; the
informative reading is relevant-vs-control within one person, not the absolute number.
