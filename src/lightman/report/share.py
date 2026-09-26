"""Standalone, shareable session report: one HTML file with everything a reviewer needs.

Built from a finished session directory (analysis.json, events.json, protocol.json,
thumbnails/). Images are embedded, nothing is fetched, so the file can be sent or opened
offline. It contains face thumbnails at key moments: share it only with the person it shows.
"""

from __future__ import annotations

import base64
import html
import json
from pathlib import Path
from typing import Any

from lightman.core.timebase import format_timecode

_CSS = (Path(__file__).parent / "templates" / "share.css").read_text("utf-8")

KEY_TYPES = {
    "episode",
    "multi_signal_deviation",
    "expression_pattern",
    "head_gesture",
    "au_novelty",
    "pulse_change",
    "blink_rate_change",
    "gaze_away",
    "stillness",
}
META_TAGS = {"expression", "brief", "fast_onset", "negative", "positive", "neutral"}


def _read(d: Path, name: str) -> Any:
    p = d / name
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _e(s: Any) -> str:
    return html.escape(str(s if s is not None else ""))


def key_moments(events: list[dict[str, Any]], n: int = 8) -> list[dict[str, Any]]:
    """Largest changes, at most one per 15 s, in time order."""
    ranked = sorted(
        (e for e in events if e["event_type"] in KEY_TYPES), key=lambda e: -e["severity"]
    )
    taken: set[int] = set()
    out: list[dict[str, Any]] = []
    for e in ranked:
        b = e["start_us"] // 15_000_000
        if b in taken:
            continue
        taken.add(b)
        out.append(e)
        if len(out) >= n:
            break
    return sorted(out, key=lambda e: e["start_us"])


def _img(d: Path, event_id: str) -> str:
    p = d / "thumbnails" / f"{event_id}.jpg"
    if not p.is_file() or p.stat().st_size > 400_000:
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode("ascii")


def _band_color(v: float | None) -> str:
    if v is None:
        return "var(--muted)"
    return (
        "var(--cool)"
        if v < 40
        else "var(--muted)"
        if v < 55
        else "var(--accent)"
        if v < 70
        else "var(--warn)"
    )


def _gauge(idx: dict[str, Any] | None, label: str) -> str:
    if not idx or idx.get("value") is None:
        return (
            f'<div class="gauge"><span class="k">{_e(label)}</span><span class="v">n/a</span></div>'
        )
    v = float(idx["value"])
    return (
        f'<div class="gauge"><span class="k">{_e(label)}</span>'
        f'<span class="v" style="color:{_band_color(v)}">{v:.0f}<small>/100</small> {_e(idx.get("band"))}</span>'
        f'<span class="track"><i style="left:{v:.1f}%"></i></span>'
        f'<span class="sub">reliability {idx.get("reliability", 0):.2f}'
        + (
            f"; moved with lying: {_e(', '.join(idx.get('drivers', [])))}"
            if idx.get("drivers")
            else ""
        )
        + "</span></div>"
    )


def render_share_report(session_dir: Path) -> str:
    d = session_dir
    a = _read(d, "analysis.json") or {}
    m = _read(d, "manifest.json") or {}
    events: list[dict[str, Any]] = (_read(d, "events.json") or {}).get("events", [])
    proto = _read(d, "protocol.json")
    counts = a.get("event_counts") or {}
    subject = (m.get("subject_ids") or ["subject"])[0]
    dur = format_timecode(int(a.get("duration_us") or 0))
    created = str(m.get("created_utc") or "")[:16].replace("T", " ")
    patterns: dict[str, int] = {}
    for e in events:
        if e["event_type"] == "expression_pattern":
            name = next((t for t in e["tags"] if t not in META_TAGS), "pattern")
            patterns[name] = patterns.get(name, 0) + 1
    moments = key_moments(events)
    parts: list[str] = []
    parts.append(
        f"<header><div class='eyebrow'>Lightman session report</div><h1>{_e(subject)}, {_e(dur)}</h1>"
        f"<p class='meta'>{_e(created)} UTC, {_e(a.get('mode', 'prerecorded'))} session "
        f"{_e(d.name)}</p></header>"
    )
    parts.append(
        "<p class='caveat'>Measurements of face, head, eyes, voice and pulse against this "
        "person's own baseline. Nothing here identifies an emotion, an intention or a lie. "
        "Indices are weighted shares of weak research cues, not probabilities.</p>"
    )
    stats = [
        ("episodes", counts.get("episode", 0)),
        ("deviations", counts.get("baseline_deviation", 0)),
        ("expression patterns", counts.get("expression_pattern", 0)),
        ("gaze away", counts.get("gaze_away", 0)),
        ("gestures", counts.get("head_gesture", 0)),
        ("blinks", counts.get("blink", 0)),
    ]
    parts.append(
        "<section class='stats'>"
        + "".join(f"<div><b>{_e(v)}</b><span>{_e(k)}</span></div>" for k, v in stats)
        + "</section>"
    )
    sc = (a.get("session_cues") or {}).get("index")
    poss = (proto or {}).get("possibility") if proto else None
    parts.append("<section><h2>Possibility of deception, cue-based</h2>")
    parts.append(_gauge(sc, "whole session (discounted: no within-person comparison)"))
    if poss and poss.get("text"):
        parts.append(f"<p class='poss'>{_e(poss['text'])}</p>")
    parts.append("</section>")
    if proto and proto.get("questions"):
        rows = []
        for q in proto["questions"]:
            ci = q.get("control_index") or {}
            qi = q.get("cue_index") or {}
            lat = q.get("response_latency_ms")
            rows.append(
                f"<tr class='{_e(q['category'])}'><td>{_e(q['id'])}</td><td>{_e(q['category'])}</td>"
                f"<td class='txt'>{_e(q['text'])}</td><td>{'-' if lat is None else f'{lat:.0f} ms'}</td>"
                f"<td>{_e(q['deviations'])}</td>"
                f"<td style='color:{_band_color(qi.get('value'))}'>{'-' if qi.get('value') is None else round(qi['value'])}</td>"
                f"<td style='color:{_band_color(ci.get('value'))}'>{'-' if ci.get('value') is None else round(ci['value'])}</td>"
                f"<td class='txt'>{_e(', '.join(q.get('expression_patterns', [])[:3]))}</td></tr>"
            )
        parts.append(
            "<section><h2>Questions</h2><div class='wrap'><table><thead><tr><th>#</th><th>type</th>"
            "<th>question</th><th>latency</th><th>deviations</th><th>index vs calibration</th>"
            "<th>index vs control answers</th><th>patterns</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table></div></section>"
        )
    if moments:
        cards = []
        for e in moments:
            src = _img(d, e["event_id"])
            img = f"<img src='{src}' alt=''>" if src else "<div class='noimg'></div>"
            cards.append(
                f"<figure>{img}<figcaption><b>{_e(format_timecode(e['start_us'])[3:])}</b> "
                f"{_e(e['label'])}</figcaption></figure>"
            )
        parts.append(
            "<section><h2>Key moments</h2><div class='moments'>"
            + "".join(cards)
            + "</div></section>"
        )
    if patterns:
        parts.append(
            "<section><h2>Expression patterns</h2><p>"
            + ", ".join(f"{_e(k)} {v}" for k, v in sorted(patterns.items(), key=lambda kv: -kv[1]))
            + ". Patterns name what the face looked like, not what was felt.</p></section>"
        )
    narr = a.get("narrative") or []
    if narr:
        parts.append(
            "<section><h2>What happened</h2><ul>"
            + "".join(f"<li>{_e(x)}</li>" for x in narr)
            + "</ul></section>"
        )
    pc = a.get("pulse_check")
    if pc and pc.get("n_matched"):
        parts.append(
            f"<section><h2>Pulse check</h2><p>Camera estimate against {pc['n_matched']} watch "
            f"readings: mean error {pc['mae_bpm']} bpm, bias {pc['bias_bpm']:+} bpm.</p></section>"
        )
    nr = a.get("norms")
    if nr:
        parts.append(
            f"<section><h2>Against this person's earlier sessions</h2><p>Norms from "
            f"{nr['sessions_used']} sessions. Widened: {len(nr['widened'])} signals. Drift: "
            + (
                ", ".join(f"{_e(x['signal'])} {x['shift_sd']:+} SD" for x in nr["drift"][:5])
                or "none"
            )
            + ".</p></section>"
        )
    body = "\n".join(parts)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lightman report {_e(subject)} {_e(created)}</title>
<style>
{_CSS}
</style></head><body><main>
{body}
</main></body></html>"""
