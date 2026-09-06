"""Subject-specific baseline modeling. V0.1: robust statistics over a leading window."""

from lightman.baseline.robust import (
    BaselineSnapshot,
    SignalBaseline,
    compute_leading_window_baseline,
    compute_state_baselines,
    per_frame_center_scale,
    robust_z,
)

__all__ = [
    "BaselineSnapshot",
    "SignalBaseline",
    "compute_leading_window_baseline",
    "compute_state_baselines",
    "per_frame_center_scale",
    "robust_z",
]
