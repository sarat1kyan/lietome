# ADR-027 Local speech-to-text with word timing; opt-in recording and replay

**Context.** The maintainer's example: someone says "I did not steal the car" while the face
shows something else. Measuring that needs the words and their timing. Reviewing it needs the
video: live sessions kept numbers and thumbnails only, so the sessions view had no picture to
replay the overlays on.

**Decision.**

1. *Speech-to-text* (speech/transcribe.py): faster-whisper (MIT) with the multilingual Whisper
   base checkpoint (MIT; four files SHA-pinned in the manifest as model group `whisper__base`,
   pinned Hugging Face revision), int8 on CPU, word timestamps, VAD filter, language detection.
   Optional extra `lightman[asr]`; without it or without the model the session records
   "unavailable" and nothing else changes. Measured: 4.6 s of speech in 1.6 s on an M5 Pro,
   model load included.
2. *Live:* the audio stream keeps the session's PCM in memory (int16, capped at 45 min). After
   the session is saved, a background thread transcribes it and writes transcript.json
   (status pending, then done); the UI polls. Audio is never written to disk.
3. *Offline:* the audio track is decoded again at 16 kHz and transcribed at the end of the
   pipeline; the narrative gets one line with word, hedge and denial counts.
4. *Verbal markers* (speech/markers.py): small English lexicons of hedges and denials; longer
   phrases win ("did not" over "not"). A denial with a face or body event (expression pattern,
   episode, deviation, AU pairing, gaze away, self-touch, shrug, head gesture) within 1 s is a
   "denial moment". Per protocol answer: text, words, words per minute, hedges, denials, added
   to protocol.json. Other languages are transcribed but not marked.
5. *Recording and replay:* opt-in "record video" in the live view. The browser records the
   camera and microphone (MediaRecorder, WebM) and uploads it to the session after stop
   (`POST /api/sessions/{id}/media`, size-limited, video/webm or video/mp4 only) with the offset
   between recording start and the analysis clock. The sessions view plays it (or an uploaded
   original) and draws the HUD over it from the saved measurements at the playhead: face box,
   head axes, gaze, AU panel with SD, FACS pattern meter.

**Rejected.** Cloud transcription (audio would leave the machine). Streaming transcription
during the session (CPU competes with the face models; answers are reviewed afterwards).
Recording by default (privacy: frames stay in memory unless the operator opts in).

**Consequences.** New artifacts: transcript.json, media.webm + media.json. New endpoints:
transcript, media upload, media-info. `[speech]` config section.
