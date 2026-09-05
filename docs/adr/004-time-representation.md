# ADR-004 Time representation

**Context.** Video (VFR common), audio (48 kHz), and future live capture must align to
millisecond precision over multi-hour sessions; results must survive JSON round-trips exactly.

**Decision.** Media time is an `int` count of microseconds (`t_us`) relative to the first
decoded frame of the analyzed stream, derived exactly from container PTS with `Fraction`
arithmetic. Frame index x FPS is used only when PTS is absent, and the row is flagged
`timestamp_estimated`. Wall-clock time is a separate ISO-8601 UTC string. Human display uses
`HH:MM:SS.mmm`.

**Rejected.** Float seconds (rounding/equality issues, no exactness guarantee), milliseconds
(too coarse for 48 kHz audio and 240 fps video), nanoseconds (overkill; int64 still fine but
JSON readers vary).

**Consequences.** MediaPipe requires ms; the backend converts and enforces monotonicity.
