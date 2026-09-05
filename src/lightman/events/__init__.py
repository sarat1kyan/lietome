"""Event generation from normalized signals: baseline deviations, blinks, co-occurrence."""

from lightman.events.blinks import detect_blinks
from lightman.events.deviation import cluster_cooccurring, detect_deviation_events

__all__ = ["cluster_cooccurring", "detect_blinks", "detect_deviation_events"]
