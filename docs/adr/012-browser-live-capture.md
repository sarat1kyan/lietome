# ADR-012 Browser live capture over WebSocket

**Context.** Terminal processes on macOS need camera/microphone permission granted to the
terminal app through System Settings; users hit "not authorized" with no prompt. Browsers
handle the permission prompt natively. Live audio was also missing.

**Decision.** `WS /api/live`: the page captures camera (getUserMedia) and microphone, sends
JPEG frames (15 fps, 640 px wide, at most 2 in flight) and 16 kHz float32 PCM chunks with a
9-byte header (kind, t_us); the server runs `LiveAnalyzer` (shared with the CLI runner) and
`StreamingAudioAnalyzer` (Silero VAD + single-window YIN with the absolute-threshold step,
voiced-speech-gated baseline and deviation events) in worker threads and streams back
per-frame values, 478 landmark points, quality, stats, events and audio readouts. Stop writes
the same session directory. The UI draws landmarks and the face box on the self-view, shows a
labelled LIVE badge, readouts, a rolling 60 s lane strip and the event feed, then opens the
saved session.

**Rejected.** WebRTC (more machinery for a localhost tool), sending raw frames (bandwidth),
pyin in the live path (25 s JIT warm-up), unlimited in-flight frames (latency growth).

**Consequences.** Live audio exists only in the browser path (the CLI `live` command stays
video-only). Frame JPEG compression adds a few ms and slight quality loss versus the CLI path.
