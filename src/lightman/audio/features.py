"""Frame-level and segment-level vocal features from 16 kHz mono audio.

Frame level (hop 20 ms): RMS energy (dB), F0 (pyin, NaN when unvoiced), voicing probability.
Segment level (per VAD speech segment): duration, F0 statistics in semitones, energy, a
syllable-nuclei speech-rate proxy, pause before the segment, and *approximate* jitter/shimmer
computed from the frame-level F0/amplitude tracks (true cycle-level jitter needs glottal pulse
marking; the suffix "_approx" is deliberate).

None of these is a "stress" or "deception" measure. They are acoustic observations compared
against the speaker's own baseline downstream.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from lightman.audio.vad import SpeechSegment

RATE = 16_000
HOP_MS = 20
HOP = RATE * HOP_MS // 1000  # 320 samples
FRAME_LENGTH = 1024  # 64 ms analysis window for pyin
F0_MIN = 60.0
F0_MAX = 400.0
SILENCE_DB = -80.0


@dataclass(slots=True)
class FrameFeatures:
    t_us: npt.NDArray[np.int64]
    energy_db: npt.NDArray[np.float64]
    f0_hz: npt.NDArray[np.float64]
    voiced_prob: npt.NDArray[np.float64]
    speech_prob: npt.NDArray[np.float64]


@dataclass(slots=True)
class SegmentFeatures:
    start_us: int
    end_us: int
    duration_ms: float
    pause_before_ms: float | None
    f0_median_hz: float
    f0_std_semitones: float
    f0_range_semitones: float
    energy_mean_db: float
    voiced_fraction: float
    syllable_rate_hz: float
    jitter_local_approx: float
    shimmer_local_db_approx: float


def rms_db(
    x: npt.NDArray[np.float32], hop: int = HOP, frame: int = FRAME_LENGTH
) -> npt.NDArray[np.float64]:
    n = 1 + max(0, (x.size - 1) // hop)
    out = np.full(n, SILENCE_DB, dtype=np.float64)
    half = frame // 2
    for i in range(n):
        c = i * hop
        seg = x[max(0, c - half) : c + half]
        if seg.size:
            r = float(np.sqrt(np.mean(seg.astype(np.float64) ** 2)))
            out[i] = 20 * np.log10(r) if r > 1e-9 else SILENCE_DB
    return out


def compute_frame_features(
    samples: npt.NDArray[np.float32],
    *,
    origin_us: int,
    speech_probs: npt.NDArray[np.floating],
    chunk_us: int,
    f0_min: float = F0_MIN,
    f0_max: float = F0_MAX,
) -> FrameFeatures:
    import librosa

    x = np.asarray(samples, dtype=np.float32)
    if x.size < FRAME_LENGTH:
        x = np.pad(x, (0, FRAME_LENGTH - x.size))
    f0, _flag, vprob = librosa.pyin(
        x, fmin=f0_min, fmax=f0_max, sr=RATE, frame_length=FRAME_LENGTH, hop_length=HOP, center=True
    )
    n = f0.size
    t_us = origin_us + (np.arange(n, dtype=np.int64) * HOP * 1_000_000) // RATE
    energy = rms_db(x)
    energy = np.resize(energy, n) if energy.size != n else energy
    # speech prob per frame: nearest VAD chunk
    if speech_probs.size:
        idx = np.clip(((t_us - origin_us) // chunk_us).astype(np.int64), 0, speech_probs.size - 1)
        sp = np.asarray(speech_probs, dtype=np.float64)[idx]
    else:
        sp = np.zeros(n, dtype=np.float64)
    f0 = np.where(np.isfinite(f0), f0, np.nan).astype(np.float64)
    return FrameFeatures(
        t_us=t_us,
        energy_db=energy,
        f0_hz=f0,
        voiced_prob=np.asarray(vprob, dtype=np.float64),
        speech_prob=sp,
    )


def hz_to_semitones(f0: npt.NDArray[np.floating], ref_hz: float) -> npt.NDArray[np.float64]:
    return 12.0 * np.log2(np.asarray(f0, dtype=np.float64) / ref_hz)


def syllable_nuclei_count(energy_db: npt.NDArray[np.floating], *, hop_ms: int = HOP_MS) -> int:
    """Count energy peaks (syllable nuclei proxy): local maxima of a 60 ms-smoothed envelope
    at least 2 dB above the surrounding minima and >= 120 ms apart."""
    e = np.asarray(energy_db, dtype=np.float64)
    if e.size < 3:
        return 0
    k = max(1, 60 // hop_ms)
    kernel = np.ones(k) / k
    sm = np.convolve(e, kernel, mode="same")
    min_dist = max(1, 120 // hop_ms)
    peaks: list[int] = []
    for i in range(1, sm.size - 1):
        if sm[i] >= sm[i - 1] and sm[i] > sm[i + 1] and sm[i] > np.median(sm):
            if peaks and i - peaks[-1] < min_dist:
                if sm[i] > sm[peaks[-1]]:
                    peaks[-1] = i
                continue
            left = sm[max(0, i - min_dist) : i].min()
            right = sm[i + 1 : i + 1 + min_dist].min()
            if sm[i] - max(left, right) >= 2.0:
                peaks.append(i)
    return len(peaks)


def compute_segment_features(
    frames: FrameFeatures, segments: list[SpeechSegment]
) -> list[SegmentFeatures]:
    out: list[SegmentFeatures] = []
    prev_end: int | None = None
    for seg in segments:
        m = (frames.t_us >= seg.start_us) & (frames.t_us < seg.end_us)
        f0 = frames.f0_hz[m]
        e = frames.energy_db[m]
        voiced = np.isfinite(f0)
        dur_ms = (seg.end_us - seg.start_us) / 1000
        if voiced.sum() >= 3:
            fv = f0[voiced]
            med = float(np.median(fv))
            st = hz_to_semitones(fv, med)
            f0_std = float(np.std(st))
            f0_range = float(np.percentile(st, 95) - np.percentile(st, 5))
            periods = 1.0 / fv
            jitter = float(np.mean(np.abs(np.diff(periods))) / np.mean(periods))
            amp = 10 ** (e[voiced] / 20)
            shimmer_db = (
                float(np.mean(np.abs(20 * np.log10(amp[1:] / amp[:-1])))) if amp.size > 1 else 0.0
            )
        else:
            med = f0_std = f0_range = jitter = shimmer_db = float("nan")
        out.append(
            SegmentFeatures(
                start_us=seg.start_us,
                end_us=seg.end_us,
                duration_ms=dur_ms,
                pause_before_ms=(seg.start_us - prev_end) / 1000 if prev_end is not None else None,
                f0_median_hz=med,
                f0_std_semitones=f0_std,
                f0_range_semitones=f0_range,
                energy_mean_db=float(np.mean(e)) if e.size else float("nan"),
                voiced_fraction=float(voiced.mean()) if voiced.size else 0.0,
                syllable_rate_hz=(syllable_nuclei_count(e) / (dur_ms / 1000))
                if dur_ms > 0
                else 0.0,
                jitter_local_approx=jitter,
                shimmer_local_db_approx=shimmer_db,
            )
        )
        prev_end = seg.end_us
    return out


def audio_quality(
    samples: npt.NDArray[np.float32], speech_probs: npt.NDArray[np.floating], chunk: int
) -> dict[str, float]:
    """SNR estimate (speech vs non-speech chunk energy) and clipping fraction."""
    x = np.asarray(samples, dtype=np.float64)
    n = min(speech_probs.size, x.size // chunk)
    if n == 0:
        return {"snr_db": float("nan"), "clipping_fraction": 0.0, "speech_fraction": 0.0}
    chunks = x[: n * chunk].reshape(n, chunk)
    power = np.mean(chunks**2, axis=1) + 1e-12
    sp = np.asarray(speech_probs[:n]) >= 0.5
    if sp.any() and (~sp).any():
        snr = 10 * np.log10(np.mean(power[sp]) / np.mean(power[~sp]))
    else:
        snr = float("nan")
    return {
        "snr_db": float(snr),
        "clipping_fraction": float(np.mean(np.abs(x) >= 0.99)),
        "speech_fraction": float(sp.mean()),
    }
