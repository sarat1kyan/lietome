"""Re-run baseline + event detection on a saved features.parquet with the current code/config.

    uv run python experiments/replay_events.py output/<session_id> [config.toml]

Prints event counts by signal and the severity distribution. Use it to tune floors and
thresholds against real sessions without re-running the models.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import numpy as np

from lightman.baseline import compute_leading_window_baseline
from lightman.config import LightmanConfig
from lightman.events import cluster_cooccurring, detect_blinks, detect_deviation_events
from lightman.features.table import SIGNAL_COLUMNS, read_feature_table


def main() -> None:
    session = Path(sys.argv[1])
    cfg = LightmanConfig.load(Path(sys.argv[2])) if len(sys.argv) > 2 else LightmanConfig()
    cols = read_feature_table(session / "features.parquet")
    t_us = cols["t_us"].astype(np.int64)
    quality = cols["quality"].astype(np.float64)
    signals = {n: cols[n].astype(np.float64) for n in SIGNAL_COLUMNS if n in cols}
    baseline = compute_leading_window_baseline(t_us, quality, signals, cfg.baseline)
    blinks = detect_blinks(
        t_us=t_us,
        quality=quality,
        ear=signals["eye.aspect_ratio_mean"],
        baseline=baseline,
        cfg=cfg.events,
        subject_id="s",
        extractor_id="replay",
    )
    dev = detect_deviation_events(
        t_us=t_us,
        quality=quality,
        signals=signals,
        baseline=baseline,
        cfg=cfg.events,
        subject_id="s",
        extractor_id="replay",
        id_start=len(blinks),
        exclude_intervals=[(b.start_us, b.end_us) for b in blinks],
    )
    clusters = cluster_cooccurring(dev, subject_id="s", extractor_id="replay", id_start=10_000)
    dur_s = (t_us[-1] - baseline.window_end_us) / 1e6 if t_us.size else 0
    print(
        f"frames {t_us.size}, post-baseline {dur_s:.0f} s, baseline quality {baseline.quality:.2f}"
    )
    print(f"blinks {len(blinks)}, deviation events {len(dev)}, clusters {len(clusters)}")
    print(f"events per minute after baseline: {60 * len(dev) / max(dur_s, 1):.1f}")
    sev = np.array([e.severity for e in dev]) if dev else np.zeros(0)
    if sev.size:
        p50, p90 = np.percentile(sev, [50, 90])
        print(f"severity p50 {p50:.1f}  p90 {p90:.1f}  max {sev.max():.1f}")
    by_sig = Counter(e.contributions[0].feature for e in dev)
    for name, n in by_sig.most_common():
        sb = baseline.signals[name]
        print(
            f"  {name:28s} {n:4d}  scale {sb.scale:.3f}{' (floored)' if sb.floor_applied else ''}"
        )


if __name__ == "__main__":
    main()
