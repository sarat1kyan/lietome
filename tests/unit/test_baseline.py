import math

import numpy as np
from hypothesis import given
from hypothesis import strategies as st

from lightman.baseline.robust import (
    MAD_TO_SIGMA,
    compute_leading_window_baseline,
    robust_center_scale,
    robust_z,
)
from lightman.config import BaselineConfig


def test_median_mad_resists_contamination() -> None:
    rng = np.random.default_rng(1)
    clean = rng.normal(0.2, 0.02, 500)
    contaminated = clean.copy()
    contaminated[:50] = 5.0  # 10% gross outliers (e.g. tracking glitches)
    c1, s1, *_ = robust_center_scale(clean, "coefficient")
    c2, s2, *_ = robust_center_scale(contaminated, "coefficient")
    assert abs(c1 - c2) < 0.01
    assert s2 < 1.5 * s1


def test_scale_floor_applied_for_constant_signal() -> None:
    c, s, n, floored = robust_center_scale(np.full(100, 0.3), "coefficient")
    assert c == 0.3 and s == 0.03 and n == 100 and floored


def test_zero_inflated_signal_does_not_collapse_scale() -> None:
    """A resting jawOpen is 0 most of the time with brief excursions: MAD alone says 0."""
    x = np.zeros(600)
    x[::5] = 0.4  # 20% excursions (talking during calibration)
    _c, s, _n, floored = robust_center_scale(x, "coefficient")
    assert s > 0.03 and not floored  # winsorized SD keeps a meaningful spread


def test_nan_handling() -> None:
    c, s, n, _ = robust_center_scale(np.array([np.nan, np.nan]), "deg")
    assert math.isnan(c) and math.isnan(s) and n == 0
    z = robust_z(np.array([1.0, 2.0]), c, s)
    assert np.isnan(z).all()


@given(st.lists(st.floats(-50, 50, allow_nan=False), min_size=20, max_size=200))
def test_robust_z_is_zero_at_median(values: list[float]) -> None:
    x = np.asarray(values)
    c, s, *_ = robust_center_scale(x, "deg")
    z = robust_z(np.array([c]), c, s)
    assert z[0] == 0.0
    # scaled MAD is a consistent sigma estimator: normal data -> ~1
    assert s >= 0.5  # floor for degrees


def test_leading_window_baseline_quality_and_notes() -> None:
    n = 300
    t_us = (np.arange(n) * 33_333).astype(np.int64)  # 10 s @ 30 fps
    quality = np.ones(n)
    quality[:20] = 0.1  # poor start
    sig = {"blendshape.jawOpen": np.random.default_rng(0).normal(0.1, 0.02, n)}
    cfg = BaselineConfig(window_s=30.0, min_samples=60, good_samples=600, min_quality=0.5)
    b = compute_leading_window_baseline(t_us, quality, sig, cfg)
    assert b.frames_in_window == n
    assert b.frames_used == n - 20
    assert 0 < b.quality < 1
    assert any("shorter than the baseline window" in x for x in b.notes)
    sb = b.signals["blendshape.jawOpen"]
    assert abs(sb.center - 0.1) < 0.01
    assert abs(sb.scale - 0.02) < 0.015 or sb.floor_applied
    assert MAD_TO_SIGMA == 1.4826


def test_window_restricts_samples() -> None:
    n = 3000
    t_us = (np.arange(n) * 33_333).astype(np.int64)  # 100 s
    quality = np.ones(n)
    values = np.concatenate([np.zeros(900), np.ones(n - 900)])
    cfg = BaselineConfig(window_s=30.0)
    b = compute_leading_window_baseline(t_us, quality, {"head.yaw_deg": values}, cfg)
    assert b.frames_used == 901  # t <= 30 s inclusive
    assert b.signals["head.yaw_deg"].center == 0.0
