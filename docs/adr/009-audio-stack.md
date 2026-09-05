# ADR-009 Audio stack: PyAV decode, Silero VAD (ONNX), librosa pyin

**Context.** Phase 5 needs voice activity, pitch, loudness, pauses and approximate voice
quality from the same file as the video, aligned on the shared microsecond clock, without
torch and without GPL code in the core.

**Decision.** Decode with PyAV and resample to 16 kHz mono (`media/audio.py`), stamping blocks
with container time so audio shares the video origin. VAD: Silero v6 ONNX via onnxruntime,
pinned in the manifest. Frame features (hop 20 ms): RMS energy dB, pyin F0 and voicing
probability, VAD speech probability. Segment features: duration, pause before, F0 median and
spread in semitones, energy, syllable-nuclei rate proxy, jitter/shimmer *approximations* from
the frame tracks. Baselines are computed over speech frames only. Events: `voice.f0_hz` and
`voice.energy_db` robust-z deviations (source "audio") and `speech_pause` observations.

**Rejected.** silero-vad pip package (torch), openSMILE (non-commercial), parselmouth (GPL-3),
webrtcvad (unmaintained, weaker), energy-only VAD (fails in noise). `librosa.yin` alone (no
voicing decision). Cycle-level jitter/shimmer (needs pulse marking; deferred, hence "_approx").

**Consequences.** librosa adds ~300 MB of dependencies and a one-time numba JIT cost per
process; acceptable for prerecorded analysis, to be revisited for live mode (yin + VAD gate).
No speaker diarization yet: with several speakers the "baseline" mixes voices. No question/
answer structure yet, so response latency is not computed; `speech_pause` is the placeholder.
