"""Self-contained HTML report: inline CSS, inline SVG timelines, base64 thumbnails.

No JavaScript frameworks or CDN assets: the report must open offline, from a USB stick,
years later, exactly as generated. Charts are plain SVG generated here.
"""

from __future__ import annotations

import base64
import math
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from jinja2 import Environment, PackageLoader, select_autoescape

from lightman.baseline.robust import BaselineSnapshot, robust_z
from lightman.core.timebase import format_timecode
from lightman.schema import Event, MediaInfo, QualitySummary

_env = Environment(
    loader=PackageLoader("lightman.report", "templates"),
    autoescape=select_autoescape(["html"]),
)
_env.filters["tc"] = format_timecode

PLOT_W, PLOT_H, PAD_L, PAD_R, PAD_T, PAD_B = 1100, 90, 60, 20, 8, 22
MAX_POINTS = 1400


def _downsample(x: npt.NDArray[np.floating], n: int) -> npt.NDArray[np.floating]:
    if x.shape[0] <= n:
        return x
    idx = np.linspace(0, x.shape[0] - 1, n).astype(int)
    out: npt.NDArray[np.floating] = x[idx]
    return out


def _polyline(
    t_s: npt.NDArray[np.floating], z: npt.NDArray[np.floating], t_max: float, zlim: float
) -> str:
    inner_w = PLOT_W - PAD_L - PAD_R
    inner_h = PLOT_H - PAD_T - PAD_B
    pts: list[str] = []
    segments: list[str] = []
    for tt, zz in zip(t_s, z, strict=True):
        if not math.isfinite(zz):
            if pts:
                segments.append(" ".join(pts))
                pts = []
            continue
        x = PAD_L + (tt / t_max) * inner_w if t_max > 0 else PAD_L
        zc = max(-zlim, min(zlim, zz))
        y = PAD_T + (1 - (zc + zlim) / (2 * zlim)) * inner_h
        pts.append(f"{x:.1f},{y:.1f}")
    if pts:
        segments.append(" ".join(pts))
    return "".join(
        f'<polyline points="{s}" fill="none" stroke="var(--line)" stroke-width="1.2"/>'
        for s in segments
    )


def _signal_svg(
    name: str,
    t_us: npt.NDArray[np.integer],
    values: npt.NDArray[np.floating],
    baseline: BaselineSnapshot,
    events: list[Event],
    z_enter: float,
) -> str:
    sb = baseline.signals.get(name)
    if sb is None or not math.isfinite(sb.center):
        return ""
    z = robust_z(values, sb.center, sb.scale)
    t_s = t_us.astype(np.float64) / 1e6
    t_max = float(t_s[-1]) if t_s.size else 1.0
    zlim = 6.0
    inner_w = PLOT_W - PAD_L - PAD_R
    inner_h = PLOT_H - PAD_T - PAD_B

    def ypos(zv: float) -> float:
        return PAD_T + (1 - (zv + zlim) / (2 * zlim)) * inner_h

    parts = [f'<svg viewBox="0 0 {PLOT_W} {PLOT_H}" class="signal" role="img" aria-label="{name}">']
    parts.append(
        f'<rect x="{PAD_L}" y="{PAD_T}" width="{inner_w}" height="{inner_h}" class="plotbg"/>'
    )
    # baseline window shading
    bw = (baseline.window_end_us / 1e6) / t_max * inner_w if t_max > 0 else 0
    parts.append(
        f'<rect x="{PAD_L}" y="{PAD_T}" width="{bw:.1f}" height="{inner_h}" class="basewin"/>'
    )
    for zv, cls in ((0.0, "zero"), (z_enter, "thr"), (-z_enter, "thr")):
        y = f"{ypos(zv):.1f}"
        parts.append(f'<line x1="{PAD_L}" x2="{PAD_L + inner_w}" y1="{y}" y2="{y}" class="{cls}"/>')
    for e in events:
        if not any(c.feature == name for c in e.contributions):
            continue
        x0 = PAD_L + (e.start_us / 1e6) / t_max * inner_w if t_max > 0 else PAD_L
        x1 = PAD_L + (e.end_us / 1e6) / t_max * inner_w if t_max > 0 else PAD_L
        parts.append(
            f'<rect x="{x0:.1f}" y="{PAD_T}" width="{max(1.5, x1 - x0):.1f}" '
            f'height="{inner_h}" class="ev {e.event_type}"/>'
        )
    parts.append(_polyline(_downsample(t_s, MAX_POINTS), _downsample(z, MAX_POINTS), t_max, zlim))
    parts.append(
        f'<text x="4" y="{ypos(zlim) + 10:.0f}" class="ax">+{zlim:.0f} SD</text>'
        f'<text x="4" y="{ypos(0) + 4:.0f}" class="ax">0</text>'
        f'<text x="4" y="{ypos(-zlim):.0f}" class="ax">-{zlim:.0f} SD</text>'
    )
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        x = PAD_L + frac * inner_w
        parts.append(
            f'<text x="{x:.0f}" y="{PLOT_H - 6}" class="ax" text-anchor="middle">'
            f"{format_timecode(int(frac * t_max * 1e6))}</text>"
        )
    parts.append("</svg>")
    return "".join(parts)


def _b64_png(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def render_report(
    *,
    dest: Path,
    media: MediaInfo,
    summary: dict[str, Any],
    quality: QualitySummary,
    baseline: BaselineSnapshot,
    events: list[Event],
    table: dict[str, npt.NDArray[np.generic]],
    thumbnails: dict[str, Path],
    disclaimer: str,
    signals_to_plot: list[str],
    z_enter: float = 3.0,
) -> None:
    t_us = table["t_us"].astype(np.int64)
    plots = []
    for name in signals_to_plot:
        if name in table:
            svg = _signal_svg(name, t_us, table[name].astype(np.float64), baseline, events, z_enter)
            if svg:
                plots.append({"name": name, "svg": svg, "baseline": baseline.signals[name]})
    non_blink = [e for e in events if e.event_type != "blink"]
    ranked = sorted(non_blink, key=lambda e: e.severity, reverse=True)
    template = _env.get_template("report.html.j2")
    html = template.render(
        media=media,
        summary=summary,
        quality=quality,
        baseline=baseline,
        events=ranked,
        blink_count=summary.get("blink_count", 0),
        plots=plots,
        thumbs={k: _b64_png(v) for k, v in thumbnails.items() if v.exists()},
        disclaimer=disclaimer,
    )
    dest.write_text(html, "utf-8")
