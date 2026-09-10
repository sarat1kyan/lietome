"""Remote photoplethysmography (rPPG): a camera-based pulse-rate estimate.

Skin color flickers slightly with each heartbeat. Averaging skin pixels over a stable region
(forehead, cheeks) and projecting the color trace onto a pulse-sensitive direction (POS,
Wang et al. 2017) yields a periodic signal whose dominant frequency in 0.7-3.0 Hz is the pulse
rate. It is an *estimate*: motion, lighting changes, low frame rate and darker skin tones (lower
signal-to-noise; Nowara et al. 2020) all degrade it. Every estimate carries an SNR and is
dropped below a threshold rather than shown.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from lightman.schema.events import Event, EvidenceLevel, FeatureContribution

# MediaPipe FaceMesh indices bounding the forehead (between the brows and the hairline) and
# the two cheek centers.
_FOREHEAD_TOP = 10
_BROW_L, _BROW_R = 105, 334
_TEMPLE_L, _TEMPLE_R = 70, 300
_CHEEK_L, _CHEEK_R = 50, 280

BAND_HZ = (0.7, 3.0)
RESAMPLE_HZ = 15.0


def skin_means(
    rgb: npt.NDArray[np.uint8], landmarks: npt.NDArray[np.floating], w: int, h: int
) -> tuple[float, float, float]:
    """Mean R, G, B over forehead + both cheeks. NaN triple when the ROI is empty."""
    lm = landmarks
    fx0 = int(lm[_TEMPLE_L, 0] * w)
    fx1 = int(lm[_TEMPLE_R, 0] * w)
    fy0 = int(lm[_FOREHEAD_TOP, 1] * h)
    fy1 = int(min(lm[_BROW_L, 1], lm[_BROW_R, 1]) * h)
    face_w = max(1.0, float(lm[:, 0].max() - lm[:, 0].min()) * w)
    half = int(0.07 * face_w)
    rois = [(fx0, fy0, fx1, fy1)]
    for idx in (_CHEEK_L, _CHEEK_R):
        cx, cy = int(lm[idx, 0] * w), int(lm[idx, 1] * h)
        rois.append((cx - half, cy - half, cx + half, cy + half))
    acc = np.zeros(3, dtype=np.float64)
    count = 0
    for ax, ay, bx, by in rois:
        x0, x1 = max(0, min(ax, bx)), min(w, max(ax, bx))
        y0, y1 = max(0, min(ay, by)), min(h, max(ay, by))
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        patch = rgb[y0:y1, x0:x1].reshape(-1, 3)
        acc += patch.sum(axis=0, dtype=np.float64)
        count += patch.shape[0]
    if count == 0:
        return (math.nan, math.nan, math.nan)
    r, g, b = acc / count
    return (float(r), float(g), float(b))


@dataclass(frozen=True, slots=True)
class PulseEstimate:
    t_us: int
    bpm: float
    snr_db: float


def _pos_pulse(rgb: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Plane-orthogonal-to-skin projection of an (n, 3) normalized color trace."""
    c = rgb / np.maximum(rgb.mean(axis=0), 1e-6)
    s1 = c[:, 1] - c[:, 2]
    s2 = c[:, 1] + c[:, 2] - 2.0 * c[:, 0]
    sd2 = float(np.std(s2))
    h = s1 + (float(np.std(s1)) / sd2) * s2 if sd2 > 1e-9 else s1
    return h - h.mean()


def _detrend(x: npt.NDArray[np.float64], fs: float, win_s: float = 1.0) -> npt.NDArray[np.float64]:
    """Remove a moving mean (slow lighting and posture drift) before spectral analysis."""
    k = max(3, int(win_s * fs) | 1)
    pad = np.pad(x, k // 2, mode="edge")
    ma = np.convolve(pad, np.ones(k) / k, mode="valid")
    return x - ma


def _dominant_frequency(x: npt.NDArray[np.float64], fs: float) -> tuple[float, float]:
    """(peak frequency in the pulse band, SNR in dB: peak and its harmonic vs the rest of the band).

    Follows de Haan & Jeanne (2013): signal power within +-0.15 Hz of the peak and of its first
    harmonic against everything else in the band.
    """
    n = x.size
    win = np.hanning(n)
    spec = np.abs(np.fft.rfft((x - x.mean()) * win)) ** 2
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    band = (freqs >= BAND_HZ[0]) & (freqs <= BAND_HZ[1])
    if not band.any():
        return math.nan, -math.inf
    p = spec[band]
    f = freqs[band]
    k = int(np.argmax(p))
    peak_f = float(f[k])
    near = (np.abs(f - peak_f) <= 0.15) | (np.abs(f - 2.0 * peak_f) <= 0.15)
    sig = float(p[near].sum())
    rest = float(p[~near].sum())
    snr = 10.0 * math.log10(sig / rest) if rest > 0 else math.inf
    return peak_f, snr


def estimate_pulse(
    t_us: npt.NDArray[np.integer],
    r: npt.NDArray[np.floating],
    g: npt.NDArray[np.floating],
    b: npt.NDArray[np.floating],
    quality: npt.NDArray[np.floating],
    *,
    window_s: float = 10.0,
    step_s: float = 1.0,
    min_quality: float = 0.4,
    min_coverage: float = 0.8,
) -> list[PulseEstimate]:
    """Sliding-window pulse estimates; one per ``step_s`` with a valid window."""
    t = np.asarray(t_us, dtype=np.int64)
    if t.size < 2:
        return []
    rgb = np.column_stack([r, g, b]).astype(np.float64)
    ok = np.isfinite(rgb).all(axis=1) & (np.asarray(quality, dtype=float) >= min_quality)
    out: list[PulseEstimate] = []
    win_us = int(window_s * 1e6)
    step_us = int(step_s * 1e6)
    n_res = int(window_s * RESAMPLE_HZ)
    start = int(t[0])
    end = start + win_us
    while end <= int(t[-1]):
        m = (t >= start) & (t < end)
        if m.sum() >= 8:
            mt, mok = t[m], ok[m]
            if mok.mean() >= min_coverage and mok.sum() >= 8:
                grid = np.linspace(start, end, n_res, endpoint=False)
                res = np.column_stack(
                    [np.interp(grid, mt[mok], rgb[m][mok][:, ch]) for ch in range(3)]
                )
                pulse = _detrend(_pos_pulse(res), RESAMPLE_HZ)
                f, snr = _dominant_frequency(pulse, RESAMPLE_HZ)
                if math.isfinite(f):
                    out.append(PulseEstimate(t_us=end, bpm=60.0 * f, snr_db=snr))
        start += step_us
        end += step_us
    return out


def pulse_events(
    estimates: list[PulseEstimate],
    *,
    subject_id: str,
    extractor_id: str,
    baseline_quality: float,
    id_start: int,
    min_snr_db: float = 3.0,
    reference_s: float = 30.0,
    min_change_bpm: float = 10.0,
    min_sustain_s: float = 5.0,
) -> tuple[list[Event], dict[str, float | None]]:
    """Sustained pulse-estimate changes against the first ``reference_s`` of usable estimates.

    Returns (events, summary) where summary has reference_bpm, median_bpm, usable_fraction.
    """
    good = [e for e in estimates if e.snr_db >= min_snr_db]
    summary: dict[str, float | None] = {
        "reference_bpm": None,
        "median_bpm": None,
        "usable_fraction": (len(good) / len(estimates)) if estimates else None,
    }
    if len(good) < 5:
        return [], summary
    t0 = good[0].t_us
    ref = [e.bpm for e in good if e.t_us <= t0 + int(reference_s * 1e6)]
    if len(ref) < 3:
        return [], summary
    ref_bpm = float(np.median(ref))
    summary["reference_bpm"] = round(ref_bpm, 1)
    summary["median_bpm"] = round(float(np.median([e.bpm for e in good])), 1)
    events: list[Event] = []
    k = id_start
    run: list[PulseEstimate] = []

    def close() -> None:
        nonlocal k, run
        if run and (run[-1].t_us - run[0].t_us) >= int(min_sustain_s * 1e6):
            bpm = float(np.median([e.bpm for e in run]))
            up = bpm > ref_bpm
            events.append(
                Event(
                    event_id=f"ev_{k:05d}",
                    subject_id=subject_id,
                    source="video",
                    event_type="pulse_change",
                    level=EvidenceLevel.OBSERVATION,
                    start_us=run[0].t_us,
                    end_us=run[-1].t_us,
                    peak_us=run[0].t_us,
                    label=(
                        f"pulse estimate {'up' if up else 'down'}: {bpm:.0f} vs {ref_bpm:.0f} bpm"
                    ),
                    description=(
                        f"Camera-based pulse estimate (rPPG) stayed near {bpm:.0f} bpm for "
                        f"{(run[-1].t_us - run[0].t_us) / 1e6:.0f} s against a reference of "
                        f"{ref_bpm:.0f} bpm from the first {reference_s:.0f} s. The estimate "
                        "depends on lighting, stillness and skin tone; it is not a medical "
                        "measurement and changes with movement, speech and posture."
                    ),
                    contributions=[
                        FeatureContribution(
                            feature="pulse.bpm",
                            unit="bpm",
                            peak_value=bpm,
                            baseline_center=ref_bpm,
                            baseline_scale=max(3.0, 0.08 * ref_bpm),
                            peak_deviation=(bpm - ref_bpm) / max(3.0, 0.08 * ref_bpm),
                            direction="increase" if up else "decrease",
                        )
                    ],
                    severity=round(abs(bpm - ref_bpm) / max(3.0, 0.08 * ref_bpm), 2),
                    confidence=round(
                        0.6 * min(1.0, float(np.mean([e.snr_db for e in run])) / 10.0), 3
                    ),
                    quality=1.0,
                    baseline_quality=baseline_quality,
                    extractor_id=extractor_id,
                    tags=["pulse", "rppg"],
                )
            )
            k += 1
        run = []

    for e in good:
        if e.t_us <= t0 + int(reference_s * 1e6):
            continue
        if abs(e.bpm - ref_bpm) >= min_change_bpm and (
            not run or (e.bpm > ref_bpm) == (run[0].bpm > ref_bpm)
        ):
            run.append(e)
        else:
            close()
            if abs(e.bpm - ref_bpm) >= min_change_bpm:
                run.append(e)
    close()
    return events, summary


class StreamingPulse:
    """Keeps recent skin means and re-estimates the pulse every ``step_s`` for the live HUD."""

    def __init__(self, *, window_s: float = 10.0, step_s: float = 1.0, min_quality: float = 0.4):
        self.window_us = int(window_s * 1e6)
        self.step_us = int(step_s * 1e6)
        self.min_quality = min_quality
        self.window_s = window_s
        self._t: list[int] = []
        self._rgb: list[tuple[float, float, float]] = []
        self._q: list[float] = []
        self._next_us: int | None = None
        self.estimates: list[PulseEstimate] = []
        self.latest: PulseEstimate | None = None

    def push(
        self, t_us: int, rgb: tuple[float, float, float], quality: float
    ) -> PulseEstimate | None:
        self._t.append(t_us)
        self._rgb.append(rgb)
        self._q.append(quality)
        while self._t and self._t[0] < t_us - self.window_us - 200_000:
            self._t.pop(0)
            self._rgb.pop(0)
            self._q.pop(0)
        if self._next_us is None:
            self._next_us = t_us + self.window_us
        if t_us < self._next_us:
            return None
        self._next_us = t_us + self.step_us
        arr = np.asarray(self._rgb, dtype=np.float64)
        est = estimate_pulse(
            np.asarray(self._t, dtype=np.int64),
            arr[:, 0],
            arr[:, 1],
            arr[:, 2],
            np.asarray(self._q, dtype=np.float64),
            window_s=self.window_s,
            step_s=self.window_s,
            min_quality=self.min_quality,
        )
        if not est:
            return None
        self.latest = est[-1]
        self.estimates.append(self.latest)
        return self.latest
