"""Blink-rate change events.

Blink rate is one of the few facial measures with a real literature on cognitive load and
arousal, in both directions (suppression while concentrating, increase after). Even so, the
event here says only "blink rate over the last 30 s is far from this person's reference rate".
Reference = blinks in the first ``reference_s`` after the blink detector is armed.
"""

from __future__ import annotations

from lightman.schema.events import Event, EvidenceLevel, FeatureContribution

WINDOW_S = 30.0
STEP_S = 5.0
REFERENCE_S = 60.0
HIGH_RATIO = 2.0
LOW_RATIO = 0.4
MIN_ABS_DIFF_PER_MIN = 8.0


def blink_rate_events(
    blink_times_us: list[int],
    *,
    start_us: int,
    end_us: int,
    subject_id: str,
    extractor_id: str,
    baseline_quality: float,
    id_start: int,
    reference_s: float = REFERENCE_S,
) -> list[Event]:
    """Detect sustained windows whose blink rate is far from the reference rate."""
    ref_end = start_us + int(reference_s * 1e6)
    if end_us <= ref_end + int(WINDOW_S * 1e6):
        return []
    ref_blinks = sum(1 for t in blink_times_us if start_us <= t < ref_end)
    ref_rate = ref_blinks / (reference_s / 60.0)
    if ref_rate <= 0:
        ref_rate = 0.5  # avoid division by zero; treat as very low reference
    out: list[Event] = []
    k = id_start
    open_run: list[tuple[int, int, float]] = []

    def close_run() -> None:
        nonlocal k
        if not open_run:
            return
        s = open_run[0][0]
        e = open_run[-1][1]
        rates = [r for _, _, r in open_run]
        rate = max(rates) if open_run[0][2] > ref_rate else min(rates)
        up = rate > ref_rate
        out.append(
            Event(
                event_id=f"ev_{k:05d}",
                subject_id=subject_id,
                source="video",
                event_type="blink_rate_change",
                level=EvidenceLevel.INTERPRETATION,
                start_us=s,
                end_us=e,
                peak_us=s,
                label=(
                    f"blink rate {'elevated' if up else 'reduced'}: "
                    f"{rate:.0f}/min vs {ref_rate:.0f}/min"
                ),
                description=(
                    f"Blinks per minute over 30 s windows were {rate:.0f} against a "
                    f"reference of {ref_rate:.0f} measured in the first {reference_s:.0f} s "
                    "after calibration. "
                    "Blink rate varies with attention, dryness, screen use and speech; no "
                    "specific cause is implied."
                ),
                contributions=[
                    FeatureContribution(
                        feature="blink.rate_per_min",
                        unit="per_min",
                        peak_value=rate,
                        baseline_center=ref_rate,
                        baseline_scale=max(1.0, ref_rate * 0.5),
                        peak_deviation=(rate - ref_rate) / max(1.0, ref_rate * 0.5),
                        direction="increase" if up else "decrease",
                    )
                ],
                severity=abs(rate - ref_rate) / max(1.0, ref_rate * 0.5),
                confidence=0.8,
                quality=1.0,
                baseline_quality=baseline_quality,
                extractor_id=extractor_id,
                tags=["eye", "rate"],
            )
        )
        k += 1
        open_run.clear()

    t = ref_end
    while t + int(WINDOW_S * 1e6) <= end_us:
        w0, w1 = t, t + int(WINDOW_S * 1e6)
        n = sum(1 for b in blink_times_us if w0 <= b < w1)
        rate = n / (WINDOW_S / 60.0)
        high = rate >= HIGH_RATIO * ref_rate and rate - ref_rate >= MIN_ABS_DIFF_PER_MIN
        low = rate <= LOW_RATIO * ref_rate and ref_rate - rate >= MIN_ABS_DIFF_PER_MIN
        if high or low:
            if open_run and ((open_run[0][2] > ref_rate) != high):
                close_run()
            open_run.append((w0, w1, rate))
        else:
            close_run()
        t += int(STEP_S * 1e6)
    close_run()
    return out
