import numpy as np

from lightman.protocol import Marker, summarize_protocol
from lightman.protocol.summary import parse_question_script
from lightman.schema.events import Event, EvidenceLevel, FeatureContribution


def _dev(start_us: int, end_us: int, feature: str, z: float) -> Event:
    return Event(
        event_id=f"ev_{start_us}", subject_id="s", source="video", event_type="baseline_deviation",
        level=EvidenceLevel.OBSERVATION, start_us=start_us, end_us=end_us, peak_us=start_us,
        label=feature, severity=abs(z), confidence=1.0, quality=1.0, baseline_quality=0.8,
        extractor_id="x",
        contributions=[FeatureContribution(feature=feature, unit="coefficient", peak_value=0.5,
                                           baseline_center=0.1, baseline_scale=0.05,
                                           peak_deviation=z, direction="increase")],
    )  # fmt: skip


def test_parse_script_categories_and_expected() -> None:
    qs = parse_question_script(
        "C: Is today Monday? [truth]\nR: Did you take it?  [LIE]\nplain question\n\n"
    )
    assert [q["category"] for q in qs] == ["control", "relevant", "neutral"]
    assert [q["expected"] for q in qs] == ["truth", "lie", None]
    assert qs[1]["text"] == "Did you take it?"


def test_summary_per_question_latency_deviations_and_comparison() -> None:
    t_us = (np.arange(1200) * 100_000).astype(np.int64)  # 120 s
    speaking = np.zeros(1200, dtype=bool)
    # question at 20 s, answer speech from 21.5 s to 30 s; question 2 at 40 s, speech 40.8-50 s
    speaking[215:300] = True
    speaking[408:500] = True
    speaking[605:700] = True
    speaking[802:900] = True
    markers = [
        Marker(
            kind="question",
            t_us=20_000_000,
            id="q1",
            text="control one",
            category="control",
            expected="truth",
        ),
        Marker(
            kind="question",
            t_us=40_000_000,
            id="q2",
            text="relevant one",
            category="relevant",
            expected="lie",
        ),
        Marker(
            kind="question",
            t_us=60_000_000,
            id="q3",
            text="control two",
            category="control",
            expected="truth",
        ),
        Marker(
            kind="question",
            t_us=80_000_000,
            id="q4",
            text="relevant two",
            category="relevant",
            expected="lie",
        ),
        Marker(kind="note", t_us=45_000_000, text="laughed"),
    ]
    events = [
        _dev(42_000_000, 43_000_000, "au.AU4", 5.0),
        _dev(44_000_000, 44_500_000, "au.AU4", 6.0),
        _dev(85_000_000, 86_000_000, "blendshape.jawOpen", 4.0),
        _dev(25_000_000, 25_500_000, "head.yaw_deg", 3.5),
    ]
    s = summarize_protocol(
        markers, events=events, t_us=t_us, speaking=speaking, session_end_us=120_000_000
    )
    assert [q.id for q in s.questions] == ["q1", "q2", "q3", "q4"]
    q1, q2 = s.questions[0], s.questions[1]
    assert q1.response_latency_ms == 1500 and q2.response_latency_ms == 800
    assert (
        q2.deviations == 2 and q2.max_severity == 6.0 and q2.top_signals[0]["feature"] == "au.AU4"
    )
    assert q1.end_us == 40_000_000 and q2.answer_speech_s > 8
    assert s.by_category["relevant"]["n"] == 2 and s.by_category["control"]["n"] == 2
    assert s.control_vs_relevant["delta_deviations_per_min"] > 0
    assert s.control_vs_relevant["permutation_p_deviations"] is not None
    assert any("anecdotal" in n for n in s.notes)
    assert s.ground_truth["n_lie"] == 2 and s.ground_truth["auroc"] == 0.75  # q4 scores below q1
    assert any("not interpretable" in n for n in s.notes)
    assert "not evidence of lie detection" in s.ground_truth["note"]


def test_summary_without_speech_and_end_marker() -> None:
    t_us = (np.arange(600) * 100_000).astype(np.int64)
    markers = [
        Marker(kind="question", t_us=10_000_000, id="q1", text="a"),
        Marker(kind="end", t_us=20_000_000),
    ]
    s = summarize_protocol(markers, events=[], t_us=t_us, speaking=None, session_end_us=60_000_000)
    assert s.questions[0].end_us == 20_000_000 and s.questions[0].response_latency_ms is None
    assert any("response latency not available" in n for n in s.notes)
    assert s.ground_truth["auroc"] is None and s.control_vs_relevant == {}
