# ADR-029 Expressed affect, engagement, talk time and client trends

**Context.** Practitioners ask different questions than the deception literature: how did the
person's expression move over the session, were they with the conversation, who did the
talking, and is anything changing from one session to the next. All four can be answered from
signals Lightman already measures, against the person's own calibration.

**Decision.**

1. *Expressed affect* (practice/affect.py). Raw valence = AU12 + 0.5 AU6 - 0.6 (AU4 + AU15 +
   0.5 AU9 + 0.5 AU10 + 0.5 AU20); raw arousal = AU5 + 0.5 AU26 + 0.25 (AU1 + AU2) + head
   speed (capped); blendshape fallback when the AU model is off. Each is normalized by the
   calibration median and 1.4826 MAD (floor 0.05), smoothed over about one second, mapped with
   tanh(z / 3) to [-1, 1]. While the person speaks, voice loudness and pitch z (from the audio
   baseline) contribute 30% of arousal. Live: a circumplex readout on the video. Summary: means,
   share of time more positive, more negative, activated, calm, and the valence trend per minute.
2. *Engagement* (practice/conversation.py): share of frames with the face visible, head within
   25 degrees and gaze within 0.45 of their calibration centers, overall and per 10 s.
3. *Talk time*: speech frames are the client's when the mouth moves (rolling SD of jaw opening
   and AU25 above 1.5 times the 75th percentile of silent frames), otherwise someone else's.
   Turns join same-speaker runs across pauses up to 0.4 s and keep those of 0.5 s or more.
   Reported: seconds, share, turns, mean turn length, with a note that one microphone makes it
   approximate.
4. *Practice summary* (practice.json), computed from the saved tables for live, uploaded and
   older sessions (lazily on request): the above plus speech rate, long pauses, positive and
   negative pattern counts, gaze-away and self-touch counts, blink rate, pulse.
5. *Client trends*: `GET /api/clients/{code}/trends`, one row per session: valence, arousal,
   engagement, client talk share, speech rate, negative patterns per minute, blink rate. The
   clients page draws one sparkline per measure.

**Rejected.** Emotion classifiers trained on AffectNet or FER datasets (research-only licences,
and a category label overstates what a face shows). Speaker diarization models (gated weights,
heavy); the mouth-based split is explainable and local.

**Consequences.** New artifact practice.json, two endpoints, a session overview card and a
trends panel. Affect is labelled "expression, not feeling" everywhere it appears.
