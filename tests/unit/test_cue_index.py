import numpy as np

from lightman.interpretation.cues import CUES, cue_profile, deception_cue_index
from lightman.interpretation.expressions import (
    PATTERN_ENTER,
    StreamingExpressionDetector,
    detect_expression_patterns,
    pattern_scores,
    personal_thresholds,
)
from lightman.protocol.summary import Marker, summarize_protocol
from lightman.schema.events import Event, EvidenceLevel, FeatureContribution


def _profile(**present: bool):
    rows = []
    for c in CUES:
        p = present.get(c.key)
        if p is None:
            rows.append({"key": c.key, "name": c.name, "value": None, "present": False})
        else:
            v = 1.5 if p else 0.0
            if c.key == "movement":
                v = -1.5 if p else 0.0
            rows.append({"key": c.key, "name": c.name, "value": v, "present": p})
    return {"window_us": [0, 60_000_000], "cues": rows}


def test_index_neutral_when_nothing_moved_and_rises_with_weighted_cues() -> None:
    none = deception_cue_index(_profile(pitch=False, lip_press=False, tension=False))
    assert none["value"] == 50.0 and none["band"] == "unremarkable" and none["drivers"] == []
    some = deception_cue_index(_profile(pitch=True, lip_press=False, tension=False))
    strong = deception_cue_index(
        _profile(pitch=True, lip_press=True, tension=True, negative_affect=True)
    )
    assert 50 < some["value"] < strong["value"] <= 100
    assert strong["band"] in ("elevated", "high") and "higher voice pitch" in strong["drivers"]
    # a cue that moved the other way pulls the index below 50
    prof = _profile(pitch=False, lip_press=False)
    prof["cues"][0]["value"] = -1.5
    low = deception_cue_index(prof)
    assert low["value"] < 50 and "higher voice pitch" in low["counters"]
    # short windows and few evaluable cues shrink toward 50
    short = _profile(pitch=True, lip_press=True, tension=True, negative_affect=True)
    short["window_us"] = [0, 5_000_000]
    assert deception_cue_index(short)["value"] < strong["value"]
    assert deception_cue_index({"window_us": [0, 1], "cues": []})["value"] is None
    assert "not a calibrated probability" in strong["caveat"]


def _pattern_event(k: int, start_us: int, name: str, tags: list[str]) -> Event:
    return Event(
        event_id=f"ev_{k:05d}",
        subject_id="s",
        source="video",
        event_type="expression_pattern",
        level=EvidenceLevel.INTERPRETATION,
        start_us=start_us,
        end_us=start_us + 300_000,
        peak_us=start_us,
        label=f"expression pattern: {name}",
        description="x",
        contributions=[
            FeatureContribution(
                feature="au.AU4",
                unit="probability",
                peak_value=0.9,
                baseline_center=0.0,
                baseline_scale=1.0,
                peak_deviation=0.9,
                direction="increase",
            )
        ],
        severity=3.0,
        confidence=0.7,
        quality=1.0,
        baseline_quality=1.0,
        extractor_id="x",
        tags=["expression", name, *tags],
    )


def test_cue_profile_counts_negative_and_brief_patterns_and_tension() -> None:
    n = 300
    t = (np.arange(n) * 100_000).astype(np.int64)
    sig = {"au.AU4": np.full(n, 0.1), "au.AU7": np.full(n, 0.1), "au.AU23": np.full(n, 0.1)}
    sig["au.AU4"][100:] = 0.6  # tension rises after 10 s
    center = dict.fromkeys(sig, 0.1)
    scale = dict.fromkeys(sig, 0.1)
    events = [
        _pattern_event(1, 12_000_000, "fear", ["brief", "negative"]),
        _pattern_event(3, 18_000_000, "contempt", ["brief", "negative"]),
        _pattern_event(2, 15_000_000, "happiness", []),
        _pattern_event(4, 2_000_000, "happiness", []),
    ]
    prof = cue_profile(
        window=(10_000_000, 30_000_000),
        t_us=t,
        signals=sig,
        baseline_center=center,
        baseline_scale=scale,
        voice_f0_z=None,
        blink_times_us=[],
        reference_blink_rate=None,
        response_latency_ms=None,
        control_latency_ms=None,
        events=events,
    )
    by = {r["key"]: r for r in prof["cues"]}
    assert by["negative_affect"]["present"] and by["brief_pattern"]["present"]
    assert by["tension"]["present"] and by["tension"]["value"] > 1
    assert prof["index"]["value"] > 55 and "facial tension" in " ".join(prof["index"]["drivers"])
    before = cue_profile(
        window=(0, 9_000_000),
        t_us=t,
        signals=sig,
        baseline_center=center,
        baseline_scale=scale,
        voice_f0_z=None,
        blink_times_us=[],
        reference_blink_rate=None,
        response_latency_ms=None,
        control_latency_ms=None,
        events=events,
    )
    assert before["index"]["value"] == 50.0


def test_new_prototypes_and_personal_thresholds() -> None:
    n = 30
    aus = [
        "AU1",
        "AU2",
        "AU4",
        "AU5",
        "AU6",
        "AU7",
        "AU9",
        "AU10",
        "AU12",
        "AU15",
        "AU20",
        "AU23",
        "AU24",
        "AU25",
        "AU26",
    ]
    sig = {f"au.{a}": np.full(n, 0.1) for a in aus}
    sig["gaze.vertical"] = np.zeros(n)
    sig["au.AU12"][:10] = 0.8
    sig["gaze.vertical"][:10] = -0.4  # smile with gaze down = embarrassment display
    sig["au.AU4"][10:20] = 0.8
    sig["au.AU7"][10:20] = 0.8
    sig["au.AU10"][10:20] = 0.7  # distress core
    sig["au.AU7"][20:] = 0.8
    sig["au.AU23"][20:] = 0.8  # tension
    sc = pattern_scores(sig, n)
    assert sc["embarrassment"][5] >= PATTERN_ENTER and sc["social smile"][5] >= PATTERN_ENTER
    assert sc["embarrassment"][15] == 0.0
    assert sc["distress"][15] >= PATTERN_ENTER and sc["tension"][25] >= PATTERN_ENTER
    # personal floor: a face resting at 0.6 on a pattern needs more than the default entry
    enter, exit_ = personal_thresholds(np.full(20, 0.6))
    assert enter == 0.75 and abs(exit_ - 0.60) < 1e-9
    assert personal_thresholds(np.full(20, 0.1)) == (PATTERN_ENTER, 0.40)
    assert personal_thresholds(np.full(20, 0.9))[0] == 0.85  # capped
    # offline: calibration frames with a constant brow furrow suppress later furrow events
    t = (np.arange(n) * 100_000).astype(np.int64)
    sig2 = {f"au.{a}": np.full(n, 0.1) for a in aus}
    sig2["au.AU4"][:] = 0.6  # resting furrow the whole time
    ev = detect_expression_patterns(
        t_us=t, quality=np.ones(n), signals=sig2, subject_id="s", extractor_id="x",
        baseline_quality=1.0, calibration_end_us=int(t[15]),
    )  # fmt: skip
    assert not [e for e in ev if "brow furrow" in e.tags]
    ev_nocal = detect_expression_patterns(
        t_us=t, quality=np.ones(n), signals=sig2, subject_id="s", extractor_id="x",
        baseline_quality=1.0,
    )  # fmt: skip
    assert [e for e in ev_nocal if "brow furrow" in e.tags]
    # streaming learns the same floor
    st = StreamingExpressionDetector(
        subject_id="s", extractor_id="x", baseline_quality=1.0, frame_period_us=100_000
    )
    for _ in range(15):
        st.learn(1.0, {"au.AU4": 0.6, "au.AU1": 0.1, "au.AU2": 0.1, "au.AU12": 0.1})
    st.finish_learning()
    assert st.thresholds["brow furrow"][0] > PATTERN_ENTER
    out = []
    for i in range(20):
        out += st.update(
            i * 100_000, 1.0, {"au.AU4": 0.6, "au.AU1": 0.1, "au.AU2": 0.1, "au.AU12": 0.1}
        )
    assert out == []
    # negative valence tag on fear events
    sig3 = {f"au.{a}": np.full(n, 0.1) for a in aus}
    for a in ("AU1", "AU2", "AU4", "AU5", "AU7", "AU20", "AU26"):
        sig3[f"au.{a}"][5:15] = 0.9
    fear = detect_expression_patterns(
        t_us=t,
        quality=np.ones(n),
        signals=sig3,
        subject_id="s",
        extractor_id="x",
        baseline_quality=1.0,
    )
    assert any("fear" in e.tags and "negative" in e.tags for e in fear)


def test_protocol_possibility_compares_relevant_with_control() -> None:
    n = 900
    t = (np.arange(n) * 100_000).astype(np.int64)  # 90 s
    sig = {
        "au.AU4": np.full(n, 0.1),
        "au.AU7": np.full(n, 0.1),
        "au.AU23": np.full(n, 0.1),
        "au.AU24": np.full(n, 0.1),
        "head.speed_deg_s": np.full(n, 10.0),
    }
    # relevant answer (60-85 s): tension and lip press up, head still
    sig["au.AU4"][600:850] = 0.7
    sig["au.AU7"][600:850] = 0.7
    sig["au.AU24"][600:850] = 0.7
    sig["head.speed_deg_s"][600:850] = 1.0
    center = {k: float(v[0]) for k, v in sig.items()}
    scale = dict.fromkeys(sig, 0.1)
    scale["head.speed_deg_s"] = 5.0
    markers = [
        Marker(kind="question", t_us=10_000_000, id="q1", text="c", category="control"),
        Marker(kind="end", t_us=30_000_000),
        Marker(kind="question", t_us=35_000_000, id="q2", text="c", category="control"),
        Marker(kind="end", t_us=55_000_000),
        Marker(kind="question", t_us=60_000_000, id="q3", text="r", category="relevant"),
        Marker(kind="end", t_us=85_000_000),
    ]
    events = [_pattern_event(1, 70_000_000, "contempt", ["negative"])]
    ps = summarize_protocol(
        markers,
        events=events,
        t_us=t,
        speaking=None,
        session_end_us=int(t[-1]),
        cue_inputs={"signals": sig, "baseline_center": center, "baseline_scale": scale},
    )
    q3 = next(q for q in ps.questions if q.id == "q3")
    assert q3.cue_index is not None and q3.cue_index["value"] > 60
    assert ps.possibility is not None
    assert ps.possibility["top_question"] == "q3" and ps.possibility["delta"] > 10
    assert ps.possibility["delta_ci95"] is None  # one relevant question: no interval
    assert "possibility" in ps.possibility["text"] and "not a probability" in ps.possibility["text"]
