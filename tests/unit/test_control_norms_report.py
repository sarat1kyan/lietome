import json
from pathlib import Path

import numpy as np

from lightman.baseline.norms import apply_norms, load_norms, update_norms
from lightman.baseline.robust import BaselineSnapshot, SignalBaseline
from lightman.features.rppg import PulseEstimate, pulse_agreement
from lightman.protocol.summary import Marker, summarize_protocol


def _session(n: int = 1200):
    t = (np.arange(n) * 100_000).astype(np.int64)  # 120 s at 10 fps
    sig = {
        "au.AU4": np.full(n, 0.2),
        "au.AU7": np.full(n, 0.2),
        "au.AU23": np.full(n, 0.2),
        "au.AU24": np.full(n, 0.2),
        "head.speed_deg_s": np.full(n, 8.0),
    }
    rng = np.random.default_rng(0)
    sig = {k: v + rng.normal(0, 0.02 * max(1.0, float(v[0])), n) for k, v in sig.items()}
    return t, sig


def test_control_referenced_index_uses_the_other_control_answers() -> None:
    t, sig = _session()
    # answers are generally tenser than calibration (all questions), the relevant one more so
    for k in ("au.AU4", "au.AU7", "au.AU23"):
        sig[k][100:] += 0.25
    for k in ("au.AU4", "au.AU7", "au.AU24"):
        sig[k][900:1100] += 0.3
    center = dict.fromkeys(sig, 0.2)
    center["head.speed_deg_s"] = 8.0
    scale = dict.fromkeys(sig, 0.05)
    scale["head.speed_deg_s"] = 2.0
    markers = [
        Marker(kind="question", t_us=12_000_000, id="q1", text="c1", category="control"),
        Marker(kind="end", t_us=30_000_000),
        Marker(kind="question", t_us=35_000_000, id="q2", text="c2", category="control"),
        Marker(kind="end", t_us=55_000_000),
        Marker(kind="question", t_us=60_000_000, id="q3", text="c3", category="control"),
        Marker(kind="end", t_us=80_000_000),
        Marker(kind="question", t_us=90_000_000, id="q4", text="r", category="relevant"),
        Marker(kind="end", t_us=110_000_000),
    ]
    ps = summarize_protocol(
        markers,
        events=[],
        t_us=t,
        speaking=None,
        session_end_us=int(t[-1]),
        cue_inputs={"signals": sig, "baseline_center": center, "baseline_scale": scale},
    )
    by = {q.id: q for q in ps.questions}
    # against calibration every answer looks tense; against control answers only q4 stands out
    assert all(by[i].cue_index["value"] > 55 for i in ("q1", "q2", "q3", "q4"))
    assert all(by[i].control_index is not None for i in ("q1", "q2", "q3", "q4"))
    assert by["q4"].control_index["value"] > by["q1"].control_index["value"] + 10
    assert by["q1"].control_index["value"] < 60
    assert by["q4"].control_shift and by["q4"].control_shift[0]["shift_sd"] > 2
    assert ps.possibility is not None and ps.possibility["basis"] == "control answers"
    assert "control answers" in ps.possibility["text"]


def _snap(scale: float, center: float = 0.2) -> BaselineSnapshot:
    return BaselineSnapshot(
        mode="leading_window",
        window_start_us=0,
        window_end_us=40_000_000,
        frames_in_window=500,
        frames_used=500,
        quality=0.9,
        signals={
            "au.AU4": SignalBaseline(
                feature="au.AU4",
                unit="probability",
                center=center,
                scale=scale,
                n=500,
                floor_applied=False,
            )
        },
    )


def test_norms_widen_narrow_calibrations_and_flag_drift(tmp_path: Path) -> None:
    assert load_norms(tmp_path, "anna") is None
    update_norms(tmp_path, "anna", "20260101T000000Z-aaaaaa", "2026-01-01", _snap(0.10))
    assert load_norms(tmp_path, "anna") is None  # one session is not a norm
    update_norms(tmp_path, "anna", "20260102T000000Z-bbbbbb", "2026-01-02", _snap(0.12))
    norms = load_norms(tmp_path, "anna")
    assert norms is not None and norms["sessions"] == 2
    adjusted, rep = apply_norms(_snap(0.02, center=0.9), norms)
    assert rep is not None and rep["widened"] == ["au.AU4"]
    assert abs(adjusted.signals["au.AU4"].scale - 0.055) < 1e-9
    assert rep["drift"] and rep["drift"][0]["signal"] == "au.AU4"
    assert any("usual" in n for n in adjusted.notes)
    _same, rep2 = apply_norms(_snap(0.11), norms)
    assert rep2 is not None and rep2["widened"] == [] and rep2["drift"] == []
    assert load_norms(tmp_path, "../etc") is None  # ids are validated
    data = json.loads((tmp_path / "_subjects" / "anna.json").read_text())
    assert len(data["sessions"]) == 2


def test_pulse_agreement_pairs_readings_with_usable_estimates() -> None:
    est = [PulseEstimate(t_us=i * 1_000_000, bpm=70.0 + (i % 3), snr_db=6.0) for i in range(60)]
    est[30] = PulseEstimate(t_us=30_000_000, bpm=120.0, snr_db=0.5)  # gated out
    res = pulse_agreement(est, [(10_000_000, 72.0), (30_000_000, 70.0), (200_000_000, 80.0)])
    assert res is not None and res["n_references"] == 3 and res["n_matched"] == 2
    assert res["mae_bpm"] is not None and res["mae_bpm"] < 3
    assert pulse_agreement(est, []) is None


def test_share_report_renders_a_session(tmp_path: Path) -> None:
    from lightman.report.share import key_moments, render_share_report

    d = tmp_path / "20260101T000000Z-cccccc"
    d.mkdir()
    (d / "analysis.json").write_text(json.dumps({
        "duration_us": 90_000_000, "mode": "live", "event_counts": {"episode": 2},
        "narrative": ["One line <b>escaped</b>."],
        "session_cues": {"index": {
            "value": 52.0, "band": "unremarkable", "reliability": 0.4, "drivers": [],
        }},
    }))  # fmt: skip
    (d / "manifest.json").write_text(
        json.dumps({"subject_ids": ["anna"], "created_utc": "2026-01-01T00:00:00"})
    )
    ev = [
        {"event_id": "ev_00001", "event_type": "episode", "start_us": 5_000_000,
         "end_us": 6_000_000, "severity": 7.0, "label": "episode", "tags": []},
        {"event_id": "ev_00002", "event_type": "expression_pattern", "start_us": 8_000_000,
         "end_us": 8_300_000, "severity": 3.0, "label": "brief expression pattern: fear",
         "tags": ["expression", "fear", "brief", "negative"]},
    ]  # fmt: skip
    (d / "events.json").write_text(json.dumps({"events": ev}))
    html = render_share_report(d)
    assert "anna" in html and "&lt;b&gt;escaped&lt;/b&gt;" in html
    assert "fear 1" in html and "negative" not in html.split("Expression patterns")[1][:80]
    assert "not probabilities" in html
    assert [e["event_id"] for e in key_moments(ev)] == ["ev_00001"]
