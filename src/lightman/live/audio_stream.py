"""Streaming audio analyzer for live mode: 16 kHz mono PCM chunks -> VAD -> energy/F0 per
20 ms hop -> streaming baseline over voiced speech -> voice deviation events.

Differences from the offline audio stage, on purpose: F0 comes from ``librosa.yin`` (no
voicing decision, but no numba warm-up delay); voicing = VAD speech probability above the
threshold AND energy above the floor AND a periodicity check on the yin trough. Jitter/shimmer
and segment features are not computed live.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from lightman.audio.features import FRAME_LENGTH, HOP, RATE, SILENCE_DB, syllable_nuclei_count
from lightman.audio.vad import CHUNK, CONTEXT, SileroVAD
from lightman.config import LightmanConfig
from lightman.live.streaming import StreamingBaseline, StreamingDeviationDetector
from lightman.schema import Event
from lightman.schema.events import EvidenceLevel, FeatureContribution

VOICED_ENERGY_FLOOR_DB = -50.0
RATE_WINDOW_HOPS = 100  # 2 s of 20 ms hops for the speech-rate proxy
RATE_MIN_SPEECH_FRACTION = 0.6


@dataclass(slots=True)
class AudioFrameResult:
    t_us: int
    speech_prob: float
    f0_hz: float | None
    energy_db: float
    voiced: bool
    new_events: list[Event]
    baseline_ready: bool
    rate_syl_s: float | None = None


class StreamingAudioAnalyzer:
    def __init__(
        self, cfg: LightmanConfig, vad: SileroVAD, *, subject_id: str, id_start: int = 200_000
    ) -> None:
        import onnxruntime  # noqa: F401 - VAD needs it; fail early if missing

        self.cfg = cfg
        self.vad = vad
        self.subject_id = subject_id
        self._buf = np.zeros(0, dtype=np.float32)
        self._buf_t0_us = 0  # container/live time of _buf[0]
        self._consumed = 0  # samples consumed from the stream start
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._ctx = np.zeros(CONTEXT, dtype=np.float32)
        self._sr = np.array(RATE, dtype=np.int64)
        self._speech_prob = 0.0
        self._vad_pos = 0  # samples fed to VAD
        self.baseline = StreamingBaseline(
            cfg.baseline, ["voice.f0_hz", "voice.energy_db", "voice.rate_syl_s"]
        )
        self._energy_hist: list[float] = []
        self._speech_hist: list[bool] = []
        self._last_speech_us: int | None = None
        self._in_speech = False
        self._pause_k = 900_000
        self.detector: StreamingDeviationDetector | None = None
        self.events: list[Event] = []
        self._id_start = id_start
        self._warmup_us = cfg.events.warmup_ms * 1000
        self.hops: list[tuple[int, float, float, float, bool, float]] = []
        """(t_us, speech_prob, f0_hz or nan, energy_db, voiced) per 20 ms hop."""

    def push(self, pcm: npt.NDArray[np.float32], t_us: int) -> list[AudioFrameResult]:
        """Append samples whose first sample occurs at ``t_us``; return per-hop results."""
        pcm = np.asarray(pcm, dtype=np.float32).reshape(-1)
        if self._buf.size == 0:
            self._buf_t0_us = t_us
        self._buf = np.concatenate([self._buf, pcm])
        out: list[AudioFrameResult] = []
        # VAD over complete 512-sample chunks that we have not fed yet
        total_avail = self._consumed + self._buf.size
        while self._vad_pos + CHUNK <= total_avail:
            start = self._vad_pos - self._consumed
            chunk = self._buf[start : start + CHUNK]
            inp = np.concatenate([self._ctx, chunk])[None, :]
            prob, self._state = self.vad._session.run(
                None, {"input": inp, "state": self._state, "sr": self._sr}
            )
            self._speech_prob = float(prob.ravel()[0])
            self._ctx = chunk[-CONTEXT:]
            self._vad_pos += CHUNK
        # hops: emit one result per HOP once a full analysis window is available around it
        half = FRAME_LENGTH // 2
        while self._buf.size >= FRAME_LENGTH:
            win = self._buf[:FRAME_LENGTH]
            center_us = self._buf_t0_us + int(half * 1_000_000 / RATE)
            rms = float(np.sqrt(np.mean(win.astype(np.float64) ** 2)))
            energy = 20 * math.log10(rms) if rms > 1e-9 else SILENCE_DB
            f0: float | None = None
            voiced = False
            if (
                self._speech_prob >= self.cfg.audio.vad_threshold
                and energy > VOICED_ENERGY_FLOOR_DB
            ):
                f0, periodic = _yin_f0(win, self.cfg.audio.f0_min_hz, self.cfg.audio.f0_max_hz)
                voiced = periodic
                if not voiced:
                    f0 = None
            speaking_hop = self._speech_prob >= self.cfg.audio.vad_threshold
            pause_events = self._track_pauses(center_us, speaking_hop)
            self._energy_hist.append(energy)
            self._speech_hist.append(speaking_hop)
            if len(self._energy_hist) > RATE_WINDOW_HOPS:
                self._energy_hist.pop(0)
                self._speech_hist.pop(0)
            rate: float | None = None
            if len(self._speech_hist) == RATE_WINDOW_HOPS:
                frac = sum(self._speech_hist) / RATE_WINDOW_HOPS
                if frac >= RATE_MIN_SPEECH_FRACTION:
                    speech_s = frac * RATE_WINDOW_HOPS * HOP / RATE
                    rate = syllable_nuclei_count(np.asarray(self._energy_hist)) / speech_s
            values = {
                "voice.f0_hz": f0 if f0 is not None else math.nan,
                "voice.energy_db": energy,
                "voice.rate_syl_s": rate if rate is not None else math.nan,
            }
            quality = 1.0 if voiced else 0.0
            new_events: list[Event] = []
            if not self.baseline.ready:
                if self.baseline.update(center_us, quality, values):
                    snap = self.baseline.snapshot
                    assert snap is not None  # noqa: S101
                    self.detector = StreamingDeviationDetector(
                        self.cfg.events.model_copy(
                            update={
                                "signals": self.cfg.audio.signals,
                                "min_duration_ms": self.cfg.audio.min_event_ms,
                            }
                        ),
                        snap,
                        subject_id=self.subject_id,
                        extractor_id=self.vad.provenance.extractor_id,
                        frame_period_us=int(HOP * 1_000_000 / RATE),
                        id_start=self._id_start,
                    )
            elif self.detector is not None:
                new_events = [
                    e.model_copy(update={"source": "audio"})
                    for e in self.detector.update(center_us, quality, values)
                    if e.start_us >= self._warmup_us
                ]
                new_events += pause_events
                self.events.extend(new_events)
            self.hops.append(
                (
                    center_us,
                    self._speech_prob,
                    f0 if f0 is not None else math.nan,
                    energy,
                    voiced,
                    rate if rate is not None else math.nan,
                )
            )
            out.append(
                AudioFrameResult(
                    t_us=center_us,
                    speech_prob=self._speech_prob,
                    f0_hz=f0,
                    energy_db=energy,
                    voiced=voiced,
                    new_events=new_events,
                    baseline_ready=self.baseline.ready,
                    rate_syl_s=rate,
                )
            )
            self._buf = self._buf[HOP:]
            self._consumed += HOP
            self._buf_t0_us += int(HOP * 1_000_000 / RATE)
        return out

    def _track_pauses(self, t_us: int, speaking: bool) -> list[Event]:
        """Within-speech gaps of at least ``audio.long_pause_ms`` (after the baseline is ready)."""
        out: list[Event] = []
        if speaking:
            if (
                not self._in_speech
                and self._last_speech_us is not None
                and self.baseline.ready
                and t_us - self._last_speech_us >= self.cfg.audio.long_pause_ms * 1000
            ):
                gap_ms = (t_us - self._last_speech_us) / 1000
                out.append(
                    Event(
                        event_id=f"ev_{self._pause_k:05d}",
                        subject_id=self.subject_id,
                        source="audio",
                        event_type="speech_pause",
                        level=EvidenceLevel.OBSERVATION,
                        start_us=self._last_speech_us,
                        end_us=t_us,
                        peak_us=self._last_speech_us,
                        label=f"speech pause: {gap_ms / 1000:.1f} s",
                        description=(
                            f"No speech for {gap_ms:.0f} ms between two stretches of speech. "
                            "Pauses mark thinking, turn-taking and breathing; the deception "
                            "literature finds pause measures small and inconsistent."
                        ),
                        contributions=[
                            FeatureContribution(
                                feature="voice.pause_ms",
                                unit="ms",
                                peak_value=gap_ms,
                                baseline_center=float(self.cfg.audio.long_pause_ms),
                                baseline_scale=float(self.cfg.audio.long_pause_ms) / 2,
                                peak_deviation=(gap_ms - self.cfg.audio.long_pause_ms)
                                / (self.cfg.audio.long_pause_ms / 2),
                                direction="increase",
                            )
                        ],
                        severity=round(min(10.0, gap_ms / 1000), 2),
                        confidence=0.7,
                        quality=1.0,
                        baseline_quality=1.0,
                        extractor_id=self.vad.provenance.extractor_id,
                        tags=["pause"],
                    )
                )
                self._pause_k += 1
            self._in_speech = True
            self._last_speech_us = t_us
        else:
            self._in_speech = False
        return out

    def f0_z(self) -> tuple[np.ndarray, np.ndarray] | None:
        """(t_us, robust z of voiced F0 against the speaking-state or 'all' baseline)."""
        snap = self.baseline.snapshot
        if snap is None or not self.hops:
            return None
        sb = snap.signals.get("voice.f0_hz")
        if sb is None or not (math.isfinite(sb.center) and sb.scale > 0):
            return None
        t = np.array([h[0] for h in self.hops], dtype=np.int64)
        f0 = np.array([h[2] for h in self.hops], dtype=float)
        return t, (f0 - sb.center) / sb.scale

    def finish(self) -> list[Event]:
        if self.detector is not None:
            flushed = [e.model_copy(update={"source": "audio"}) for e in self.detector.flush()]
            self.events.extend(flushed)
            return flushed
        return []


def _yin_f0(win: npt.NDArray[np.float32], fmin: float, fmax: float) -> tuple[float, bool]:
    """Single-window YIN: returns (f0_hz, periodic). Periodic when the cumulative mean
    normalized difference trough is below 0.2 (a standard YIN voicing criterion)."""
    x = win.astype(np.float64)
    x = x - x.mean()
    n = x.size
    tau_min = max(2, int(RATE / fmax))
    tau_max = min(n // 2, int(RATE / fmin))
    if tau_max <= tau_min + 1:
        return 0.0, False
    w = n - tau_max
    seg = x[:w]
    d = np.empty(tau_max + 1)
    d[0] = 0.0
    for tau in range(1, tau_max + 1):
        diff = seg - x[tau : tau + w]
        d[tau] = float(np.dot(diff, diff))
    cum = np.cumsum(d[1:]) / np.arange(1, tau_max + 1)
    cmnd = np.ones(tau_max + 1)
    cmnd[1:] = d[1:] / np.maximum(cum, 1e-12)
    # absolute threshold step: first tau whose trough dips below 0.2, then descend to the local
    # minimum. Taking the global minimum instead would return octave errors on clean tones.
    below = np.nonzero(cmnd[tau_min : tau_max + 1] < 0.2)[0]
    if below.size:
        tau = int(below[0]) + tau_min
        while tau + 1 <= tau_max and cmnd[tau + 1] < cmnd[tau]:
            tau += 1
    else:
        tau = int(np.argmin(cmnd[tau_min : tau_max + 1])) + tau_min
    trough = float(cmnd[tau])
    # parabolic interpolation around the trough
    if 1 <= tau < tau_max:
        a, b, c = cmnd[tau - 1], cmnd[tau], cmnd[tau + 1]
        denom = a - 2 * b + c
        tau_f = tau + 0.5 * (a - c) / denom if abs(denom) > 1e-12 else float(tau)
    else:
        tau_f = float(tau)
    return RATE / tau_f, trough < 0.2
