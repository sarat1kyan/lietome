import numpy as np

from lightman.baseline.adaptive import (
    AdaptiveBaseline,
    AdaptiveConfig,
    adaptive_center_scale_arrays,
)
from lightman.baseline.robust import BaselineSnapshot, SignalBaseline


def _snap(center: float, scale: float, state: str = "all") -> BaselineSnapshot:
    return BaselineSnapshot(
        mode="leading_window",
        state=state,
        window_start_us=0,
        window_end_us=40_000_000,
        frames_in_window=100,
        frames_used=100,
        quality=0.8,
        signals={
            "x": SignalBaseline(
                feature="x",
                unit="coefficient",
                center=center,
                scale=scale,
                n=100,
                floor_applied=False,
            )
        },
    )


def test_scale_grows_to_the_wider_conversational_range_but_is_bounded() -> None:
    cfg = AdaptiveConfig(half_life_s=10.0, max_scale_ratio=3.0)
    ab = AdaptiveBaseline({"all": _snap(0.0, 0.03)}, cfg)
    rng = np.random.default_rng(0)
    t = 0
    for _ in range(3000):  # 100 s at 30 fps of a wider but centered signal
        t += 33_333
        ab.update("all", t, {"x": float(rng.normal(0.0, 0.06))})
    c, s = ab.center_scale("all", "x")
    assert abs(c) < 0.02
    assert 0.05 < s <= 0.09  # tracked toward 0.06, capped at 3 x anchor


def test_center_shift_is_bounded_and_excursions_do_not_update() -> None:
    cfg = AdaptiveConfig(half_life_s=5.0, max_center_shift=2.0, update_z_max=2.5)
    ab = AdaptiveBaseline({"all": _snap(0.0, 0.03)}, cfg)
    t = 0
    for _ in range(3000):
        t += 33_333
        ab.update("all", t, {"x": 0.05})  # slow drift target within update range
    c, _ = ab.center_scale("all", "x")
    assert c <= 0.06 + 1e-9  # bounded at anchor + 2 scales
    ab2 = AdaptiveBaseline({"all": _snap(0.0, 0.03)}, cfg)
    t = 0
    for _ in range(300):
        t += 33_333
        ab2.update("all", t, {"x": 0.9})  # a large excursion: |z| >> update_z_max
    c2, s2 = ab2.center_scale("all", "x")
    assert c2 == 0.0  # center never moved toward the excursion
    assert s2 <= 0.03 * 4.0  # scale learning is clipped and capped


def test_offline_arrays_start_after_window_and_track_state() -> None:
    n = 900
    t_us = (np.arange(n) * 33_333).astype(np.int64)
    values = np.concatenate([np.zeros(300), np.full(600, 0.04)])
    frame_state = np.array(["all"] * n)
    center, scale = adaptive_center_scale_arrays(
        t_us,
        values,
        frame_state,
        {"all": _snap(0.0, 0.03)},
        "x",
        AdaptiveConfig(half_life_s=5.0),
        start_us=int(t_us[299]),
    )
    assert center[0] == 0.0 and scale[0] == 0.03
    assert center[-1] > 0.03 and scale[-1] >= 0.03
    assert np.all(np.isfinite(center)) and np.all(scale >= 0.03)
